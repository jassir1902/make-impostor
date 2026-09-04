import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importamos los routers que creamos en los pasos anteriores
from app.api import routes
from app.api import websockets
from app.core import redis_client

app = FastAPI(
    title="Imposter Game API",
    description="Backend en tiempo real para el juego del Impostor",
    version="1.0.0"
)

# --- CONFIGURACIÓN DE CORS ---
# NUNCA combinar "*" con orígenes explícitos + allow_credentials=True: el
# wildcard hace irrelevantes los orígenes específicos, y esa combinación es
# justamente la que rompe cuando la Fase 4 agregue autenticación (Supabase)
# basada en cookies o credenciales. La lista de producción se controla vía
# variable de entorno para no tener que tocar código en cada despliegue.
_extra_origins = os.getenv("CORS_EXTRA_ORIGINS", "")
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
] + [origin.strip() for origin in _extra_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTRO DE RUTAS ---
app.include_router(routes.router)
app.include_router(websockets.router)


@app.on_event("startup")
async def start_background_services():
    """
    Habilita las notificaciones keyspace de Redis y arranca, como tarea de
    fondo, el listener que resuelve los timeouts de turno (ver
    `02_architecture.md`, sección 4.2). Sin esto, los TTL de turno expiran
    en Redis sin que nadie reaccione y las partidas quedan congeladas.
    """
    await redis_client.ensure_keyspace_notifications_enabled()
    asyncio.create_task(
        redis_client.subscribe_to_turn_timeouts(websockets.handle_turn_timeout)
    )

# --- ENDPOINT DE SALUD (Health Check) ---
# Muy útil para que Render sepa que tu servidor arrancó correctamente
@app.get("/")
async def root():
    return {
        "status": "online",
        "message": "Servidor del Juego del Impostor activo y funcionando. 🚀"
    }