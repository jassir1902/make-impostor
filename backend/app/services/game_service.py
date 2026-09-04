import random
import math
import time
from typing import Dict, List, Optional, Tuple

from app.models.game import GameRoom, Topic, Player, RoundLog, WordEntry, LastSubmission


def _first_alive_turn_index(room: GameRoom) -> int:
    """
    Encuentra el primer índice de `turn_order` cuyo jugador sigue vivo.
    Necesario porque `turn_order` nunca se filtra ni se reordena tras una
    eliminación: sin esto, una ronda nueva podría empezar apuntando a un
    jugador ya eliminado en la ronda anterior, dejando la partida esperando
    indefinidamente un turno que nunca podrá completarse.
    """
    for index, player_id in enumerate(room.turn_order):
        if room.players[player_id].is_alive:
            return index
    return 0  # Defensivo: no debería alcanzarse si check_win_condition ya se evaluó.

def get_max_imposters(num_players: int) -> int:
    """Calcula el máximo de impostores permitidos según la regla matemática[cite: 1]."""
    return math.floor((num_players - 1) / 2)

def start_game(room: GameRoom, topic: Topic) -> Tuple[bool, Optional[str], str]:
    """
    Retorna (éxito, código_de_error, mensaje). `código_de_error` es None si
    `éxito` es True; en caso contrario es uno de los códigos del enum
    cerrado definido en `03_api_and_events.md`, sección 4.2.
    """
    num_players = len(room.players)

    if num_players < 3:
        return False, "INVALID_PHASE", "Se requieren al menos 3 jugadores para iniciar la partida."

    # El servidor es la autoridad absoluta en la validación matemática[cite: 1].
    max_imposters = get_max_imposters(num_players)
    if room.imposters_count > max_imposters or room.imposters_count < 1:
        return False, "INVALID_IMPOSTERS_COUNT", f"Número de impostores inválido. Máximo permitido: {max_imposters}."

    # 1. RESETEO TOTAL DE JUGADORES
    for player in room.players.values():
        player.role = "innocent"
        player.is_alive = True
    
    # 2. SELECCIÓN DE PALABRA (Filtro Histórico)
    if topic.id not in room.used_words_history:
        room.used_words_history[topic.id] = []
    
    used_words = room.used_words_history[topic.id]
    available_words = [w for w in topic.words if w.name not in used_words]
    
    # Agotamiento del catálogo: Reinicio automático del filtro[cite: 1].
    if not available_words:
        room.used_words_history[topic.id] = []
        available_words = topic.words 
    
    room.current_topic = topic
    room.current_word = random.choice(available_words)
    room.used_words_history[topic.id].append(room.current_word.name)

    # 3. ASIGNACIÓN DE ROLES Y ORDEN
    player_ids = list(room.players.keys())
    room.imposter_ids = random.sample(player_ids, room.imposters_count)
    for imp_id in room.imposter_ids:
        room.players[imp_id].role = "impostor"

    random.shuffle(player_ids)
    room.turn_order = player_ids
    room.current_turn_index = 0
    
    # 4. RESETEO DE RONDA E HISTORIAL
    room.round_number = 1
    room.game_history = []
    room.current_round_log = RoundLog(round_number=room.round_number)
    room.votes = {}
    room.tied_players = []
    room.status = "playing"

    # Turn deadline será establecido por el router tras guardar el lock[cite: 2]
    room.turn_deadline = time.time() + 20.0 

    return True, None, "Juego iniciado correctamente."

def record_player_word(room: GameRoom, player_id: str, typed_word: str, timed_out: bool = False):
    """
    Registra la palabra en el historial de la ronda y actualiza
    `last_submission` — lo que dispara el aviso transitorio a todos los
    jugadores ("Jassir dijo: 'Perro'"), ya que en el juego presencial esa
    palabra se dice en voz alta y no es información secreta.

    `timed_out` solo debe pasarse como True desde el listener de expiración
    del servidor (ver `resolve_turn_timeout` más abajo) — nunca a partir de
    un valor que el cliente haya incluido en su payload de `send_word`.
    Esto evita que un jugador declare su propio "TIEMPO_AGOTADO" y lo haga
    pasar como una penalización automática del servidor en el resumen final.
    """
    if room.current_round_log:
        room.current_round_log.words_spoken[player_id] = WordEntry(value=typed_word, timed_out=timed_out)

    next_sequence = (room.last_submission.sequence + 1) if room.last_submission else 1
    room.last_submission = LastSubmission(
        player_id=player_id,
        word=typed_word,
        timed_out=timed_out,
        sequence=next_sequence,
    )

def resolve_turn_timeout(room: GameRoom, expected_round: int, expected_turn_index: int) -> Optional[str]:
    """
    Aplica la penalización de TIEMPO_AGOTADO al jugador cuyo turno expiró y
    avanza al siguiente. Debe invocarse únicamente desde el listener de
    notificaciones keyspace del servidor (nunca a partir de una acción de
    cliente), bajo el mismo cerrojo distribuido que protege `send_word`.

    `expected_round`/`expected_turn_index` deben ser los valores que el
    temporizador tenía armados en el momento en que se creó (ver
    `redis_client.set_turn_timeout`, que ahora codifica ambos en el nombre
    de la clave). Si al procesar la notificación el turno ACTUAL de la sala
    ya no coincide con esos valores, significa que esta notificación quedó
    obsoleta — el jugador ya envió su palabra y `send_word` ya ganó la
    carrera y avanzó el turno — y no debe aplicarse ninguna penalización.

    Comparar solo "¿el jugador actual ya tiene palabra registrada?" no es
    suficiente: si el turno ya avanzó, el jugador actual es uno distinto
    que aún no ha tenido oportunidad de actuar, y penalizarlo sería un
    falso positivo. Retorna el nuevo `room.status`, o None si la
    notificación resultó obsoleta.
    """
    if room.status != "playing" or not room.turn_order:
        return None

    if room.round_number != expected_round or room.current_turn_index != expected_turn_index:
        return None

    current_player_id = room.turn_order[room.current_turn_index]
    record_player_word(room, current_player_id, "TIEMPO_AGOTADO", timed_out=True)
    room.status = advance_turn(room)
    return room.status


def advance_turn(room: GameRoom) -> str:
    """
    Avanza el turno al siguiente jugador vivo.
    Retorna "playing" si la ronda sigue, o "voting" si todos han completado su turno[cite: 1].
    """
    room.current_turn_index += 1
    
    while room.current_turn_index < len(room.turn_order):
        next_player_id = room.turn_order[room.current_turn_index]
        if room.players[next_player_id].is_alive:
            room.turn_deadline = time.time() + 20.0
            return "playing"
        room.current_turn_index += 1
        
    # Fase de Escritura completada, pasamos a Fase de Votación
    room.status = "voting"
    room.turn_deadline = None
    return "voting"

def check_win_condition(room: GameRoom) -> Optional[str]:
    """
    Verifica las condiciones de victoria de la partida[cite: 1].
    Retorna "innocents", "impostors" o None si el juego continúa.
    """
    alive_players = room.alive_players
    alive_imposters = [p for p in alive_players if p.role == "impostor"]
    alive_civilians = [p for p in alive_players if p.role == "innocent"]

    if len(alive_imposters) == 0:
        return "innocents"
    elif len(alive_imposters) >= len(alive_civilians):
        return "impostors"
    
    return None

def resolve_voting(room: GameRoom) -> Dict:
    """
    Resuelve los votos y aplica la Regla del Primer o Doble Empate[cite: 1].
    """
    if not room.votes:
        return {"status": "error", "message": "No hay votos registrados."}
    
    is_revote = len(room.tied_players) > 0

    # Contar votos
    vote_counts: Dict[str, int] = {}
    for target_id in room.votes.values():
        vote_counts[target_id] = vote_counts.get(target_id, 0) + 1

    max_votes = max(vote_counts.values())
    tied_players = [pid for pid, count in vote_counts.items() if count == max_votes]
    room.votes = {}

    if len(tied_players) > 1:
        if not is_revote:
            # Regla del Primer Empate[cite: 1]
            room.tied_players = tied_players
            return {"status": "tie", "tied_players": tied_players}
        else:
            # Regla del Doble Empate: Nadie eliminado[cite: 1]
            room.tied_players = []  
            room.current_round_log.was_double_tie = True
            room.game_history.append(room.current_round_log)
            
            room.round_number += 1
            room.current_round_log = RoundLog(round_number=room.round_number)
            room.status = "playing"
            room.current_turn_index = _first_alive_turn_index(room)

            return {"status": "double_tie", "eliminated": None}

    # Resolución normal: Un solo eliminado
    room.tied_players = []
    eliminated_id = tied_players[0]
    room.players[eliminated_id].is_alive = False

    room.current_round_log.eliminated_id = eliminated_id
    room.game_history.append(room.current_round_log)
    
    winner = check_win_condition(room)
    if winner:
        calculate_and_apply_scores(room)
        room.status = "revealing"
        return {"status": "game_over", "winner": winner, "eliminated": eliminated_id}
    
    room.round_number += 1
    room.current_round_log = RoundLog(round_number=room.round_number)
    room.status = "playing"
    room.current_turn_index = _first_alive_turn_index(room)

    return {"status": "eliminated", "eliminated": eliminated_id}

def calculate_and_apply_scores(room: GameRoom):
    """
    Puntaje efímero de sala, calculado exclusivamente al finalizar (revealing).
    Inocente: +100 por ronda. Impostor: +200 por ronda[cite: 1].
    """
    total_rounds = room.round_number
    
    for player_id, player in room.players.items():
        if player.role is None:
            continue
            
        rounds_survived = 0

        if player.is_alive:
            rounds_survived = total_rounds
        else:
            elimination_found = False
            for log in room.game_history:
                if log.eliminated_id == player_id:
                    # Sobrevivió las rondas anteriores completas; fue
                    # eliminado durante la votación de esta ronda. Un valor
                    # de 0 aquí es legítimo (eliminado en la ronda 1) y no
                    # debe sustituirse por ningún otro cálculo.
                    rounds_survived = log.round_number - 1
                    elimination_found = True
                    break

            if not elimination_found:
                # Caso defensivo: el jugador está marcado como no vivo pero
                # no aparece en ningún RoundLog como eliminado (no debería
                # ocurrir en operación normal). No se le atribuyen puntos
                # por rondas que no está confirmado que sobrevivió.
                rounds_survived = 0

        points_earned = rounds_survived * 200 if player.role == "impostor" else rounds_survived * 100
        player.score += points_earned

async def handle_host_migration(room: GameRoom, redis_client_module) -> bool:
    """
    Transfiere los privilegios de Host al jugador más antiguo conectado en la sala,
    consultando el Sorted Set (join_order) en Redis[cite: 1, 2].

    Limpia explícitamente `is_host` de cualquier jugador que lo tuviera antes
    de promover — la función es responsable de esta invariante por sí misma
    (nunca hay más de un Host a la vez), sin depender de que cada llamador
    haya recordado limpiarlo de antemano.
    """
    for p in room.players.values():
        p.is_host = False

    # Consulta el Sorted Set ordenado por score (timestamp de ingreso)
    join_order = await redis_client_module.client.zrange(f"room:{{{room.id}}}:join_order", 0, -1)

    for player_id in join_order:
        # El jugador de menor score (más antiguo) que sigue online recibe el rol
        if player_id in room.players and room.players[player_id].is_online:
            room.players[player_id].is_host = True
            return True

    return False