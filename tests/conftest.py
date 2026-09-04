import pytest

from app.models.game import GameRoom, Player, Topic, Word


@pytest.fixture
def make_room():
    """
    Builder de GameRoom con N jugadores ya insertados (sin roles ni turno
    asignado todavía). Cada test decide desde ahí qué estado adicional
    necesita — evita repetir la construcción de jugadores en cada caso.
    """

    def _make(num_players: int = 3, host_index: int = 0) -> tuple[GameRoom, list[str]]:
        room = GameRoom(id="TEST")
        for i in range(num_players):
            player = Player(name=f"Jugador{i}")
            room.players[player.id] = player

        player_ids = list(room.players.keys())
        room.players[player_ids[host_index]].is_host = True

        return room, player_ids

    return _make


@pytest.fixture
def sample_topic() -> Topic:
    return Topic(
        name="Animales",
        is_official=True,
        words=[
            Word(name="Perro", hint="Mamífero doméstico"),
            Word(name="Gato", hint="Felino doméstico"),
            Word(name="Loro", hint="Ave que habla"),
        ],
    )
