# Hoja de Ruta y Fases de Desarrollo (Roadmap)

Este documento establece el plan de ejecución iterativo para la construcción y evolución de la aplicación web "El Impostor". Su propósito es guiar el desarrollo de manera secuencial, asegurando que cada fase entregue un incremento de software funcional sobre una base técnica sólida y escalable.

---

## Fase 1: Infraestructura Base y MVP Funcional

**Objetivo:** Establecer un entorno de producción contenerizado definitivo (Docker/VPS) y desplegar un Producto Mínimo Viable (MVP) completamente jugable con temáticas predefinidas y sincronización en tiempo real.

> **Estado de implementación:** el código de backend (modelos, servicio de juego, WebSocket con cerrojo distribuido, listener de timeouts, las seis acciones de cliente) y las cuatro pantallas de frontend (`room-lobby`, `game-turns`, `voting`, `reveal`) más las dos páginas de Next.js (`page.tsx`, `room/[roomId]/page.tsx`) ya están escritos y compilando/probando en verde (pytest en el backend, `tsc --noEmit` en el frontend). Lo que sigue pendiente de esta fase es la parte de **DevOps e Infraestructura** de abajo (VPS, Docker Compose, Caddy, CI/CD) y una pasada de humo real jugando una partida completa con el backend y el frontend corriendo juntos — algo que ninguna prueba automatizada actual cubre todavía (ver `07_testing_and_qa_strategy.md`, sección 2.3, pendiente hasta este punto).

### DevOps e Infraestructura

- **Aprovisionamiento del Servidor:** Configurar una instancia virtual de cómputo (arquitectura ARM64) en Oracle Cloud.
- **Orquestación Local y de Producción:** Definir los servicios de la aplicación mediante Docker Compose, garantizando paridad entre el entorno de desarrollo y el de producción.
- **Proxy Inverso y SSL:** Implementar Caddy como punto de entrada de red para automatizar la emisión y renovación de certificados TLS (`https://` y `wss://`).
- **Compilación Multi-Etapa:** Configurar archivos de Dockerfile optimizados para la arquitectura de destino (ARM64).

### Backend (FastAPI)

- **Persistencia del Estado Temporal:** Implementar un nodo de Redis como Única Fuente de Verdad (SSOT) para almacenar el estado activo de las salas.
- **Configuración de Persistencia de Redis:** Habilitar el modo de persistencia AOF (_Append Only File_) en el servicio de Redis.
- **Conexión en Tiempo Real:** Desarrollar el _endpoint_ de conexión persistente mediante WebSockets para el intercambio de eventos bidireccionales.
- **Transmisión de Vistas Seguras:** Codificar el algoritmo de serialización y filtrado de datos para transmitir estados personalizados (`RoomView`) según el rol del destinatario.
- **Temporizadores Autoritativos:** Implementar la lógica de expiración de turnos mediante claves de Redis con tiempo de vida limitado (TTL) y notificaciones _keyspace_.
- **Cerrojo Distribuido con Fencing:** Implementar el mecanismo de exclusión mutua (`SET NX` + _fencing token_ vía Script Lua) que resuelve la competencia entre el temporizador de turno y las acciones del jugador. Esta pieza **no es exclusiva de un escenario multi-instancia**: incluso con un único proceso de FastAPI corriendo, el temporizador (disparado por Redis) y la acción del jugador (recibida por el mismo _event loop_ de `asyncio`) pueden competir por mutar el mismo estado, por lo que el cerrojo es una dependencia dura del MVP jugable, no una optimización futura.

### Frontend (Next.js)

- **Despliegue Estático:** Alojar la interfaz de usuario en Vercel, conectándola directamente al dominio del backend en el VPS.
- **Estructura de Vistas Core:** Construir la interfaz de usuario reactiva dividida en: Lobby de espera, Panel de configuración del anfitrión, Pantalla de ingreso de palabras y Tablero de votación.
- **Preservación de Identidad:** Implementar la persistencia del token de seguridad del jugador en el almacenamiento local del navegador (`localStorage`) para soportar reconexiones automáticas.

---

## Fase 2: Personalización de Reglas e Historial

**Objetivo:** Otorgar control granular al anfitrión sobre las mecánicas de la ronda y proveer un registro detallado de las jugadas para incentivar la interacción social post-partida.

### Backend (FastAPI)

- **Inyección de Datos Dinámicos:** Modificar los esquemas de la sala para aceptar temáticas y vocabularios personalizados proporcionados por los usuarios.
- **Métricas de Fin de Partida:** Implementar el algoritmo autoritativo para calcular y asignar el puntaje efímero de sala según el rol y las rondas sobrevivientes de cada jugador (ver `01_game_design.md`, sección 7.1).

### Frontend (Next.js)

- **Panel de Configuración Avanzado:** Implementar controles interactivos (toggles) en la interfaz del anfitrión para activar/desactivar pistas, ocultar la categoría temática y habilitar el voto anónimo.
- **Formularios Dinámicos:** Diseñar la interfaz de creación manual de temáticas, palabras clave y pistas de ayuda.
- **Resumen de Partida (Log de Rondas):** Construir la pantalla de visualización del historial de rondas, mostrando las palabras enviadas y el registro de eliminaciones al concluir la partida.

---

## Fase 3: Automatización de Contenido por Inteligencia Artificial

**Objetivo:** Mitigar el desgaste del catálogo de juego integrando generación automática de temáticas y palabras a través de un modelo de lenguaje.

### Backend (FastAPI)

- **Consumo del Servicio de IA:** Diseñar el cliente asíncrono para interactuar con la API del modelo de lenguaje (Gemini / OpenAI).
- **Control de Formato Estricto:** Implementar un sistema de _prompts_ que obligue al modelo de IA a devolver una estructura compatible con los esquemas de Pydantic.
- **Control de Consumo y Tasa:** Configurar un middleware de límites de petición (Rate Limiting) por dirección IP o identificador de sala para evitar abusos del servicio.

### Frontend (Next.js)

- **Panel de Curación Previa:** Crear una pantalla de revisión técnica ("Spoiler Warning") para que el anfitrión apruebe, edite o regenere la temática creada por la IA antes de iniciar la partida.

---

## Fase 4: Persistencia a Largo Plazo y Cuentas de Usuario

**Objetivo:** Transformar la aplicación de un juego de sesión efímera a una plataforma persistente con cuentas de usuario e historiales.

### Capa de Datos (Supabase)

- **Migración del Catálogo:** Reemplazar el archivo local de temáticas por una base de datos relacional PostgreSQL en Supabase.
- **Autenticación de Usuarios:** Integrar el servicio de autenticación de Supabase (OAuth y correo electrónico).

### Características del Sistema

- **Repositorio de Temáticas Creadas:** Habilitar a los usuarios registrados la opción de almacenar de forma permanente sus temáticas creadas manualmente o generadas por IA.
- **Estadísticas de Perfil (Victorias por Rol):** Registrar, exclusivamente para jugadores con sesión iniciada y en el instante del `revealing` de cada partida, un conteo acumulado de `victorias_como_inocente` y `victorias_como_impostor`. No se persiste el puntaje efímero de sala (`score`) ni ninguna métrica derivada adicional — ver `01_game_design.md`, sección 7.2, para la especificación completa de esta regla.

---

## Fase 5: Escalamiento Horizontal Pragmático

**Objetivo:** Adaptar el backend de FastAPI para soportar múltiples instancias concurrentes, eliminando dependencias de un único proceso.

### Backend / Arquitectura Distribuida

- **Diseño de API Stateless:** Asegurar que las instancias del backend de FastAPI no almacenen estado local de red ni de negocio, haciéndolas completamente intercambiables.
- **Sincronización por Registro de Eventos entre Instancias:** Migrar la propagación de eventos entre réplicas utilizando Redis Streams, con un Grupo de Consumidores independiente por instancia (ver `02_architecture.md`, sección 4.1) — a diferencia del cerrojo de la Fase 1 (que ya resuelve la concurrencia dentro de un solo proceso), esto resuelve específicamente que un evento generado en la Instancia A llegue a los sockets conectados en la Instancia B.
- **Rehidratación Transparente:** Programar la re-asociación dinámica de sockets al estado almacenado en Redis durante los flujos de reconexión del cliente, sin depender de afinidad de sesión (_sticky sessions_) en el balanceador.

---

## Fase 6: Visión a Futuro (North Star Architecture)

**Objetivo:** Definir la topología de infraestructura empresarial ideal ante escenarios de alta concurrencia masiva y tolerancia total a fallos. _(Nota: Esta fase está fuera del alcance del proyecto actual y se detalla exclusivamente como referencia técnica futura)._

### Orquestación de Contenedores y Red

- **Clúster de Kubernetes:** Migrar de Docker Compose a un clúster gestionado de Kubernetes (ej. Oracle OKE) para la administración y autoescalado dinámico de réplicas de FastAPI.
- **Métricas de Escalado Personalizadas:** Configurar el escalado automático de _pods_ (HPA) utilizando métricas de conexiones WebSocket activas y uso de memoria mediante KEDA o adaptadores similares, en lugar de métricas de CPU.
- **Balanceo de Carga en la Nube:** Desplegar un balanceador de carga gestionado para la terminación SSL avanzada y la distribución de tráfico de alta concurrencia.

### Capa de Almacenamiento Distribuida

- **Clúster de Redis de Alta Disponibilidad:** Migrar a una topología de Redis Sentinel para automatizar el proceso de recuperación ante fallos del nodo maestro.
- **Particionamiento Horizontal de Datos:** Configurar Redis Cluster para distribuir el estado de las salas activas entre múltiples fragmentos (_shards_) si la demanda excede la capacidad de memoria de un único servidor físico.
