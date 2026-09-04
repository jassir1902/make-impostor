from pydantic import BaseModel, Field
from typing import Literal, Union, Optional, Any

# --- PAYLOADS DE LOS EVENTOS DEL CLIENTE ---
class JoinRoomPayload(BaseModel):
    room_id: str
    player_name: str
    secret_token: Optional[str] = None

class StartGamePayload(BaseModel):
    topic_id: str
    imposters_count: int
    use_hints: bool
    show_category: bool
    anonymous_voting: bool

class SendWordPayload(BaseModel):
    word: str  # Puede ser "TIEMPO_AGOTADO" si el frontend manda el timeout

class VotePayload(BaseModel):
    target_id: str  # A quién acusa

# --- DEFINICIÓN DE LOS EVENTOS (Mensajes que entran al backend) ---
class JoinRoomEvent(BaseModel):
    action: Literal["join_room"]
    payload: JoinRoomPayload

class StartGameEvent(BaseModel):
    action: Literal["start_game"]
    payload: StartGamePayload

class SendWordEvent(BaseModel):
    action: Literal["send_word"]
    payload: SendWordPayload

class VoteEvent(BaseModel):
    action: Literal["vote"]
    payload: VotePayload

class NextRoundEvent(BaseModel):
    action: Literal["next_round"]
    payload: Optional[Any] = None

class LeaveRoomEvent(BaseModel):
    action: Literal["leave_room"]
    payload: Optional[Any] = None

# --- EL TIPO GLOBAL QUE ENGLOBA TODOS LOS MENSAJES ---
ClientMessage = Union[
    JoinRoomEvent, 
    StartGameEvent, 
    SendWordEvent, 
    VoteEvent, 
    NextRoundEvent,
    LeaveRoomEvent
]