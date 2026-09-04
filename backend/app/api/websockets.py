import uuid
import time
import asyncio
from typing import Dict, List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from app.models.events import ClientMessage
from app.models.game import Player, GameRoom
from app.core import redis_client
from app.services import game_service
from app.api import routes

MAX_PLAYERS_PER_ROOM = 10  # Límite de jugadores por sala
RATE_LIMIT_MESSAGES = 5    # Máximo de mensajes
RATE_LIMIT_WINDOW = 1.0    # Por segundo

# Reintentos de adquisición del cerrojo distribuido antes de descartar un
# mensaje. Sin esto, cualquier colisión normal entre dos acciones legítimas
# de jugadores distintos (ej. varios votos casi simultáneos) se perdería en
# silencio tras un único intento fallido — el diseño documentado solo acepta
# el descarte silencioso para la carrera específica turno-vs-timeout, no
# para la contención ordinaria entre jugadores.
LOCK_ACQUIRE_MAX_ATTEMPTS = 6
LOCK_ACQUIRE_RETRY_DELAY = 0.08  # segundos


async def acquire_lock_with_retry(room_id: str, worker_uuid: str) -> bool:
    for attempt in range(LOCK_ACQUIRE_MAX_ATTEMPTS):
        if await redis_client.acquire_lock(room_id, worker_uuid):
            return True
        await asyncio.sleep(LOCK_ACQUIRE_RETRY_DELAY)
    return False


# Ventana de gracia antes de migrar el Host tras una desconexión. Un refresh
# de página o un corte de red breve reconecta muchísimo antes de esto — solo
# si el Host sigue offline al cabo de esta ventana se considera un abandono
# real (01_game_design.md, sección 6: "mantiene su lugar, su rol y su estado
# vital" ante un refresh o corte temporal).
HOST_MIGRATION_GRACE_PERIOD_SECONDS = 12.0


async def schedule_host_migration_if_still_offline(room_id: str, secret_token: str) -> None:
    """
    Se programa como tarea de fondo al desconectarse un Host. Si para
    cuando despierta el jugador ya reconectó (is_online volvió a True) o ya
    no es Host (otra ruta ya migró, ej. un leave_room explícito mientras
    tanto), no hace nada — evita tanto el "flip" instantáneo de Host que
    producía un simple refresh como la condición de carrera contra el
    join_room de la reconexión.
    """
    await asyncio.sleep(HOST_MIGRATION_GRACE_PERIOD_SECONDS)

    worker_uuid = str(uuid.uuid4())
    if not await acquire_lock_with_retry(room_id, worker_uuid):
        return

    try:
        state_json = await redis_client.get_room_state(room_id)
        if not state_json:
            return

        room = GameRoom.model_validate_json(state_json)
        player = next((p for p in room.players.values() if p.secret_token == secret_token), None)

        if not player or player.is_online or not player.is_host:
            return

        migrated = await game_service.handle_host_migration(room, redis_client)
        saved = await redis_client.release_lock_and_update(room_id, worker_uuid, room.model_dump_json())
        if saved and migrated:
            await manager.broadcast_room_view(room)
    finally:
        await redis_client.release_lock(room_id, worker_uuid)

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        # Mapeo local de esta instancia: room_id -> { secret_token: WebSocket }
        # Nótese que ahora indexamos por secret_token para manejar el Last-One-Wins
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}
        # Mapeo para protección contra flood: id_del_socket -> lista de timestamps
        self.rate_limits: Dict[str, List[float]] = {}
        # Mapeo inverso de socket (por su hash) al secret_token autenticado (Zero-Trust)
        self.socket_to_token: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.rate_limits[id(websocket)] = []

    def check_rate_limit(self, websocket: WebSocket) -> bool:
        """Implementa un limitador de tasa simple (Token Bucket). Retorna True si excede el límite."""
        now = time.time()
        socket_id = id(websocket)
        
        # Limpiamos timestamps viejos
        self.rate_limits[socket_id] = [t for t in self.rate_limits[socket_id] if now - t < RATE_LIMIT_WINDOW]
        self.rate_limits[socket_id].append(now)
        
        return len(self.rate_limits[socket_id]) > RATE_LIMIT_MESSAGES

    async def disconnect(self, websocket: WebSocket, room_id: Optional[str] = None):
        socket_id = id(websocket)
        if socket_id in self.rate_limits:
            del self.rate_limits[socket_id]
            
        token = self.socket_to_token.get(websocket)
        if token and room_id and room_id in self.active_connections:
            if token in self.active_connections[room_id] and self.active_connections[room_id][token] == websocket:
                del self.active_connections[room_id][token]
        
        if websocket in self.socket_to_token:
            del self.socket_to_token[websocket]

    def has_active_connection(self, room_id: str, secret_token: str) -> bool:
        """
        True si `secret_token` sigue teniendo un socket activo registrado en
        esta sala (en esta instancia). Se usa para evitar que la limpieza de
        una conexión vieja, cerrada por la política Last-One-Wins (código
        4009), sobrescriba el estado 'is_online=True' que la conexión nueva
        ya estableció — de lo contrario, un jugador que se acaba de
        reconectar terminaría marcado como desconectado.
        """
        return room_id in self.active_connections and secret_token in self.active_connections[room_id]

    async def send_error(self, websocket: WebSocket, code: str, message: str):
        """Envía un error personalizado (Taxonomía Estricta) sin cerrar el socket."""
        try:
            await websocket.send_json({
                "action": "error",
                "payload": {"code": code, "message": message}
            })
        except Exception:
            pass

    async def broadcast_room_view(self, room: GameRoom):
        """
        Serializa el estado de la sala de forma segura ocultando los roles
        y lo envía EXCLUSIVAMENTE a los sockets que residen en esta instancia local.
        (En la Fase 5, este método será llamado al consumir eventos de Redis Streams).
        """
        room_id = room.id
        if room_id not in self.active_connections:
            return

        for secret_token, websocket in self.active_connections[room_id].items():
            # Buscar el jugador dueño del secret_token
            viewer = next((p for p in room.players.values() if p.secret_token == secret_token), None)
            if not viewer:
                continue

            is_imposter = viewer.role == "impostor"
            
            # 1. Limpiar datos de los demás jugadores (Ocultar el rol exacto)
            safe_players = {}
            for pid, p in room.players.items():
                safe_players[pid] = {
                    "id": p.id,
                    "name": p.name,
                    "is_online": p.is_online,
                    "is_host": p.is_host,
                    "is_alive": p.is_alive,
                    "score": p.score,
                }
                # Ocultar el rol es una protección de Zero-Trust mientras la
                # partida está en curso (playing/voting) — evita que el
                # inspector de red delate al impostor antes de tiempo. Una
                # vez que la partida terminó (revealing), esa protección ya
                # no tiene ningún propósito: es precisamente el momento en
                # que el juego DEBE revelar quién era quién, o el desenlace
                # (sobre todo una victoria del impostor sin ser descubierto)
                # nunca llega a conocerse.
                if room.status == "revealing":
                    safe_players[pid]["role"] = p.role

            # 2. Determinar qué ve ESTE jugador específico
            your_word = None
            your_hint = None
            current_category_name = None
            
            if room.status == "playing":
                if room.show_category and room.current_topic:
                    current_category_name = room.current_topic.name
                    
                if is_imposter:
                    if room.use_hints and room.current_word:
                        your_hint = room.current_word.hint
                else:
                    if room.current_word:
                        your_word = room.current_word.name

            # 3. Construir el payload final seguro (RoomView)
            view = {
                "action": "room_update",
                "payload": {
                    "id": room.id,
                    "status": room.status,
                    "round_number": room.round_number,
                    "current_turn_index": room.current_turn_index,
                    "turn_order": room.turn_order,
                    "turn_deadline": room.turn_deadline,
                    "use_hints": room.use_hints,
                    "show_category": room.show_category,
                    "current_category": current_category_name,
                    "players": safe_players,
                    "your_role": viewer.role,
                    "your_word": your_word,
                    "your_hint": your_hint,
                    "tied_players": room.tied_players,
                    "last_submission": (
                        {
                            "player_id": room.last_submission.player_id,
                            "word": room.last_submission.word,
                            "timed_out": room.last_submission.timed_out,
                            "sequence": room.last_submission.sequence,
                        }
                        if room.last_submission
                        else None
                    ),
                }
            }
            
            # En la Fase final (revealing), agregamos la información de victoria
            if room.status == "revealing":
                winner = game_service.check_win_condition(room)
                view["payload"]["winner"] = winner
                view["payload"]["round_log"] = [
                    {
                        "round_number": log.round_number,
                        "words": {
                            pid: {"value": entry.value, "timed_out": entry.timed_out}
                            for pid, entry in log.words_spoken.items()
                        },
                        "eliminated_id": log.eliminated_id,
                        "was_double_tie": log.was_double_tie,
                    }
                    for log in room.game_history
                ]
            
            try:
                await websocket.send_json(view)
            except Exception:
                pass

manager = ConnectionManager()
message_adapter = TypeAdapter(ClientMessage)


async def handle_turn_timeout(room_id: str, round_number: int, turn_index: int) -> None:
    """
    Invocado por `redis_client.subscribe_to_turn_timeouts` cuando expira una
    clave `room:{room_id}:timeout:{round_number}:{turn_index}`. Compite por
    el mismo cerrojo distribuido que cualquier `send_word` entrante —
    `resolve_turn_timeout` compara `round_number`/`turn_index` contra el
    turno actual de la sala y no hace nada si ya no coinciden (turno ya
    resuelto por una acción legítima del jugador).
    """
    worker_uuid = str(uuid.uuid4())
    if not await acquire_lock_with_retry(room_id, worker_uuid):
        return

    try:
        state_json = await redis_client.get_room_state(room_id)
        if not state_json:
            return

        room = GameRoom.model_validate_json(state_json)
        new_status = game_service.resolve_turn_timeout(room, round_number, turn_index)

        if new_status is None:
            # La notificación llegó tarde (turno ya resuelto por otra vía);
            # no hay nada que mutar. El `finally` libera el cerrojo.
            return

        if new_status == "playing":
            await redis_client.set_turn_timeout(room_id, room.round_number, room.current_turn_index, 20)

        saved = await redis_client.release_lock_and_update(room_id, worker_uuid, room.model_dump_json())
        if saved:
            await manager.broadcast_room_view(room)
    finally:
        await redis_client.release_lock(room_id, worker_uuid)

@router.websocket("/ws/room/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket)
    room_id = room_id.upper()
    current_token = None
    should_close_after = False

    try:
        while True:
            data = await websocket.receive_text()
            
            # Prevención de Flood
            if manager.check_rate_limit(websocket):
                await websocket.close(code=4029, reason="Too Many Requests")
                break
                
            try:
                event = message_adapter.validate_json(data)
            except ValidationError:
                await manager.send_error(websocket, "INVALID_FORMAT", "Formato de evento inválido.")
                continue

            # --- PROCESAMIENTO CON CERROJO DISTRIBUIDO (FULL FENCING) ---
            # Adquirimos el cerrojo antes de leer el estado para evitar condiciones de carrera[cite: 2]
            worker_uuid = str(uuid.uuid4())
            if not await acquire_lock_with_retry(room_id, worker_uuid):
                # Tras varios reintentos, la sala sigue bloqueada. Para la
                # mayoría de las acciones esto no es una carrera legítima
                # esperada (esa solo existe entre send_word y el timeout de
                # turno) — es más probable que indique contención anómala.
                # Se avisa explícitamente en vez de dejar el botón del
                # cliente sin ninguna respuesta visible.
                await manager.send_error(
                    websocket,
                    "SERVER_BUSY",
                    "El servidor está ocupado procesando otra acción. Intenta de nuevo.",
                )
                continue
                
            try:
                state_json = await redis_client.get_room_state(room_id)
                if not state_json:
                    await websocket.close(code=4004, reason="Room Not Found")
                    break
                    
                room = GameRoom.model_validate_json(state_json)
                room_mutated = False

                # --- ROUTER DE EVENTOS ---
                
                if event.action == "join_room":
                    payload = event.payload
                    
                    player = None
                    if payload.secret_token:
                        player = next((p for p in room.players.values() if p.secret_token == payload.secret_token), None)

                    if player:
                        # Política Last-One-Wins: Si el token ya tiene un socket en esta misma réplica, cerramos el antiguo.
                        if room_id in manager.active_connections and player.secret_token in manager.active_connections[room_id]:
                            old_socket = manager.active_connections[room_id][player.secret_token]
                            if old_socket != websocket:
                                await old_socket.close(code=4009, reason="Session Duplicated")
                        
                        player.is_online = True
                        room_mutated = True
                    else:
                        # --- JUGADOR NUEVO ---
                        if room.status != "waiting":
                            await websocket.close(code=4003, reason="Game In Progress")
                            break

                        if len(room.players) >= MAX_PLAYERS_PER_ROOM:
                            await websocket.close(code=4006, reason="Room Full")
                            break

                        is_host = len(room.players) == 0
                        player = Player(name=payload.player_name, is_host=is_host)
                        room.players[player.id] = player
                        
                        # Registro de antigüedad para Migración de Host (Sección 3.3)[cite: 2]
                        await redis_client.client.zadd(f"room:{{{room_id}}}:join_order", {player.id: time.time()})
                        room_mutated = True

                    # Actualizamos nuestros diccionarios locales (Zero-Trust)
                    current_token = player.secret_token
                    manager.socket_to_token[websocket] = current_token
                    if room_id not in manager.active_connections:
                        manager.active_connections[room_id] = {}
                    manager.active_connections[room_id][current_token] = websocket

                    # Enviamos el token secreto y el ID de forma privada
                    await websocket.send_json({
                        "action": "joined_successfully",
                        "payload": {
                            "player_id": player.id,
                            "secret_token": player.secret_token
                        }
                    })

                elif event.action == "send_word":
                    # Autorización Zero-Trust: Resolvemos el remitente por su token asociado al socket[cite: 3].
                    token = manager.socket_to_token.get(websocket)
                    player_id = next((p.id for p in room.players.values() if p.secret_token == token), None)
                    
                    if not player_id or room.status != "playing":
                        await manager.send_error(websocket, "INVALID_PHASE", "Acción no permitida en esta fase.")
                        continue

                    if not room.players[player_id].is_alive:
                        await manager.send_error(websocket, "INVALID_PHASE", "Un jugador eliminado no puede enviar palabras.")
                        continue

                    if room.turn_order[room.current_turn_index] != player_id:
                        await manager.send_error(websocket, "NOT_YOUR_TURN", "No es tu turno.")
                        continue

                    # Lógica de juego delegada al servicio
                    game_service.record_player_word(room, player_id, event.payload.word)
                    room.status = game_service.advance_turn(room)
                    
                    if room.status == "playing":
                        await redis_client.set_turn_timeout(room_id, room.round_number, room.current_turn_index, 20)
                        
                    room_mutated = True
                    
                elif event.action == "start_game":
                    token = manager.socket_to_token.get(websocket)
                    sender = next((p for p in room.players.values() if p.secret_token == token), None)

                    if not sender or not sender.is_host:
                        await manager.send_error(websocket, "UNAUTHORIZED_ACTION", "Solo el Host puede iniciar la partida.")
                        continue

                    if room.status != "waiting":
                        await manager.send_error(websocket, "INVALID_PHASE", "La partida ya ha comenzado.")
                        continue

                    payload = event.payload
                    topic = routes.find_topic_by_id(payload.topic_id)
                    if not topic:
                        await manager.send_error(websocket, "TOPIC_NOT_FOUND", "La temática seleccionada no existe en el catálogo.")
                        continue

                    room.use_hints = payload.use_hints
                    room.show_category = payload.show_category
                    room.anonymous_voting = payload.anonymous_voting
                    room.imposters_count = payload.imposters_count

                    success, error_code, message = game_service.start_game(room, topic)
                    if not success:
                        await manager.send_error(websocket, error_code, message)
                        continue

                    await redis_client.set_turn_timeout(room_id, room.round_number, room.current_turn_index, 20)
                    room_mutated = True

                elif event.action == "vote":
                    token = manager.socket_to_token.get(websocket)
                    voter_id = next((p.id for p in room.players.values() if p.secret_token == token), None)

                    if not voter_id or room.status != "voting":
                        await manager.send_error(websocket, "INVALID_PHASE", "Acción no permitida en esta fase.")
                        continue

                    if not room.players[voter_id].is_alive:
                        await manager.send_error(websocket, "INVALID_PHASE", "Un jugador eliminado no puede votar.")
                        continue

                    target_id = event.payload.target_id
                    target = room.players.get(target_id)

                    if not target or not target.is_alive:
                        await manager.send_error(websocket, "INVALID_TARGET", "El jugador votado no existe o no está vivo.")
                        continue

                    if room.tied_players and target_id not in room.tied_players:
                        await manager.send_error(websocket, "INVALID_TARGET", "En el desempate solo puedes votar por los jugadores empatados.")
                        continue

                    # Se permite sobrescribir el voto propio mientras la ronda
                    # de votación siga abierta (cambiar de opinión antes de
                    # que todos hayan votado).
                    room.votes[voter_id] = target_id
                    room_mutated = True

                    alive_count = len(room.alive_players)
                    if len(room.votes) >= alive_count:
                        game_service.resolve_voting(room)
                        # resolve_voting ya deja room.status en "playing"
                        # (ronda nueva o doble empate), "voting" (primer
                        # empate) o "revealing" (fin de partida) según
                        # corresponda.
                        if room.status == "playing":
                            await redis_client.set_turn_timeout(room_id, room.round_number, room.current_turn_index, 20)

                elif event.action == "next_round":
                    # Interpretación: reinicia una nueva partida (revancha)
                    # dentro de la misma sala tras el resumen final. El caso
                    # de doble empate ya se resuelve automáticamente dentro
                    # de `resolve_voting` sin esperar este evento — si la
                    # intención original era otra, este es el punto a ajustar.
                    token = manager.socket_to_token.get(websocket)
                    sender = next((p for p in room.players.values() if p.secret_token == token), None)

                    if not sender or not sender.is_host:
                        await manager.send_error(websocket, "UNAUTHORIZED_ACTION", "Solo el Host puede iniciar una nueva partida.")
                        continue

                    if room.status != "revealing":
                        await manager.send_error(websocket, "INVALID_PHASE", "Solo se puede reiniciar la partida tras el resumen final.")
                        continue

                    for p in room.players.values():
                        p.is_alive = True
                        p.role = None
                        # `score` se preserva intencionalmente entre partidas
                        # de una misma sala (01_game_design.md, sección 7.1).

                    room.status = "waiting"
                    room.round_number = 0
                    room.current_topic = None
                    room.current_word = None
                    room.imposter_ids = []
                    room.current_round_log = None
                    room.game_history = []
                    room.turn_order = []
                    room.current_turn_index = 0
                    room.turn_deadline = None
                    room.votes = {}
                    room.tied_players = []

                    room_mutated = True

                elif event.action == "leave_room":
                    token = manager.socket_to_token.get(websocket)
                    player = next((p for p in room.players.values() if p.secret_token == token), None)

                    if player:
                        was_host = player.is_host

                        if room.status == "waiting":
                            # Aún no hay roles ni turnos que desenrollar:
                            # abandonar el lobby es simplemente dejar de
                            # estar en la lista de jugadores.
                            del room.players[player.id]
                            await redis_client.client.zrem(f"room:{{{room_id}}}:join_order", player.id)
                        else:
                            # "Salida Definitiva": eliminación inmediata
                            # (01_game_design.md, sección 6).
                            player.is_alive = False
                            player.is_online = False

                            if (room.status == "playing" and room.turn_order
                                    and room.current_turn_index < len(room.turn_order)
                                    and room.turn_order[room.current_turn_index] == player.id):
                                room.status = game_service.advance_turn(room)
                                if room.status == "playing":
                                    await redis_client.set_turn_timeout(room_id, room.round_number, room.current_turn_index, 20)

                            if room.status in ("playing", "voting"):
                                winner = game_service.check_win_condition(room)
                                if winner:
                                    game_service.calculate_and_apply_scores(room)
                                    room.status = "revealing"

                        if was_host:
                            await game_service.handle_host_migration(room, redis_client)

                        room_mutated = True

                    # Limpieza local inmediata: quien envía leave_room no
                    # debe seguir recibiendo el broadcast que esta misma
                    # mutación va a disparar para el resto de la sala.
                    await manager.disconnect(websocket, room_id)
                    current_token = None
                    should_close_after = True

                # -----------------------------------------------------------
                # FENCING: Solo escribimos si el cerrojo sigue siendo nuestro
                if room_mutated:
                    new_state = room.model_dump_json()
                    saved = await redis_client.release_lock_and_update(room_id, worker_uuid, new_state)
                    
                    # Si guardamos con éxito, transmitimos el estado
                    if saved:
                        # En Fase 5 esto se enviaría a Redis Streams (XADD)
                        # Por ahora en Fase 1 (1 nodo), lo emitimos localmente:
                        await manager.broadcast_room_view(room)

                if should_close_after:
                    await websocket.close(code=1000, reason="Left room")
                    break

            finally:
                # Única salida del cerrojo, y tiene que ser un `finally`: los
                # rechazos de validación (`continue`), los cierres del socket
                # (`break`) y las excepciones salían todos de la sección
                # crítica sin soltarlo, dejándolo retenido hasta agotar su PX
                # de 5 s. En esa ventana el timeout de turno no lograba
                # adquirirlo, se rendía en silencio, y como su clave TTL ya
                # había expirado el turno se quedaba sin reloj para siempre.
                #
                # Es idempotente: si `release_lock_and_update` ya borró el
                # cerrojo, o si expiró y lo tiene otro worker, no hace nada.
                await redis_client.release_lock(room_id, worker_uuid)

    except WebSocketDisconnect:
        await manager.disconnect(websocket, room_id)

        if current_token:
            # Si otra conexión (ej. una reconexión que cerró este socket vía
            # Last-One-Wins, código 4009) ya tomó este secret_token, esta
            # desconexión es la del socket VIEJO — no se debe marcar
            # is_online=False, o se sobrescribiría el estado "en línea" que
            # la conexión nueva ya estableció.
            if manager.has_active_connection(room_id, current_token):
                return

            # Flujo de desconexión: marcar como offline (Protegido por Lock).
            # IMPORTANTE: una desconexión simple (refresh, corte de red breve)
            # NUNCA dispara migración de Host aquí — el GDD (sección 6) exige
            # que un refresh mantenga "su lugar, su rol y su estado vital".
            # Disparar la migración desde este mismo manejador además entra en
            # una carrera real con el join_room de la reconexión, causando
            # comportamiento no determinista (a veces migra, a veces no).
            # La migración por ausencia real del Host se resuelve aparte, con
            # un período de gracia (ver schedule_host_migration_if_still_offline).
            worker_uuid = str(uuid.uuid4())
            if await acquire_lock_with_retry(room_id, worker_uuid):
                try:
                    state_json = await redis_client.get_room_state(room_id)
                    if state_json:
                        room = GameRoom.model_validate_json(state_json)
                        player = next((p for p in room.players.values() if p.secret_token == current_token), None)
                        if player:
                            was_host = player.is_host
                            player.is_online = False

                            saved = await redis_client.release_lock_and_update(room_id, worker_uuid, room.model_dump_json())
                            if saved:
                                await manager.broadcast_room_view(room)

                            if was_host:
                                asyncio.create_task(
                                    schedule_host_migration_if_still_offline(room_id, current_token)
                                )
                finally:
                    pass