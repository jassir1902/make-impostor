"""
Cobertura del ciclo de vida del cerrojo distribuido en `websockets.py`.

El doble de Redis de este archivo NO simula expiración por TTL: sirve para
demostrar que el código libera el cerrojo por todos sus caminos de salida,
no que las semánticas de Redis sean correctas. La prueba de concurrencia
real contra un Redis de verdad (07_testing_and_qa_strategy.md, sección 4.1)
sigue pendiente y no la sustituye este archivo.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import websockets as ws_module
from app.core import redis_client
from app.models.game import GameRoom, Player

ROOM_ID = "ABCD"
LOCK_KEY = f"room:{{{ROOM_ID}}}:lock"
STATE_KEY = f"room:{{{ROOM_ID}}}:state"


class FakeRedisClient:
    """
    Doble mínimo de `redis.asyncio.Redis` con lo que tocan las rutas bajo
    prueba. Sin expiración: `px`/`ex` se aceptan y se ignoran, porque estas
    pruebas afirman sobre presencia/ausencia de claves, no sobre tiempo.
    """

    def __init__(self):
        self.store: dict[str, str] = {}
        self.sorted_sets: dict[str, dict[str, float]] = {}

    async def set(self, key, value, nx=False, px=None, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, *keys):
        removed = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                removed += 1
        return removed

    async def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)
        return len(mapping)

    async def zrange(self, key, start, end):
        members = sorted(self.sorted_sets.get(key, {}).items(), key=lambda kv: kv[1])
        return [member for member, _ in members]

    async def zrem(self, key, member):
        return int(self.sorted_sets.get(key, {}).pop(member, None) is not None)


def _make_update_and_unlock(fake: FakeRedisClient):
    """Equivalente en Python de LUA_UPDATE_AND_UNLOCK."""

    async def script(keys, args):
        lock_key, state_key = keys
        token, new_state = args
        if fake.store.get(lock_key) == token:
            fake.store[state_key] = new_state
            del fake.store[lock_key]
            return 1
        return 0

    return script


def _make_release_lock(fake: FakeRedisClient):
    """Equivalente en Python de LUA_RELEASE_LOCK."""

    async def script(keys, args):
        (lock_key,) = keys
        (token,) = args
        if fake.store.get(lock_key) == token:
            del fake.store[lock_key]
            return 1
        return 0

    return script


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedisClient()
    monkeypatch.setattr(redis_client, "client", fake)
    monkeypatch.setattr(redis_client, "_update_and_unlock_script", _make_update_and_unlock(fake))
    monkeypatch.setattr(redis_client, "_release_lock_script", _make_release_lock(fake))
    return fake


@pytest.fixture
def client(fake_redis):
    """
    App mínima con solo el router de WebSocket: evita el evento de arranque
    de `main.py`, que abriría una suscripción real de keyspace a Redis.
    """
    app = FastAPI()
    app.include_router(ws_module.router)

    # `manager` es un singleton de módulo: sin esto, los sockets de una
    # prueba sobreviven a la siguiente.
    ws_module.manager.active_connections.clear()
    ws_module.manager.socket_to_token.clear()
    ws_module.manager.rate_limits.clear()

    with TestClient(app) as test_client:
        yield test_client


def seed_room(fake: FakeRedisClient, room: GameRoom) -> None:
    fake.store[STATE_KEY] = room.model_dump_json()


def read_room(fake: FakeRedisClient) -> GameRoom:
    return GameRoom.model_validate_json(fake.store[STATE_KEY])


# --- Liberación fenceada (unidad sobre redis_client) --------------------------


class TestReleaseLock:
    @pytest.mark.asyncio
    async def test_releases_when_token_matches(self, fake_redis):
        fake_redis.store[LOCK_KEY] = "worker-a"

        assert await redis_client.release_lock(ROOM_ID, "worker-a") is True
        assert LOCK_KEY not in fake_redis.store

    @pytest.mark.asyncio
    async def test_does_not_delete_another_workers_lock(self, fake_redis):
        """
        El worker A se demoró más que su PX, el cerrojo expiró y B lo tomó.
        Cuando A llega tarde a liberar, NO debe borrar el cerrojo de B: eso
        dejaría a dos workers dentro de la misma sección crítica, que es lo
        que el fencing existe para impedir (02_architecture.md, 4.3).
        """
        fake_redis.store[LOCK_KEY] = "worker-b"

        assert await redis_client.release_lock(ROOM_ID, "worker-a") is False
        assert fake_redis.store[LOCK_KEY] == "worker-b"

    @pytest.mark.asyncio
    async def test_is_noop_when_lock_already_gone(self, fake_redis):
        """
        Se invoca desde un `finally` sin saber por qué camino se salió, así
        que tiene que ser segura cuando `release_lock_and_update` ya borró
        el cerrojo.
        """
        assert await redis_client.release_lock(ROOM_ID, "worker-a") is False
        assert LOCK_KEY not in fake_redis.store


# --- Ciclo de vida del cerrojo en el endpoint --------------------------------


class TestEndpointReleasesLock:
    def test_lock_released_after_successful_join(self, client, fake_redis):
        seed_room(fake_redis, GameRoom(id=ROOM_ID))

        with client.websocket_connect(f"/ws/room/{ROOM_ID}") as ws:
            ws.send_json({
                "action": "join_room",
                "payload": {"room_id": ROOM_ID, "player_name": "Ana", "secret_token": None},
            })
            ws.receive_json()  # joined_successfully
            ws.receive_json()  # room_update

        assert LOCK_KEY not in fake_redis.store
        assert len(read_room(fake_redis).players) == 1

    def test_lock_released_after_rejected_action(self, client, fake_redis):
        """
        Prueba de regresión del hallazgo 1. Un `send_word` fuera de fase se
        rechaza con `continue`, que saltaba por encima de la liberación del
        cerrojo y lo dejaba retenido los 5 s completos de su PX. En esa
        ventana el timeout de turno no lograba adquirirlo, se rendía en
        silencio, y como su clave TTL ya había expirado el turno se quedaba
        sin reloj de forma permanente.
        """
        seed_room(fake_redis, GameRoom(id=ROOM_ID))

        with client.websocket_connect(f"/ws/room/{ROOM_ID}") as ws:
            ws.send_json({
                "action": "join_room",
                "payload": {"room_id": ROOM_ID, "player_name": "Ana", "secret_token": None},
            })
            ws.receive_json()
            ws.receive_json()

            # La sala sigue en "waiting": el servidor responde INVALID_PHASE.
            ws.send_json({"action": "send_word", "payload": {"word": "Perro"}})
            error = ws.receive_json()

        assert error["action"] == "error"
        assert error["payload"]["code"] == "INVALID_PHASE"
        assert LOCK_KEY not in fake_redis.store

    def test_lock_released_when_room_disappears_mid_session(self, client, fake_redis):
        """
        La rama que cierra con 4004 sale con `break`, otro camino que se
        saltaba la liberación.
        """
        seed_room(fake_redis, GameRoom(id=ROOM_ID))

        with client.websocket_connect(f"/ws/room/{ROOM_ID}") as ws:
            ws.send_json({
                "action": "join_room",
                "payload": {"room_id": ROOM_ID, "player_name": "Ana", "secret_token": None},
            })
            ws.receive_json()
            ws.receive_json()

            del fake_redis.store[STATE_KEY]  # la sala desaparece bajo los pies

            ws.send_json({"action": "next_round", "payload": None})

        assert LOCK_KEY not in fake_redis.store

    def test_lock_released_after_unauthorized_action(self, client, fake_redis):
        """
        Un no-Host intentando `start_game` sale por `UNAUTHORIZED_ACTION`,
        otro de los trece `continue` que dejaban el cerrojo retenido.
        """
        room = GameRoom(id=ROOM_ID)
        host = Player(name="Host", is_host=True)
        room.players[host.id] = host
        seed_room(fake_redis, room)

        with client.websocket_connect(f"/ws/room/{ROOM_ID}") as ws:
            ws.send_json({
                "action": "join_room",
                "payload": {"room_id": ROOM_ID, "player_name": "Ana", "secret_token": None},
            })
            ws.receive_json()
            ws.receive_json()

            ws.send_json({
                "action": "start_game",
                "payload": {
                    "topic_id": "cualquiera",
                    "imposters_count": 1,
                    "use_hints": True,
                    "show_category": True,
                    "anonymous_voting": False,
                },
            })
            error = ws.receive_json()

        assert error["payload"]["code"] == "UNAUTHORIZED_ACTION"
        assert LOCK_KEY not in fake_redis.store
