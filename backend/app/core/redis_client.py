import redis.asyncio as redis
from typing import Optional, Callable, Awaitable
import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)

# Conexión global a Redis
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
client = redis.from_url(redis_url, decode_responses=True)

# Coincide con "room:{ABCD}:timeout:<round>:<turn_index>" y captura el
# código de sala, la ronda y el índice de turno que arma ese temporizador.
_TIMEOUT_KEY_PATTERN = re.compile(r"^room:\{(.+)\}:timeout:(\d+):(\d+)$")


async def ensure_keyspace_notifications_enabled() -> bool:
    """
    Intenta habilitar `notify-keyspace-events Ex` en tiempo de ejecución.

    Sin esto, el listener de expiración de `subscribe_to_turn_timeouts`
    nunca recibirá ningún evento y los turnos jamás avanzarán por tiempo
    agotado — este es el mecanismo documentado en `02_architecture.md`,
    sección 4.2, y es una dependencia dura, no opcional.

    Algunos proveedores de Redis administrado deshabilitan `CONFIG SET`;
    si eso ocurre, se registra un error explícito en los logs en vez de
    fallar en silencio, para que quede claro que hace falta configurarlo
    manualmente en `redis.conf` o en el panel del proveedor.
    """
    try:
        current = await client.config_get("notify-keyspace-events")
        current_value = current.get("notify-keyspace-events", "")
        if "E" in current_value and ("x" in current_value or "g" in current_value.lower()):
            return True
        await client.config_set("notify-keyspace-events", "Ex")
        return True
    except Exception as exc:
        logger.error(
            "No se pudo configurar 'notify-keyspace-events Ex' vía CONFIG SET (%s). "
            "Los temporizadores de turno NO avanzarán automáticamente hasta que esto "
            "se configure manualmente en redis.conf o en el proveedor administrado.",
            exc,
        )
        return False


async def subscribe_to_turn_timeouts(on_timeout: Callable[[str, int, int], Awaitable[None]]) -> None:
    """
    Se suscribe al canal de notificaciones keyspace de expiración
    (`__keyevent@<db>__:expired`) y, para cada clave que coincida con el
    patrón `room:{CODIGO}:timeout:<ronda>:<indice_turno>`, invoca
    `on_timeout(codigo_de_sala, ronda, indice_turno)`.

    Corre indefinidamente como una tarea de fondo (ver `main.py`, evento de
    arranque). Cualquier instancia de FastAPI que esté corriendo puede
    recibir esta notificación — es intencional: la resolución real de la
    carrera contra `send_word` ocurre después, bajo el cerrojo distribuido.
    """
    db_index = client.connection_pool.connection_kwargs.get("db", 0)
    channel = f"__keyevent@{db_index}__:expired"

    pubsub = client.pubsub()
    await pubsub.subscribe(channel)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue

        expired_key = message["data"]
        match = _TIMEOUT_KEY_PATTERN.match(expired_key)
        if not match:
            continue

        room_id, round_number, turn_index = match.group(1), int(match.group(2)), int(match.group(3))
        try:
            await on_timeout(room_id, round_number, turn_index)
        except Exception:
            logger.exception("Error procesando timeout de turno para la sala %s", room_id)

# Script Lua para Full Fencing: Verifica el token, si coincide, actualiza el estado y borra el cerrojo.
LUA_UPDATE_AND_UNLOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    redis.call("set", KEYS[2], ARGV[2])
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

async def create_room_atomic(room_id: str, state_json: str) -> bool:
    """
    Intenta crear la sala. Retorna True si tuvo éxito, False si hubo colisión (NX).
    """
    key = f"room:{{{room_id}}}:state"
    result = await client.set(key, state_json, nx=True)
    return bool(result)

async def get_room_state(room_id: str) -> Optional[str]:
    """Obtiene el JSON actual de la sala."""
    key = f"room:{{{room_id}}}:state"
    return await client.get(key)

async def acquire_lock(room_id: str, worker_uuid: str) -> bool:
    """
    Adquiere un cerrojo con un tiempo de vida máximo de 5 segundos.
    """
    lock_key = f"room:{{{room_id}}}:lock"
    result = await client.set(lock_key, worker_uuid, nx=True, px=5000)
    return bool(result)

_update_and_unlock_script = client.register_script(LUA_UPDATE_AND_UNLOCK)


async def release_lock_and_update(room_id: str, worker_uuid: str, new_state_json: str) -> bool:
    """
    Ejecuta el script Lua para escribir el estado solo si mantenemos el cerrojo.
    """
    lock_key = f"room:{{{room_id}}}:lock"
    state_key = f"room:{{{room_id}}}:state"

    result = await _update_and_unlock_script(keys=[lock_key, state_key], args=[worker_uuid, new_state_json])
    return bool(result)

async def set_turn_timeout(room_id: str, round_number: int, turn_index: int, ttl_seconds: int = 20):
    """
    Establece el reloj efímero que disparará la notificación keyspace al
    expirar. El nombre de la clave codifica `round_number` y `turn_index`
    para que el listener pueda distinguir una notificación vigente de una
    obsoleta (ver `game_service.resolve_turn_timeout`).
    """
    timeout_key = f"room:{{{room_id}}}:timeout:{round_number}:{turn_index}"
    await client.set(timeout_key, "active", ex=ttl_seconds)