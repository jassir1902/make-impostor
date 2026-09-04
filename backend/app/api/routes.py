from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import random

from app.models.game import Topic, GameRoom
from app.core import redis_client
from app.data.default_themes import load_default_topics

router = APIRouter()

# Lista global temporal para las temáticas "quemadas" (Fase 1 y 2)
local_topics_database = load_default_topics()


def find_topic_by_id(topic_id: str) -> Optional[Topic]:
    """
    Resuelve una temática por su id contra el catálogo actual. Usado tanto
    por este router como por el de WebSocket (`start_game`) para no
    duplicar el acceso al catálogo en dos lugares distintos.
    """
    return next((t for t in local_topics_database if t.id == topic_id), None)

# --- CONSTANTES DE GENERACIÓN DE CÓDIGOS ---
# Alfabeto restringido para evitar ambigüedades (O/0, I/1, etc.)
ROOM_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_ID_LENGTH = 4
MAX_GENERATION_ATTEMPTS = 10

# --- MODELOS DE ENTRADA REST ---
class IAGenerationRequest(BaseModel):
    prompt: str  # Ej: "Personajes de los simpsons, primeras 10 temporadas"

class CreateRoomResponse(BaseModel):
    room_id: str

# --- ENDPOINTS DE SALAS ---

@router.post("/api/rooms", response_model=CreateRoomResponse)
async def create_room():
    """
    Crea una nueva sala vacía y devuelve su código único.

    Este es el ÚNICO punto de entrada donde una sala nace.

    El frontend debe llamar a este endpoint ANTES de abrir la conexión
    WebSocket, y usar el room_id devuelto para conectarse.
    """
    for _ in range(MAX_GENERATION_ATTEMPTS):
        room_id = "".join(random.choices(ROOM_ID_ALPHABET, k=ROOM_ID_LENGTH))
        
        # La sala nace en estado "waiting", sin jugadores.
        # El primer jugador que haga join_room será designado Host.
        new_room = GameRoom(id=room_id)
        
        # Serializamos usando Pydantic v2
        state_json = new_room.model_dump_json()
        
        # Implementación atómica: SET NX en Redis[cite: 3].
        # Prohíbe explícitamente el uso del antipatrón check-then-act.
        success = await redis_client.create_room_atomic(room_id, state_json)
        
        if success:
            return CreateRoomResponse(room_id=room_id)

    # Señal real de agotamiento del espacio de códigos; no debería
    # pasar en operación normal, pero lo exponemos como 500 explícito
    # en vez de dejar que la excepción se propague sin contexto[cite: 8].
    raise HTTPException(
        status_code=500, 
        detail=f"No se pudo generar un código de sala único tras {MAX_GENERATION_ATTEMPTS} intentos. Espacio de códigos agotado."
    )

@router.get("/api/rooms/{room_id}/exists")
async def check_room_exists(room_id: str):
    """
    Permite al frontend (Next.js) verificar si un código de sala es válido
    antes de intentar conectar el WebSocket. Útil para mostrar errores 404 de sala[cite: 8].
    """
    room_id = room_id.upper()
    state_json = await redis_client.get_room_state(room_id)
    
    if state_json:
        # Rehidratamos el JSON para responder con el conteo de jugadores y el estado
        room = GameRoom.model_validate_json(state_json)
        return {
            "exists": True, 
            "status": room.status,
            "players_count": len(room.players)
        }
        
    return {"exists": False}

# --- ENDPOINT DE SALUD E INFRAESTRUCTURA ---

@router.get("/api/health")
async def health_check():
    """
    Ruta consumida por el monitor de infraestructura (Uptime Kuma, ver 06_devops_and_ci_cd.md).
    No requiere autenticación ni pertenece a ninguna sala específica — es un chequeo 
    global de disponibilidad del backend y su dependencia crítica (Redis)[cite: 3].
    """
    try:
        # Enviamos un ping a Redis para confirmar que la dependencia crítica está viva
        await redis_client.client.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503, 
            detail="Servicio no disponible: No se pudo establecer conexión con Redis."
        )

# --- ENDPOINTS DE TEMÁTICAS ---

@router.get("/api/topics/official", response_model=List[Topic])
async def get_official_topics():
    """
    Devuelve la lista de temáticas pre-aprobadas o 'quemadas' en el código.
    El host consumirá esto para poblar su menú desplegable de selección[cite: 8].
    """
    return [topic for topic in local_topics_database if topic.is_official]

@router.post("/api/topics/generate", response_model=Topic)
async def generate_topic_with_ai(request: IAGenerationRequest):
    """
    Endpoint para la Fase 3. 
    Recibirá el prompt del host, llamará a la API del LLM, validará que devuelva
    el JSON correcto (basado en el modelo Topic) y lo devolverá al frontend
    para su revisión manual (Spoiler Warning)[cite: 8].
    """
    raise HTTPException(
        status_code=501, 
        detail="La generación de temáticas por IA estará disponible en la Fase 3."
    )