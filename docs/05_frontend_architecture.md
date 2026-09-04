# Arquitectura del Frontend - El Impostor

Este documento detalla la estructura de directorios, la estrategia de gestión de estado y el ciclo de vida de la conexión en tiempo real dentro de la aplicación web construida con Next.js.

## 1. Estructura de Directorios (Feature-Sliced Design)

Para garantizar la mantenibilidad y escalabilidad del proyecto, el código se organiza por "dominios de negocio" (features) en lugar de por tipos de archivos técnicos:

```text
src/
  app/
    page.tsx                    # Landing: captura el nombre y crea/une una sala
    room/[roomId]/page.tsx      # Única ruta dinámica — gobierna por connectionStatus y luego por room.status; único punto de entrada de leave_room (chrome de página, no de una feature)

  features/                     # Dominios de negocio aislados
    room-lobby/
      components/ PlayerList.tsx, HostSettingsPanel.tsx, TopicSelector.tsx, LobbyScreen.tsx
      hooks/ useHostControls.ts

    game-turns/
      components/ TurnScreen.tsx, WordInput.tsx, TurnTimer.tsx
      hooks/ useTurnTimer.ts

    voting/
      components/ VotingScreen.tsx, VoteResults.tsx

    reveal/
      components/ RoundLogSummary.tsx, GameOverScreen.tsx

  components/ui/                 # Componentes atómicos, extraídos por duplicación real
    Card.tsx                     # Contenedor con borde — base de casi toda tarjeta de la app
    Button.tsx                   # Variantes primary/ghost
    Badge.tsx                    # Etiqueta; modo `stamped` para el sello diagonal (ej. "Host")
    Toggle.tsx                   # Switch on/off (extraído de HostSettingsPanel)

  styles/
    theme.css                    # Variables CSS de la paleta (--color-bg, --color-accent, etc.); se importa una vez desde el stylesheet global

  lib/
    api/
      rooms.ts                   # Cliente REST: createRoom(), checkRoomExists()
      topics.ts                  # Cliente REST: getOfficialTopics()
    socket/ RoomSocket.ts         # Clase singleton: transporte + handshake de identidad
    storage/
      playerIdentity.ts          # secret_token por sala (localStorage, blindado contra SSR)
      playerName.ts              # Nombre del jugador (localStorage, global, blindado contra SSR)

  hooks/
    useRoomConnection.ts          # Orquesta RoomSocket + Zustand + validación Zod

  context/
    SocketContext.tsx             # Provee la instancia de RoomSocket vía Context

  store/
    gameStore.ts                  # Estado global con Zustand: room, connectionStatus, lastError, rejection, myPlayerId

  types/
    game.ts                       # Esquemas Zod (entrantes y salientes) y tipos inferidos
```

## 2. Flujo de Creación y Unión a Sala

A diferencia de la conexión WebSocket, la creación y validación de salas se resuelve enteramente por HTTP antes de instanciar un socket:

- `lib/api/rooms.ts` expone `createRoom()` (`POST /api/rooms`) y `checkRoomExists()` (`GET /api/rooms/{id}/exists`).
- **Crear sala:** `page.tsx` llama a `createRoom()`, recibe el `room_id`, y navega a `room/[roomId]`.
- **Unirse a sala:** `page.tsx` llama a `checkRoomExists()` para dar feedback inmediato ante códigos inválidos.

## 3. Gestión de Estado (Zustand)

El estado global se sincroniza a través de la tienda `useGameStore` usando **Zustand**, descartando `React Context` para evitar re-renders masivos por el reloj autoritativo.

El campo `connectionStatus` (`'idle' | 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'rejected'`) es alimentado exclusivamente por el callback `onStatusChange` de `RoomSocket`. Ningún componente lo actualiza directamente.

El store también guarda `myPlayerId` — el `player_id` propio, recibido en `joined_successfully` y fijado vía `onIdentityConfirmed` en `useRoomConnection`. Sin este campo ningún componente puede saber cuál entrada de `room.players` es "yo" (para mostrar "Tú", o para derivar si soy el Host comparando `room.players[myPlayerId]?.is_host`).

## 4. Capa de Red (RoomSocket)

La conexión por WebSocket se administra mediante el patrón **Servicio Singleton** con una clase pura (`RoomSocket`) que opera fuera del ciclo de vida de React.

- **Evitar Conexiones Duplicadas:** Al estar referenciada por un hook, se evita que el _Strict Mode_ de React abra múltiples conexiones.
- **Resiliencia Restringida (Inhibición de Bucles):** La clase cuenta con una estrategia de reconexión automática (Backoff Exponencial con techo de 30s). **Regla estricta:** Solo los cierres de bajo nivel del navegador (código `< 4000`, como el `1006` por caída de red) activan la reconexión. Si el socket se cierra con un código de aplicación del servidor (`code >= 4000`), la reconexión automática **se inhibe completamente** y se transiciona al estado terminal `'rejected'` (ver sección 5.1).
- **Cola de Mensajes con Invalidación Exhaustiva:** Si un jugador envía un mensaje durante una desconexión momentánea, la clase almacena el payload. Al reconectar:
  - `leave_room` siempre es seguro de reproducir.
  - `vote` y `send_word` se marcan con el `round_number`, `status` y **la longitud del arreglo `tied_players`** vigentes al encolar. Si al recibir la rehidratación cualquiera de estas tres variables cambió, el mensaje se descarta silenciosamente. Esto evita que un voto dirigido a un jugador eliminado se envíe ciegamente durante un desempate.
- **Ciclo de Vida Explícito:** `RoomSocket` expone un método `reset()` para limpiar la cola y desvincular listeners si el jugador cambia de sala sin recargar la página.

## 5. Handshake de Identidad y Reconexión

`RoomSocket` es responsable de mantener la identidad del jugador sincronizada.

- **En cada `onopen`**, envía automáticamente `join_room` con el `secret_token` almacenado.
- **Al recibir `joined_successfully`**, intercepta el mensaje, persiste el token y notifica vía `onIdentityConfirmed`.
- **El flush de la cola** se dispara únicamente **después** del callback `onIdentityConfirmed`, garantizando que ninguna acción encolada llegue al servidor antes que la identidad.

### 5.1 Mapeo de Códigos de Cierre en la UI (Estados Terminales)

Cuando `RoomSocket` recibe un código de cierre `>= 4000`, transiciona el `connectionStatus` a `'rejected'` y expone el motivo en el store global para que la UI renderice la pantalla de error correspondiente:

- **`4003 (Game In Progress)`:** Muestra "La partida ya ha comenzado" y redirige al inicio.
- **`4004 (Room Not Found)`:** Muestra "La sala no existe o ha expirado" y redirige al inicio.
- **`4006 (Room Full)`:** Muestra "La sala ha alcanzado el límite de 10 jugadores" y redirige al inicio.
- **`4009 (Session Duplicated)`:** Muestra "Sesión iniciada en otra pestaña/dispositivo. Reconecta para recuperar el control". (Requiere botón manual).
- **`4029 (Too Many Requests)`:** Muestra "Desconexión por seguridad (Spam detectado)".

## 6. Contrato de Datos y Validación Estricta (Zod)

El frontend confía únicamente en datos validados:

- **Mensajes entrantes:** `types/game.ts` define `ServerMessageSchema` como un `z.discriminatedUnion` sobre el campo `action`. Esto permite que Zod infiera de manera inequívoca el esquema de `payload` correcto basado en la acción correspondiente (`room_update`, `joined_successfully` o `error`), eliminando la necesidad de comprobaciones manuales. `RoomUpdateMessageSchema` envuelve `RoomViewSchema` en `{action: "room_update", payload: {...}}` — el mismo envelope que usan los otros dos mensajes, coincidiendo con lo que el backend realmente envía (ver `03_api_and_events.md`, sección 4.1). `ServerErrorMessageSchema` valida `{action: "error", payload: {code, message}}`, con `code` restringido al enum cerrado de `03_api_and_events.md`, sección 4.2. El campo `your_role` dentro de `RoomViewSchema` se valida como `z.enum(["innocent", "impostor"])`, reflejando el rol "Inocente" definido en `01_game_design.md`. `SafePlayerSchema` incluye un campo `role` opcional — solo presente cuando `status === "revealing"` (ver `02_architecture.md`, la protección de Zero-Trust sobre el rol se levanta una vez terminada la partida).
- **Mensajes salientes:** `ClientMessageSchema` usa un mapa de tipos (`ClientActionPayloadMap`) para exigir en tiempo de compilación el payload correcto según la acción, y valida en runtime antes de escribir al socket.

## 7. Prevención de Montajes de Ruta

La navegación de la sala funciona como una SPA (_Single Page Application_) pura, utilizando la variable `status` del objeto `RoomView` (`payload` de `room_update`) para renderizar condicionalmente los componentes de las features sin destruir la conexión WebSocket en el árbol de React.

## 8. Sincronización de Reloj para el Temporizador de Turno

`turn_deadline` es un timestamp Unix absoluto **en segundos de época** emitido por el servidor. Compararlo directamente contra `Date.now()` en cada tick asume que el reloj del sistema del cliente no tiene deriva — no siempre cierto, y en un temporizador de 20s el margen de error importa.

> **Corrección de una versión anterior de este documento:** aquí se documentaba la fórmula `offset = turn_deadline_recibido - performance.now()`. Esa fórmula es dimensionalmente incorrecta — `turn_deadline` son segundos desde la época Unix, y `performance.now()` son milisegundos desde que cargó la página, dos relojes con orígenes distintos que no se pueden restar directamente. La fórmula correcta es la que sigue.

En cada `room_update` recibido, el hook `useTurnTimer` calcula el offset entre el reloj de época (`Date.now()`) y el reloj monotónico (`performance.now()`) **una sola vez**, y deriva un "deadline monotónico":

```ts
const deadlineEpochMs = turnDeadline * 1000;
const deadlineMonotonico = performance.now() + (deadlineEpochMs - Date.now());
```

A partir de ahí, cada tick de la cuenta regresiva solo resta contra `performance.now()` — nunca vuelve a tocar `Date.now()` durante el turno, así que un salto o deriva del reloj del sistema a mitad de turno no afecta el conteo restante; solo el ancla inicial depende de `Date.now()`.
