// src/lib/socket/RoomSocket.ts
import {
  ClientMessageSchema,
  type ClientActionPayloadMap,
  JoinedSuccessfullyMessageSchema,
  RoomUpdateMessageSchema,
} from "@/types/game";

type Listener = (data: unknown) => void;

// 'rejected' es un estado terminal: el servidor cerró el socket a propósito
// (código >= 4000). 'left' es otro estado terminal, pero deliberado por el
// propio usuario (código 1000 — el servidor solo cierra así después de
// procesar un leave_room). Ninguno de los dos debe reconectar automáticamente.
type ConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "disconnected"
  | "rejected"
  | "left";

interface CloseMeta {
  code: number;
  reason: string;
}

interface PlayerIdentity {
  playerName: string;
  secretToken: string | null;
}

interface RoomSocketCallbacks {
  onIdentityConfirmed: (playerId: string, secretToken: string) => void;
  onStatusChange: (status: ConnectionStatus, meta?: CloseMeta) => void;
  /**
   * Se dispara cuando un mensaje saliente no pasa la validación de Zod
   * (típicamente durante desarrollo, por un cambio de contrato no
   * propagado). Antes esto solo se registraba en la consola del
   * navegador — invisible para quien está usando la app, que solo veía
   * un botón que "no hace nada".
   */
  onValidationError: (action: string, message: string) => void;
}

// Contexto de fase capturado en el momento en que se encola un mensaje
// sensible a la fase (vote/send_word). Se compara contra el RoomView de
// rehidratación al reconectar; si algo cambió, la intención quedó
// obsoleta y no se reproduce ciegamente.
interface QueuedPhaseContext {
  round_number: number;
  status: string;
  tied_players_count: number;
}

interface QueueEntry {
  json: string;
  action: string;
  context: QueuedPhaseContext | null;
}

// Códigos de cierre del servidor (>= 4000): expulsiones deliberadas de la
// aplicación. Nunca deben disparar reconexión automática (ver
// 03_api_and_events.md, sección 3.1, "Obligación del Cliente ante Cierres").
const APPLICATION_CLOSE_CODE_THRESHOLD = 4000;

// El servidor cierra con código 1000 (cierre normal WebSocket) únicamente
// después de procesar un leave_room del propio cliente — es una salida
// deliberada, no una caída de red. Tratarlo igual que un código de
// aplicación (sin reconexión) evita que el cliente intente reincorporarse
// a una sala que él mismo acaba de abandonar.
const NORMAL_CLOSURE_CODE = 1000;

// Acciones cuyo contexto de fase se verifica antes de reproducirlas tras
// una reconexión. `leave_room` y `next_round` siempre son seguros de
// reproducir sin importar cuánto duró el corte.
const PHASE_SENSITIVE_ACTIONS = new Set(["vote", "send_word"]);

export class RoomSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private identity: PlayerIdentity;
  private callbacks: RoomSocketCallbacks;
  private listeners = new Set<Listener>();
  private reconnectAttempts = 0;
  private explicitClose = false;
  private queue: QueueEntry[] = [];
  private lastKnownContext: QueuedPhaseContext | null = null;
  private awaitingRehydrationFlush = false;

  constructor(
    url: string,
    identity: PlayerIdentity,
    callbacks: RoomSocketCallbacks,
  ) {
    this.url = url;
    this.identity = identity;
    this.callbacks = callbacks;
  }

  connect() {
    this.explicitClose = false;

    // Distinguimos "connecting" (primer intento) de "reconnecting"
    // (intentos posteriores) para que la UI pueda mostrar mensajes
    // distintos: "Conectando..." vs "Conexión perdida, reconectando...".
    this.callbacks.onStatusChange(
      this.reconnectAttempts === 0 ? "connecting" : "reconnecting",
    );

    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onStatusChange("connected");

      // El handshake de identidad se manda SIEMPRE al abrir el socket,
      // ya sea la primera conexión o una reconexión tras un corte de red.
      // El flush de la cola NO ocurre aquí — espera a onIdentityConfirmed
      // y, más precisamente, al primer room_update que llega después
      // (ver onmessage), para poder validar la cola contra estado fresco.
      this.awaitingRehydrationFlush = true;
      this.send("join_room", {
        room_id: this.roomIdFromUrl(),
        player_name: this.identity.playerName,
        secret_token: this.identity.secretToken,
      });
    };

    this.ws.onmessage = (event) => {
      const raw = JSON.parse(event.data);

      const identityParsed = JoinedSuccessfullyMessageSchema.safeParse(raw);
      if (identityParsed.success) {
        const { player_id, secret_token } = identityParsed.data.payload;
        this.identity.secretToken = secret_token;
        this.callbacks.onIdentityConfirmed(player_id, secret_token);
        return;
      }

      // El primer room_update tras confirmar identidad es la rehidratación:
      // lo usamos como estado fresco para decidir qué de la cola sigue
      // siendo válido, y recién ahí vaciamos la cola.
      const roomUpdateParsed = RoomUpdateMessageSchema.safeParse(raw);
      if (roomUpdateParsed.success) {
        const freshContext: QueuedPhaseContext = {
          round_number: roomUpdateParsed.data.payload.round_number,
          status: roomUpdateParsed.data.payload.status,
          tied_players_count: roomUpdateParsed.data.payload.tied_players.length,
        };
        this.lastKnownContext = freshContext;

        if (this.awaitingRehydrationFlush) {
          this.awaitingRehydrationFlush = false;
          this.flushQueue(freshContext);
        }
      }

      this.listeners.forEach((cb) => cb(raw));
    };

    this.ws.onclose = (event: CloseEvent) => {
      if (this.explicitClose) {
        this.callbacks.onStatusChange("disconnected");
        return;
      }

      if (event.code === NORMAL_CLOSURE_CODE) {
        // El servidor solo cierra así tras procesar un leave_room propio —
        // salida deliberada, no una caída de red. Sin reconexión.
        this.callbacks.onStatusChange("left", {
          code: event.code,
          reason: event.reason,
        });
        return;
      }

      if (event.code >= APPLICATION_CLOSE_CODE_THRESHOLD) {
        // Cierre deliberado del servidor (sala llena, sesión duplicada,
        // rate limit, etc.) — estado terminal, sin reconexión automática.
        this.callbacks.onStatusChange("rejected", {
          code: event.code,
          reason: event.reason,
        });
        return;
      }

      // Cualquier otro cierre (caída de red, código 1006/1001, sin código)
      // es elegible para reconexión con backoff. No marcamos "disconnected"
      // aquí: scheduleReconnect ya notificará "reconnecting" en el próximo
      // intento, evitando que la UI parpadee entre dos estados en cada ciclo.
      this.scheduleReconnect();
    };

    this.ws.onerror = () => this.ws?.close();
  }

  private roomIdFromUrl(): string {
    const match = this.url.match(/\/ws\/room\/([^/?]+)/);
    return match ? match[1] : "";
  }

  private scheduleReconnect() {
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 15000);
    this.reconnectAttempts++;
    setTimeout(() => this.connect(), delay);
  }

  private sendRaw(action: string, msg: { action: string; payload: unknown }) {
    const json = JSON.stringify(msg);

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(json);
      return;
    }

    const context = PHASE_SENSITIVE_ACTIONS.has(action)
      ? this.lastKnownContext
      : null;
    this.queue.push({ json, action, context });
  }

  send<K extends keyof ClientActionPayloadMap>(
    action: K,
    payload: ClientActionPayloadMap[K],
  ) {
    const msg = { action, payload };

    // Validamos el mensaje saliente con el mismo esquema Zod que usa el
    // backend como referencia. Si algo no encaja (típicamente durante
    // desarrollo, por un cambio de contrato no propagado), lo detectamos
    // aquí en vez de descubrirlo por un rechazo silencioso del servidor.
    const parsed = ClientMessageSchema.safeParse(msg);
    if (!parsed.success) {
      const message = `No se pudo enviar la acción "${action}": el mensaje no tiene el formato esperado.`;
      console.error(
        `Mensaje saliente inválido para acción "${action}":`,
        parsed.error,
      );
      this.callbacks.onValidationError(action, message);
      return;
    }

    this.sendRaw(action as string, parsed.data);
  }

  private flushQueue(freshContext: QueuedPhaseContext) {
    const pending = this.queue;
    this.queue = [];

    for (const entry of pending) {
      if (
        entry.context &&
        !this.contextStillValid(entry.context, freshContext)
      ) {
        // La intención se formó contra un estado que el servidor ya
        // superó (cambió de ronda, de fase, o de sub-fase de desempate) —
        // no se reproduce ciegamente.
        continue;
      }

      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send(entry.json);
      }
    }
  }

  private contextStillValid(
    captured: QueuedPhaseContext,
    fresh: QueuedPhaseContext,
  ): boolean {
    return (
      captured.round_number === fresh.round_number &&
      captured.status === fresh.status &&
      captured.tied_players_count === fresh.tied_players_count
    );
  }

  onMessage(cb: Listener) {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  close() {
    this.explicitClose = true;
    this.ws?.close();
  }
}
