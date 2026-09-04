# API y Eventos (Contratos de Comunicación)

Este documento detalla las interfaces de comunicación entre el frontend (Next.js) y el backend (FastAPI). Se divide en rutas estáticas REST y eventos en tiempo real mediante WebSockets.

## 1. Endpoints REST (HTTP)

Estas rutas se utilizan para consultas previas a la conexión del juego o interacciones puntuales.

### 1.0 Crear una nueva sala

- **Método:** `POST`
- **Ruta:** `/api/rooms`
- **Body:** Ninguno.
- **Respuesta Exitosa:** `{"room_id": "X7K2"}`
- **Respuesta Fallida:** `500` si el servidor agota los reintentos de generación de código.

**Nota de implementación atómica:** La creación de la sala en Redis debe ejecutarse como una operación atómica de escritura condicional (`SET room:{CODIGO}:state <JSON> NX`). Queda estrictamente prohibido utilizar un patrón _check-then-act_ (`EXISTS` seguido de `SET`) para evitar que peticiones concurrentes colisionen.

### 1.1 Verificar si una sala existe

- **Método:** `GET`
- **Ruta:** `/api/rooms/{room_id}/exists`
- **Respuesta Exitosa:** `{"exists": true, "status": "waiting", "players_count": 4}`
- **Respuesta Fallida:** `{"exists": false}`

### 1.2 Obtener catálogo oficial

- **Método:** `GET`
- **Ruta:** `/api/topics/official`
- **Respuesta:** Array de objetos `Topic` (JSON).

### 1.3 Generar temática con IA (Fase 3)

- **Método:** `POST`
- **Ruta:** `/api/topics/generate`
- **Body:** `{"prompt": "Personajes de Los Simpsons..."}`
- **Respuesta:** Objeto `Topic` generado por el LLM.

### 1.4 Verificación de Salud (Health Check)

- **Método:** `GET`
- **Ruta:** `/api/health`
- **Respuesta Exitosa:** `{"status": "ok", "redis": "connected"}`
- **Respuesta Fallida:** `503` si la conexión hacia Redis no puede establecerse o responde con error.

Ruta consumida por el monitor de infraestructura (Uptime Kuma, ver `06_devops_and_ci_cd.md`, sección 5). No requiere autenticación ni pertenece a ninguna sala específica — es un chequeo global de disponibilidad del backend y su dependencia crítica (Redis).

---

## 2. Conexión WebSocket

- **Ruta base:** `wss://<dominio-backend>/ws/room/{room_id}`
- **Comportamiento general:** Todos los mensajes bidireccionales (Cliente a Servidor y Servidor a Cliente) son un JSON estricto estructurado obligatoriamente con las llaves `action` y `payload`.

### 2.1 Modelo de Autorización: Identidad por Conexión (Zero-Trust)

Ningún `payload` enviado por el cliente contiene el `player_id`. La identidad del remitente (`send_word`, `vote`, `start_game`, etc.) se resuelve **exclusivamente** a partir del `secret_token` validado durante el `join_room` de esa conexión. El backend mantiene, por socket activo, una referencia al jugador autenticado.

### 2.2 Prevención de Flood (Rate Limiting por Conexión)

Para proteger el rendimiento del nodo Redis (SPOF) frente a ataques de denegación de servicio (DoS) o _bugs_ del cliente, el backend implementa un limitador de tasa a nivel de socket (ej. máximo 5 mensajes por segundo). Si un cliente excede este límite, el servidor cerrará el socket con el código `4029 (Too Many Requests)`.

### 2.3 Política de Conexiones Duplicadas (Last-One-Wins)

Si el servidor recibe un evento `join_room` con un `secret_token` que ya posee un socket activo en la misma sala, se aplicará una política de "el último gana". El servidor enviará un mensaje de error al socket antiguo y lo cerrará inmediatamente con el código `4009 (Session Duplicated)` antes de autorizar y enrutar eventos a la nueva conexión. Esto previene acciones duplicadas y ataques de suplantación.

---

## 3. Eventos del Cliente al Servidor (Client Messages)

### 3.1 Unirse a la sala (`join_room`)

Enviado **inmediatamente después de abrir la conexión WebSocket** (en la conexión inicial y en **cada reconexión**).

```json
{
  "action": "join_room",
  "payload": {
    "room_id": "ABCD",
    "player_name": "Jassir",
    "secret_token": "token-secreto-opcional"
  }
}
```

**Respuesta Exitosa (Privada):**

```json
{
  "action": "joined_successfully",
  "payload": {
    "player_id": "uuid-publico",
    "secret_token": "uuid-privado-ultra-secreto"
  }
}
```

Tras esto, el servidor emite el `room_update` consolidado para rehidratar al cliente.

**Casos de rechazo y Códigos de Cierre (Close Codes):**

- Sala inexistente o destruida: Se cierra el socket con **Código `4004` (Room Not Found)**.
- Sala en curso y jugador nuevo: Se cierra el socket con **Código `4003` (Game In Progress)**.
- Sala llena: Se cierra el socket con **Código `4006` (Room Full)**.

**Obligación del Cliente ante Cierres (Inhibición de Reconexión):**
El frontend tiene la obligación contractual de tratar cualquier código de cierre `>= 4000` (incluyendo `4009` y `4029`) como **terminal**. No debe intentar reconectarse automáticamente ante estos códigos, ya que son expulsiones deliberadas de la aplicación. Solo las desconexiones de bajo nivel (ej. código `1006`) son elegibles para la reconexión con _backoff_.

### 3.2 Iniciar Juego (`start_game`)

```json
{
  "action": "start_game",
  "payload": {
    "topic_id": "topic_simpsons",
    "imposters_count": 1,
    "use_hints": true,
    "show_category": true,
    "anonymous_voting": false
  }
}
```

**Autorización:** Solo si el remitente es Host y la sala está en `waiting`.

### 3.3 Enviar Palabra (`send_word`)

```json
{
  "action": "send_word",
  "payload": {
    "word": "Cerveza Duff"
  }
}
```

**Autorización:** Solo si la sala está en `playing` y el remitente corresponde al `current_turn_index`.

### 3.4 Emitir Voto (`vote`)

```json
{
  "action": "vote",
  "payload": {
    "target_id": "uuid-del-jugador-acusado"
  }
}
```

**Autorización:** Solo si la sala está en `voting` y el jugador está vivo. En caso de desempate, el `target_id` debe existir dentro del arreglo `tied_players`.

### 3.5 Jugar de Nuevo (`next_round`) & Abandonar Sala (`leave_room`)

```json
{"action": "next_round", "payload": null}
{"action": "leave_room", "payload": null}
```

**`next_round` — Semántica fijada durante la implementación:** la Regla del Doble Empate (GDD, sección 5) se resuelve por completo dentro de `resolve_voting`, en el mismo instante en que llega el último voto — la ronda avanza automáticamente sin esperar ninguna acción del Host. Por lo tanto, `next_round` **no** se usa para ese caso. Su único uso real es como disparador de revancha: enviado por el Host cuando `status == "revealing"`, reinicia la sala a `status: "waiting"` con los mismos jugadores (roles limpiados, `is_alive` restaurado a `true` para todos), preservando el `score` efímero acumulado (01_game_design.md, sección 7.1 — el puntaje vive atado al ciclo de vida de la _sala_, no de una partida individual, así que una revancha en la misma sala continúa sumando).

**Autorización:** Solo si el remitente es Host y la sala está en `revealing`. Fuera de esas condiciones, el servidor rechaza con `UNAUTHORIZED_ACTION` o `INVALID_PHASE` según corresponda.

**`leave_room`:** siempre procesable por el remitente sobre sí mismo. Si la sala está en `waiting`, simplemente sale del lobby (se elimina de `players`). En cualquier otro estado es una eliminación inmediata (GDD, sección 6): se salta su turno si era el suyo, se evalúa la condición de victoria de inmediato, y si era el Host se dispara la migración automática (`02_architecture.md`, sección 3.3).

---

## 4. Eventos del Servidor al Cliente (Server Messages)

### 4.1 Broadcast de Estado Personalizado (room_update)

Serialización segura y filtrada del estado actual, emitida por el servidor ante cualquier cambio.

```json
{
  "action": "room_update",
  "payload": {
    "id": "ABCD",
    "status": "playing",
    "round_number": 1,
    "current_turn_index": 0,
    "turn_order": ["uuid-1", "uuid-2"],
    "turn_deadline": 1720549231.5,
    "use_hints": true,
    "show_category": true,
    "current_category": "Personajes de Los Simpsons",
    "players": { ... },
    "your_role": "innocent",
    "your_word": "Homero",
    "your_hint": null,
    "tied_players": []
  }
}
```

**`your_role`:** `"innocent"` o `"impostor"`. Corresponde al rol "Inocente" definido en `01_game_design.md`, sección 2.

**`turn_deadline`:** Timestamp Unix. Su uso en el cliente es **estrictamente visual** para renderizar la cuenta regresiva.

### 4.2 Notificación de Error (Taxonomía Estricta)

Todo rechazo que no implique el cierre del socket se notifica con un evento `error`.

```json
{
  "action": "error",
  "payload": {
    "code": "INVALID_IMPOSTERS_COUNT",
    "message": "El número de impostores debe ser 1 o 2."
  }
}
```

**Enum de Códigos de Error (Lista Cerrada):**

- `NOT_YOUR_TURN`: Remitente intentó enviar palabra fuera de su turno.
- `INVALID_PHASE`: Acción intentada en un estado de sala incompatible.
- `UNAUTHORIZED_ACTION`: Jugador no es Host.
- `INVALID_IMPOSTERS_COUNT`: Cantidad matemática inválida.
- `INVALID_TARGET`: Jugador votado no está vivo o no pertenece a `tied_players`.
- `TOPIC_NOT_FOUND`: Temática enviada no existe en el catálogo.

### 4.3 Cierre de Partida y Resumen (`status: "revealing"`)

Cuando la partida finaliza, el servidor emite el último `room_update` con campos extra en el `payload`:

```json
{
  "action": "room_update",
  "payload": {
    "id": "ABCD",
    "status": "revealing",
    "winner": "innocents",
    "round_log": [
      {
        "round_number": 1,
        "words": {
          "uuid-1": { "value": "Homero", "timed_out": false },
          "uuid-2": { "value": "TIEMPO_AGOTADO", "timed_out": true }
        },
        "eliminated_id": "uuid-2",
        "was_double_tie": false
      }
    ],
    "players": {
      "uuid-1": {
        "id": "uuid-1",
        "name": "Jassir",
        "is_online": true,
        "is_host": true,
        "is_alive": true,
        "score": 300,
        "role": "innocent"
      }
    },
    "your_role": "innocent",
    "your_word": "Homero",
    "your_hint": null,
    "tied_players": []
  }
}
```

**`winner`:** `"innocents"` o `"impostors"`.

**`players[].role`:** único campo de `players` que aparece condicionalmente — **solo** cuando `status === "revealing"`. Mientras la partida está en `playing`/`voting`/`waiting`, el servidor lo omite deliberadamente por Zero-Trust (no delatar al impostor vía el inspector de red). Una vez terminada la partida esa protección ya no tiene ningún propósito — es precisamente el momento en que el juego debe revelar quién era quién, o un desenlace donde el impostor gana sin ser descubierto nunca llegaría a conocerse. Ver `02_architecture.md`, sección 6.

**Protección del Garbage Collector:** Las salas en estado `revealing` quedan exentas del TTL convencional de inactividad, garantizando la disponibilidad del resumen post-partida y el debate social (ej. gracia de 15 minutos).

**Nota sobre estadísticas persistentes:** Si el jugador tiene una sesión de usuario iniciada al momento de este `revealing`, el servidor registra de forma asíncrona un incremento a sus victorias por rol (`victorias_como_inocente` o `victorias_como_impostor`) en la base de datos persistente — ver `01_game_design.md`, sección 7.2. Este registro no forma parte del `payload` de este evento ni bloquea su emisión; es un efecto secundario del lado del servidor, invisible para el contrato de red.
