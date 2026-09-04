import pytest

from app.models.game import RoundLog, WordEntry
from app.services import game_service


# --- get_max_imposters ---------------------------------------------------

class TestGetMaxImposters:
    @pytest.mark.parametrize(
        "num_players, expected_max",
        [(3, 1), (4, 1), (5, 2), (6, 2), (10, 4)],
    )
    def test_formula_floor_n_minus_1_over_2(self, num_players, expected_max):
        assert game_service.get_max_imposters(num_players) == expected_max


# --- start_game ------------------------------------------------------------

class TestStartGame:
    def test_rejects_fewer_than_three_players(self, make_room, sample_topic):
        room, _ = make_room(num_players=2)
        room.imposters_count = 1

        success, code, message = game_service.start_game(room, sample_topic)

        assert success is False
        assert code == "INVALID_PHASE"
        assert "3 jugadores" in message

    def test_rejects_imposters_count_above_max(self, make_room, sample_topic):
        room, _ = make_room(num_players=3)
        room.imposters_count = 2  # máximo permitido para 3 jugadores es 1

        success, code, message = game_service.start_game(room, sample_topic)

        assert success is False
        assert code == "INVALID_IMPOSTERS_COUNT"

    def test_rejects_imposters_count_below_one(self, make_room, sample_topic):
        room, _ = make_room(num_players=4)
        room.imposters_count = 0

        success, code, message = game_service.start_game(room, sample_topic)

        assert success is False
        assert code == "INVALID_IMPOSTERS_COUNT"

    def test_successful_start_assigns_roles_and_turn_order(self, make_room, sample_topic):
        room, player_ids = make_room(num_players=4)
        room.imposters_count = 1

        success, code, message = game_service.start_game(room, sample_topic)

        assert success is True
        assert code is None
        assert room.status == "playing"
        assert room.round_number == 1
        assert len(room.turn_order) == 4
        assert set(room.turn_order) == set(player_ids)
        assert len(room.imposter_ids) == 1

        impostors = [p for p in room.players.values() if p.role == "impostor"]
        innocents = [p for p in room.players.values() if p.role == "innocent"]
        assert len(impostors) == 1
        assert len(innocents) == 3

    def test_server_authority_ignores_client_supplied_count_out_of_range(self, make_room, sample_topic):
        """
        El servidor nunca confía ciegamente en imposters_count del cliente
        (01_game_design.md, sección 4) — este test fija ese contrato.
        """
        room, _ = make_room(num_players=3)
        room.imposters_count = 99  # valor deliberadamente absurdo

        success, code, _ = game_service.start_game(room, sample_topic)

        assert success is False
        assert code == "INVALID_IMPOSTERS_COUNT"
        assert room.status == "waiting"  # la sala no debe haber mutado


# --- advance_turn ------------------------------------------------------------

class TestAdvanceTurn:
    def test_skips_dead_players_and_stays_in_playing(self, make_room):
        room, player_ids = make_room(num_players=4)
        room.turn_order = player_ids
        room.current_turn_index = 0
        room.players[player_ids[1]].is_alive = False  # el siguiente en turno está muerto

        new_status = game_service.advance_turn(room)

        assert new_status == "playing"
        assert room.current_turn_index == 2  # saltó al índice 1 (muerto) hasta el 2

    def test_transitions_to_voting_when_all_turns_completed(self, make_room):
        room, player_ids = make_room(num_players=3)
        room.turn_order = player_ids
        room.current_turn_index = len(player_ids) - 1  # último jugador de la ronda

        new_status = game_service.advance_turn(room)

        assert new_status == "voting"
        assert room.turn_deadline is None


# --- check_win_condition -----------------------------------------------------

class TestCheckWinCondition:
    def test_innocents_win_when_no_impostors_alive(self, make_room):
        room, player_ids = make_room(num_players=3)
        for pid in player_ids:
            room.players[pid].role = "innocent"

        assert game_service.check_win_condition(room) == "innocents"

    def test_impostors_win_when_tied_or_outnumbering(self, make_room):
        room, player_ids = make_room(num_players=2)
        room.players[player_ids[0]].role = "impostor"
        room.players[player_ids[1]].role = "innocent"

        assert game_service.check_win_condition(room) == "impostors"

    def test_game_continues_when_no_condition_met(self, make_room):
        room, player_ids = make_room(num_players=4)
        room.players[player_ids[0]].role = "impostor"
        for pid in player_ids[1:]:
            room.players[pid].role = "innocent"

        assert game_service.check_win_condition(room) is None


# --- resolve_voting -----------------------------------------------------------

class TestResolveVoting:
    def _start_voting(self, make_room, num_players=4):
        room, player_ids = make_room(num_players=num_players)
        room.turn_order = player_ids
        room.players[player_ids[0]].role = "impostor"
        for pid in player_ids[1:]:
            room.players[pid].role = "innocent"
        room.round_number = 1
        room.current_round_log = RoundLog(round_number=1)
        room.status = "voting"
        return room, player_ids

    def test_single_winner_is_eliminated(self, make_room):
        room, player_ids = self._start_voting(make_room)
        target = player_ids[1]
        for voter in player_ids:
            room.votes[voter] = target

        result = game_service.resolve_voting(room)

        assert result["status"] in ("eliminated", "game_over")
        assert room.players[target].is_alive is False
        assert room.game_history[-1].eliminated_id == target

    def test_first_tie_sets_tied_players_without_eliminating(self, make_room):
        room, player_ids = self._start_voting(make_room, num_players=4)
        # Empate 2-2 entre los dos primeros
        room.votes[player_ids[0]] = player_ids[2]
        room.votes[player_ids[1]] = player_ids[2]
        room.votes[player_ids[2]] = player_ids[3]
        room.votes[player_ids[3]] = player_ids[3]

        result = game_service.resolve_voting(room)

        assert result["status"] == "tie"
        assert set(result["tied_players"]) == {player_ids[2], player_ids[3]}
        assert room.tied_players == result["tied_players"]
        assert room.players[player_ids[2]].is_alive is True
        assert room.players[player_ids[3]].is_alive is True

    def test_double_tie_eliminates_no_one_and_advances_round(self, make_room):
        room, player_ids = self._start_voting(make_room, num_players=4)
        room.tied_players = [player_ids[2], player_ids[3]]  # ya veníamos de un primer empate

        room.votes[player_ids[0]] = player_ids[2]
        room.votes[player_ids[1]] = player_ids[2]
        room.votes[player_ids[2]] = player_ids[3]
        room.votes[player_ids[3]] = player_ids[3]

        result = game_service.resolve_voting(room)

        assert result["status"] == "double_tie"
        assert result["eliminated"] is None
        assert all(p.is_alive for p in room.players.values())
        assert room.status == "playing"
        assert room.round_number == 2
        assert room.tied_players == []

    def test_double_tie_advances_turn_to_first_alive_player(self, make_room):
        """
        Test de regresión: el índice de turno de la ronda nueva debe
        respetar al primer jugador VIVO, no asumir ciegamente el índice 0
        (ver hallazgo de la auditoría sobre _first_alive_turn_index).
        """
        room, player_ids = self._start_voting(make_room, num_players=3)
        room.players[player_ids[0]].is_alive = False  # turn_order[0] ya muerto de antes

        # Único empate real posible con 2 votantes vivos: 1 voto para cada uno.
        room.tied_players = [player_ids[1], player_ids[2]]  # veníamos de un primer empate
        room.votes = {
            player_ids[1]: player_ids[2],
            player_ids[2]: player_ids[1],
        }

        result = game_service.resolve_voting(room)

        assert result["status"] == "double_tie"
        first_turn_player = room.turn_order[room.current_turn_index]
        assert room.players[first_turn_player].is_alive is True

    def test_game_over_triggers_scoring_and_revealing_status(self, make_room):
        room, player_ids = self._start_voting(make_room, num_players=2)
        target = player_ids[1]  # el innocent, dejando 1 impostor vs 0 innocents
        room.votes = {player_ids[0]: target, player_ids[1]: target}

        result = game_service.resolve_voting(room)

        assert result["status"] == "game_over"
        assert room.status == "revealing"
        # calculate_and_apply_scores ya debió correr (ver test dedicado abajo
        # para el detalle de puntaje); aquí solo confirmamos que se disparó.
        assert room.players[player_ids[0]].score > 0


# --- calculate_and_apply_scores ----------------------------------------------

class TestCalculateAndApplyScores:
    def test_innocent_survivor_gets_100_per_round(self, make_room):
        room, player_ids = make_room(num_players=2)
        room.players[player_ids[0]].role = "innocent"
        room.players[player_ids[1]].role = "impostor"
        room.round_number = 3

        game_service.calculate_and_apply_scores(room)

        assert room.players[player_ids[0]].score == 300  # 100 * 3 rondas

    def test_impostor_survivor_gets_200_per_round(self, make_room):
        room, player_ids = make_room(num_players=2)
        room.players[player_ids[0]].role = "innocent"
        room.players[player_ids[1]].role = "impostor"
        room.round_number = 3

        game_service.calculate_and_apply_scores(room)

        assert room.players[player_ids[1]].score == 600  # 200 * 3 rondas

    def test_player_eliminated_in_round_one_gets_zero_points(self, make_room):
        """
        Test de regresión directo del bug de puntaje corregido en la
        auditoría: el fallback anterior le daba `total_rounds - 1` puntos
        a un jugador eliminado en la ronda 1, en vez de 0.
        """
        room, player_ids = make_room(num_players=3)
        eliminated_id = player_ids[0]
        room.players[eliminated_id].role = "innocent"
        room.players[eliminated_id].is_alive = False

        log_round_1 = RoundLog(round_number=1, eliminated_id=eliminated_id)
        room.game_history.append(log_round_1)
        room.round_number = 3  # la partida siguió varias rondas más

        game_service.calculate_and_apply_scores(room)

        assert room.players[eliminated_id].score == 0

    def test_player_eliminated_in_round_two_gets_one_round_of_points(self, make_room):
        room, player_ids = make_room(num_players=3)
        eliminated_id = player_ids[0]
        room.players[eliminated_id].role = "innocent"
        room.players[eliminated_id].is_alive = False

        room.game_history.append(RoundLog(round_number=1))
        room.game_history.append(RoundLog(round_number=2, eliminated_id=eliminated_id))
        room.round_number = 4

        game_service.calculate_and_apply_scores(room)

        assert room.players[eliminated_id].score == 100  # sobrevivió 1 ronda completa

    def test_missing_elimination_record_defaults_to_zero(self, make_room):
        """
        Caso defensivo: jugador marcado is_alive=False sin ningún RoundLog
        que lo mencione como eliminado. No debe inventarse puntaje.
        """
        room, player_ids = make_room(num_players=2)
        ghost_id = player_ids[0]
        room.players[ghost_id].role = "innocent"
        room.players[ghost_id].is_alive = False
        room.round_number = 5
        # Deliberadamente sin agregar ningún RoundLog a room.game_history

        game_service.calculate_and_apply_scores(room)

        assert room.players[ghost_id].score == 0


# --- record_player_word / resolve_turn_timeout -------------------------------

class TestTurnTimeout:
    def _room_mid_turn(self, make_room):
        room, player_ids = make_room(num_players=3)
        room.turn_order = player_ids
        room.current_turn_index = 0
        room.round_number = 1
        room.status = "playing"
        room.current_round_log = RoundLog(round_number=1)
        return room, player_ids

    def test_client_supplied_word_is_never_marked_timed_out(self, make_room):
        """
        Aunque el cliente envíe literalmente el texto "TIEMPO_AGOTADO" como
        su palabra, timed_out debe quedar en False — solo el listener de
        expiración del servidor puede producir timed_out=True.
        """
        room, player_ids = self._room_mid_turn(make_room)
        game_service.record_player_word(room, player_ids[0], "TIEMPO_AGOTADO")

        entry = room.current_round_log.words_spoken[player_ids[0]]
        assert entry.value == "TIEMPO_AGOTADO"
        assert entry.timed_out is False

    def test_resolve_turn_timeout_applies_penalty_when_stamp_matches(self, make_room):
        room, player_ids = self._room_mid_turn(make_room)

        new_status = game_service.resolve_turn_timeout(room, expected_round=1, expected_turn_index=0)

        assert new_status == "playing"
        entry = room.current_round_log.words_spoken[player_ids[0]]
        assert entry.timed_out is True
        assert room.current_turn_index == 1

    def test_stale_notification_does_not_penalize_the_new_current_player(self, make_room):
        """
        Test de regresión del hallazgo central: si el turno ya avanzó (el
        jugador ganó la carrera contra el timeout mediante `send_word`)
        antes de que la notificación de expiración se procese, esa
        notificación queda obsoleta — su `expected_round`/`expected_turn_index`
        ya no coinciden con el turno actual. Antes de esta corrección, el
        código solo comprobaba si el jugador ACTUAL ya tenía palabra
        registrada, lo cual es casi siempre falso para el jugador que
        recién empieza su turno, aplicándole una penalización indebida.
        """
        room, player_ids = self._room_mid_turn(make_room)

        # El jugador de turno 0 gana la carrera: envía su palabra y el
        # turno avanza a index 1 dentro de la MISMA ronda.
        game_service.record_player_word(room, player_ids[0], "Perro")
        room.status = game_service.advance_turn(room)
        assert room.current_turn_index == 1

        # La notificación de expiración llega tarde, con el sello del
        # turno ORIGINAL (ronda 1, índice 0) que ya quedó resuelto.
        result = game_service.resolve_turn_timeout(room, expected_round=1, expected_turn_index=0)

        assert result is None
        assert room.current_turn_index == 1  # no se tocó el turno del nuevo jugador
        assert player_ids[1] not in room.current_round_log.words_spoken  # sin penalización indebida

    def test_resolve_turn_timeout_is_noop_when_room_not_playing(self, make_room):
        room, player_ids = self._room_mid_turn(make_room)
        room.status = "voting"

        result = game_service.resolve_turn_timeout(room, expected_round=1, expected_turn_index=0)

        assert result is None


# --- last_submission ----------------------------------------------------------

class TestLastSubmission:
    """
    No es información secreta (a diferencia del rol): en el juego
    presencial todos escuchan la palabra de cada turno en voz alta, así
    que se transmite a todos por igual, sin restricción de rol.
    """

    def _room_mid_turn(self, make_room):
        room, player_ids = make_room(num_players=3)
        room.turn_order = player_ids
        room.current_turn_index = 0
        room.round_number = 1
        room.status = "playing"
        room.current_round_log = RoundLog(round_number=1)
        return room, player_ids

    def test_manual_submission_sets_last_submission(self, make_room):
        room, player_ids = self._room_mid_turn(make_room)

        game_service.record_player_word(room, player_ids[0], "Perro")

        assert room.last_submission is not None
        assert room.last_submission.player_id == player_ids[0]
        assert room.last_submission.word == "Perro"
        assert room.last_submission.timed_out is False
        assert room.last_submission.sequence == 1

    def test_timeout_submission_sets_last_submission_with_timed_out_true(self, make_room):
        room, player_ids = self._room_mid_turn(make_room)

        game_service.resolve_turn_timeout(room, expected_round=1, expected_turn_index=0)

        assert room.last_submission is not None
        assert room.last_submission.player_id == player_ids[0]
        assert room.last_submission.timed_out is True

    def test_sequence_increments_monotonically_across_submissions(self, make_room):
        room, player_ids = self._room_mid_turn(make_room)

        game_service.record_player_word(room, player_ids[0], "Perro")
        assert room.last_submission.sequence == 1

        game_service.advance_turn(room)
        game_service.record_player_word(room, player_ids[1], "Perro")  # misma palabra, otro jugador

        assert room.last_submission.sequence == 2
        assert room.last_submission.player_id == player_ids[1]


# --- handle_host_migration (async) -------------------------------------------

class FakeRedisModule:
    """Doble de prueba mínimo para redis_client, solo con lo que usa handle_host_migration."""

    class _FakeAsyncClient:
        def __init__(self, ordered_ids):
            self._ordered_ids = ordered_ids

        async def zrange(self, key, start, end):
            return self._ordered_ids

    def __init__(self, ordered_ids):
        self.client = self._FakeAsyncClient(ordered_ids)


class TestHandleHostMigration:
    @pytest.mark.asyncio
    async def test_promotes_oldest_online_player(self, make_room):
        room, player_ids = make_room(num_players=3)
        # El más antiguo (player_ids[0]) está offline; debe saltarse.
        room.players[player_ids[0]].is_online = False
        room.players[player_ids[1]].is_online = True
        room.players[player_ids[2]].is_online = True

        fake_redis = FakeRedisModule(ordered_ids=player_ids)  # orden de ingreso

        promoted = await game_service.handle_host_migration(room, fake_redis)

        assert promoted is True
        assert room.players[player_ids[1]].is_host is True
        assert room.players[player_ids[2]].is_host is False

    @pytest.mark.asyncio
    async def test_clears_previous_host_flag_even_if_caller_forgot_to(self, make_room):
        """
        Test de regresión: la función debe ser responsable por sí misma de
        que nunca haya más de un Host a la vez, sin depender de que el
        llamador ya haya limpiado el `is_host` del jugador saliente —
        justo el bug que se coló en uno de los dos sitios que la invocan.
        """
        room, player_ids = make_room(num_players=3, host_index=0)
        assert room.players[player_ids[0]].is_host is True  # el host original, sin limpiar

        room.players[player_ids[0]].is_online = False
        room.players[player_ids[1]].is_online = True
        room.players[player_ids[2]].is_online = True

        fake_redis = FakeRedisModule(ordered_ids=player_ids)
        await game_service.handle_host_migration(room, fake_redis)

        assert room.players[player_ids[0]].is_host is False
        assert sum(1 for p in room.players.values() if p.is_host) == 1

    @pytest.mark.asyncio
    async def test_returns_false_when_no_one_online(self, make_room):
        room, player_ids = make_room(num_players=2)
        for pid in player_ids:
            room.players[pid].is_online = False

        fake_redis = FakeRedisModule(ordered_ids=player_ids)

        promoted = await game_service.handle_host_migration(room, fake_redis)

        assert promoted is False
