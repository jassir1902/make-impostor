# Arquitectura Técnica y Flujo de Datos

Este documento describe la arquitectura técnica del Juego del Impostor, detallando la separación de responsabilidades, el paradigma de servidores sin estado (stateless) y la gestión de concurrencia y persistencia utilizando Redis como Única Fuente de Verdad.

## 1. Visión General

El proyecto sigue una arquitectura distribuida Cliente-Servidor-Caché:

- **Frontend (Cliente):** Aplicación web estática construida con Next.js y React, encargada exclusivamente de la renderización reactiva de la interfaz de usuario y la transmisión de eventos al servidor a través de WebSockets.
- **Backend (FastAPI):** Nivel de aplicación _stateless_ (sin estado local). Instancias fungibles responsables de validar contratos, aplicar las reglas de negocio y orquestar eventos.
- **Capa de Datos (Redis):** Actúa como la Única Fuente de Verdad (SSOT) del juego. Administra el estado estructurado de las salas, el bus de eventos en tiempo real y el control de concurrencia.

## 2. Estructura de Directorios del Backend

El backend adopta un patrón de diseño guiado por el dominio (DDD - Domain-Driven Design) adaptado para una arquitectura distribuida:

- `app/api/`: Controladores de red.
  - `routes.py`: Endpoints REST estáticos (ej. inicialización de salas, generación de temáticas vía IA).
  - `websockets.py`: Gestor de conexiones persistentes y enrutador de mensajes entrantes.
- `app/core/`:
  - `redis_client.py`: Módulo de conexión y abstracción hacia Redis. Administra los _streams_, notificaciones _keyspace_ y ejecución de _scripts_ Lua.
- `app/models/`: Contratos de datos estrictos usando Pydantic.
  - `game.py`: Modelos principales (`GameRoom`, `Player`, `Topic`, `RoundLog`). Serializables directamente a JSON para su almacenamiento.
  - `events.py`: Esquemas de validación para los _payloads_ entrantes (del cliente) y salientes (_RoomView_).
- `app/services/`: Lógica de negocio pura.
  - `game_service.py`: Lógica transaccional que lee desde Redis, calcula nuevos estados (empates, victorias, avances de turno) y reescribe la entidad a la base de datos aplicando _fencing tokens_.

## 3. Gestión del Estado y Persistencia (Redis)

Todo el estado en vivo de las partidas reside exclusivamente en Redis, erradicando el uso de diccionarios en la memoria RAM de Python. Esto garantiza la intercambiabilidad de los _workers_ de FastAPI.

### 3.1 Nomenclatura de Claves y _Hash Tags_

Para garantizar compatibilidad futura con particionamiento horizontal (_Redis Cluster_), todas las claves asociadas a una misma sala comparten un _Hash Tag_ (el código de la sala entre llaves `{}`). Esto fuerza que todas las estructuras de la sala residan en el mismo nodo físico:

- **Estado:** `room:{ABCD}:state` (JSON serializado de la entidad `GameRoom`).
- **Eventos:** `room:{ABCD}:stream` (Registro _append-only_ de cambios).
- **Reloj:** `room:{ABCD}:timeout` (Clave efímera con TTL).
- **Cerrojo:** `room:{ABCD}:lock` (Exclusión mutua).
- **Orden de Ingreso:** `room:{ABCD}:join_order` (Sorted Set — ver sección 3.3).

### 3.2 Creación Atómica y Ciclo de Vida de la Sala

- La sala nace exclusivamente a través del endpoint `POST /api/rooms`. El backend genera un código único (ej. `ABCD`) y ejecuta una creación atómica directa mediante el comando `SET room:{ABCD}:state <JSON> NX`. Si el comando devuelve `False` por una colisión, se reintenta con otro código. Se prohíbe explícitamente el uso del antipatrón _check-then-act_ (`EXISTS` seguido de `SET`).
- **Persistencia:** El contenedor de Redis se ejecuta con la política AOF (_Append Only File_) configurada en `everysec`. Esto mitiga la volatilidad de la memoria RAM garantizando que, ante un fallo crítico de infraestructura, la pérdida máxima de información sea de 1 segundo.

### 3.3 Autoridad de Migración de Host (Orden de Ingreso)

La regla de negocio (`01_game_design.md`, sección 6) exige que, al desconectarse el Host, el privilegio pase al jugador **más antiguo** que siga conectado. Esta antigüedad no puede inferirse de la memoria local de la instancia que procesa la desconexión — un cálculo por-instancia podría promover a un jugador que en realidad solo está conectado (con estado válido) a otro _worker_, o ignorar a uno realmente más antiguo simplemente porque su socket vive en otro proceso.

Para resolverlo, `room:{ABCD}:join_order` es un **Sorted Set** de Redis donde cada miembro es el `player_id` y el _score_ es el timestamp Unix del primer `join_room` exitoso de ese jugador en la sala (no se actualiza en reconexiones posteriores). Al procesar una desconexión definitiva del Host, el `game_service.py` consulta este Sorted Set filtrando únicamente los `player_id` cuyo estado en `room:{ABCD}:state` marque `is_online: true`, y promueve al de menor _score_ (el de ingreso más antiguo) entre esos. Esta consulta y la escritura del nuevo `is_host` se protegen bajo el mismo cerrojo distribuido de la sección 4.3, para evitar que dos desconexiones casi simultáneas (ej. el Host y el segundo más antiguo cayendo en el mismo instante) produzcan una migración inconsistente.

## 4. Comunicación en Tiempo Real y Concurrencia

### 4.1 Bus de Eventos Bidireccional (Redis Streams)

La comunicación entre distintas réplicas de FastAPI se realiza mediante **Redis Streams**.

- **Regla estricta de Consumo (Broadcast):** Para garantizar que todos los _workers_ reciban todos los eventos, cada instancia de FastAPI **debe** leer el _stream_ de la sala utilizando un puntero `XREAD` independiente o un Grupo de Consumidores único (nombrado con el UUID o _hostname_ del contenedor). Está estrictamente prohibido utilizar un único Grupo de Consumidores compartido entre instancias, ya que esto provocaría balanceo de carga de eventos (pérdida silenciosa de _broadcast_).

### 4.2 Autoridad del Tiempo (TTL y Keyspace Notifications)

Al iniciar un turno, el _worker_ activo crea la clave `room:{ABCD}:timeout` con un TTL de 20 segundos. Al expirar, Redis dispara una notificación global.

- **Dependencia de Infraestructura:** Este mecanismo requiere que Redis inicie obligatoriamente con el parámetro de configuración `notify-keyspace-events Ex`. Sin esta configuración explícita en `redis.conf`, los eventos de tiempo agotado caducarán silenciosamente y la partida quedará bloqueada.

### 4.3 Control de Concurrencia (Cerrojo con Fencing Total)

Para prevenir condiciones de carrera (múltiples _workers_ intentando resolver un tiempo agotado o una votación simultáneamente), se implementa un **Cerrojo Distribuido** utilizando un _Fencing Token_:

1.  **Adquisición:** El _worker_ ejecuta `SET room:{ABCD}:lock <Worker-UUID> NX PX 5000`. Si obtiene `True`, retiene el `<Worker-UUID>` como su _fencing token_.
2.  **Protección de Escritura y Liberación (Full Fencing):** Si la lógica de negocio requiere mutar la sala, la escritura del nuevo estado y la eliminación del cerrojo se realizan atómicamente mediante un **Script Lua**. El script verifica que el valor actual en `room:{ABCD}:lock` sea estrictamente igual al `<Worker-UUID>`. Si coincide, ejecuta el `SET room:{ABCD}:state <Nuevo-JSON>` y el `DEL room:{ABCD}:lock`. Si no coincide (el lock expiró por latencia del _worker_ y fue adquirido por otro), la transacción se aborta silenciosamente, impidiendo que el _worker_ rezagado sobrescriba la base de datos con información obsoleta.
3.  **Límite de Sección Crítica:** El tiempo máximo de retención del cerrojo es de 5 segundos. Por regla de arquitectura, queda **estrictamente prohibido** ejecutar operaciones de I/O externo bloqueantes (como peticiones a la API del LLM de la Fase 3) dentro de la sección crítica protegida por este cerrojo.

## 5. Resiliencia, Reconexión y Rehidratación

El sistema está diseñado para tolerar caídas de red del cliente, actualizaciones de página y cambios de instancia de backend sin pérdida de progreso.

### 5.1 Separación de Identidad

- **Identidad Persistente (`secret_token`):** Un UUID estricto generado por el backend al unirse. El frontend lo almacena en `localStorage`.
- **Identidad de Red (`connection_id`):** El descriptor de archivo del socket actual.

### 5.2 Flujo de Rehidratación Transparente

El sistema no requiere _Sticky Sessions_ (afinidad de sesión TCP) a nivel de balanceador de carga.

1.  Si la conexión cae, el jugador reconecta y puede aterrizar en cualquier _worker_ disponible.
2.  El frontend emite el evento `join_room` incluyendo su `secret_token` en el _onopen_ del socket.
3.  El _worker_ valida el token, extrae un _snapshot_ desde `room:{ABCD}:state`, y transmite el `RoomView` consolidado al cliente (_Rehidratación instantánea_).
4.  El _worker_ se suscribe dinámicamente a `room:{ABCD}:stream` desde ese instante exacto para enrutar los eventos en vivo subsecuentes al nuevo socket.

## 6. Política de Seguridad: Autorización por Estados

El acceso y modificación de datos se gobierna por tres barreras:

1.  **Validación Contractual:** Pydantic rechaza esquemas malformados en los _payloads_ entrantes.
2.  **Validación de Máquina de Estados:** La capa de servicio intercepta intenciones según la fase del juego:
    - Un `send_word` se rechaza si `status != "playing"` o si el remitente no es el turno activo.
    - Votos son bloqueados fuera de la fase `"voting"`.
    - **Desempates:** En fases de empate, el array `tied_players` restringe los identificadores válidos para recibir votos.
3.  **Exposición Condicional del Rol:** `broadcast_room_view` omite el campo `role` de cada jugador en `players` mientras `status` sea `waiting`, `playing` o `voting` — es la protección central de Zero-Trust que evita que el impostor se delate por el inspector de red. Esa misma función lo **incluye** explícitamente en cuanto `status == "revealing"`: en ese punto la partida ya terminó y ocultarlo no protege nada — al contrario, es el momento en que el juego debe revelar quién era quién (ver `03_api_and_events.md`, sección 4.3).

## 7. Referencia de Arquitectura Objetivo (North Star)

_Este apartado describe la evolución técnica planeada fuera del alcance del proyecto base._

A escala masiva, la arquitectura evolucionará hacia:

- **Alta Disponibilidad de Datos:** Migración a **Redis Cluster** para fragmentar el espacio de las salas (aprovechando los _Hash Tags_ base), combinado con **Redis Sentinel** para tolerancia a fallos.
- **Orquestación Dinámica:** Despliegue de FastAPI en **Kubernetes**, implementando autoescalado horizontal (HPA) fundamentado en métricas de memoria y WebSockets concurrentes (KEDA), superando los límites de un nodo VPS estático.
