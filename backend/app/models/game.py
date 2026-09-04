from pydantic import BaseModel, Field
from typing import List, Dict, Literal, Optional
import uuid


# --- 1. MODELO DE LA PALABRA ---
class Word(BaseModel):
    name: str
    hint: Optional[str] = None

# --- 2. MODELO DE LA TEMÁTICA ---
class Topic(BaseModel):
    # Genera un ID único automáticamente para poder registrarlo en el historial
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    words: List[Word]
    is_official: bool = False

# --- 3. MODELO DEL JUGADOR ---
class Player(BaseModel):
    # ID persistente
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    # Token privado
    secret_token: str = Field(default_factory=lambda: str(uuid.uuid4())) 
    # ID temporal del WebSocket actual (cambia si el usuario pierde conexión y vuelve)
    connection_id: Optional[str] = None 
    
    name: str
    is_online: bool = True
    is_host: bool = False
    score: int = 0
    
    # Estado del jugador durante la partida
    is_alive: bool = True
    role: Optional[Literal["innocent", "impostor"]] = None

# --- 4. MODELO DEL HISTORIAL DE LA SALA---
class WordEntry(BaseModel):
    """
    Registro de la palabra de un jugador en una ronda. `timed_out=True`
    únicamente puede ser producido por el servidor (listener de expiración
    de TTL) — nunca por un payload de `send_word` del cliente, incluso si
    el cliente envía literalmente el texto "TIEMPO_AGOTADO" como su palabra.
    """
    value: str
    timed_out: bool = False

class RoundLog(BaseModel):
    round_number: int
    words_spoken: Dict[str, WordEntry] = {}  # Llave: ID del jugador
    eliminated_id: Optional[str] = None
    was_double_tie: bool = False

class LastSubmission(BaseModel):
    """
    La palabra que el último jugador dijo en su turno (o su penalización
    por tiempo agotado). A diferencia del rol, esto NUNCA es información
    secreta — en el juego presencial todos escuchan la palabra de cada
    turno en voz alta, así que se transmite a todos sin restricción,
    incluso mientras `status == "playing"`.

    `sequence` es un contador incremental (no un timestamp) para que el
    frontend detecte de forma inequívoca una submission NUEVA, incluso si
    por coincidencia el mismo jugador dice la misma palabra en dos turnos
    distintos — evita depender de sincronización de reloj.
    """
    player_id: str
    word: str
    timed_out: bool
    sequence: int

# --- 5. MODELO DE LA SALA ---
class GameRoom(BaseModel):
    id: str  # Código de 4 letras (ej. "XYZW")
    players: Dict[str, Player] = {} 
    status: Literal["waiting", "playing", "voting", "revealing"] = "waiting" 
    
    # Configuraciones de la partida (Elegidas por el host)
    use_hints: bool = True
    show_category: bool = True
    anonymous_voting: bool = False
    imposters_count: int = 1  # Cantidad seleccionada antes de iniciar
    
    # Estado de la ronda actual
    round_number: int = 0
    current_topic: Optional[Topic] = None
    current_word: Optional[Word] = None
    imposter_ids: List[str] = []
    
    # Lógica de historial
    current_round_log: Optional[RoundLog] = None # Lo que se está construyendo en la ronda actual
    game_history: List[RoundLog] = []  # El registro final para mostrar al terminar el juego

    # Última palabra dicha (o timeout) — ver LastSubmission arriba.
    last_submission: Optional[LastSubmission] = None

    # Sistema de turnos
    turn_order: List[str] = []  # Lista de IDs de jugadores mezclada aleatoriamente
    current_turn_index: int = 0 # Índice para saber a quién le toca enviar su palabra
    # El timestamp en el que se acaba el turno actual
    turn_deadline: Optional[float] = None

    # Bandera atómica para evitar condiciones de carrera en el timeout
    is_current_turn_resolved: bool = False
    
    # Sistema de votaciones
    # Diccionario donde la llave es el ID del votante y el valor el ID del acusado
    votes: Dict[str, str] = {} 

    # IDs de los jugadores empatados en la votación anterior
    tied_players: List[str] = Field(default_factory=list)
    
    # Historial para evitar palabras repetidas
    # Llave: ID del tópico -> Valor: Lista de nombres de palabras ya jugadas
    used_words_history: Dict[str, List[str]] = {}

    @property
    def alive_players(self) -> List[Player]:
        """Devuelve solo los jugadores que siguen vivos en la ronda actual."""
        return [p for p in self.players.values() if p.is_alive]