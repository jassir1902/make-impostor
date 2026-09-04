// src/types/game.ts
import { z } from "zod";

// --- ESQUEMA DEL MENSAJE DE IDENTIDAD CONFIRMADA ---
export const JoinedSuccessfullyMessageSchema = z.object({
  action: z.literal("joined_successfully"),
  payload: z.object({
    player_id: z.string().uuid(),
    secret_token: z.string().uuid(),
  }),
});

// --- ESQUEMA DE ERROR DEL SERVIDOR ---
// Coincide con el envelope real: {"action": "error", "payload": {code, message}}
// (ver 03_api_and_events.md, sección 4.2). El enum de códigos es la misma
// lista cerrada documentada ahí — si el backend agrega uno nuevo, este
// esquema debe actualizarse en el mismo cambio.
export const ErrorCodeSchema = z.enum([
  "NOT_YOUR_TURN",
  "INVALID_PHASE",
  "UNAUTHORIZED_ACTION",
  "INVALID_IMPOSTERS_COUNT",
  "INVALID_TARGET",
  "TOPIC_NOT_FOUND",
]);

export const ServerErrorMessageSchema = z.object({
  action: z.literal("error"),
  payload: z.object({
    code: ErrorCodeSchema,
    message: z.string(),
  }),
});

// --- ESQUEMA DEL JUGADOR SEGURO ---
// `role` solo viaja cuando la partida terminó (status === "revealing") —
// el backend lo omite deliberadamente mientras la partida está en curso
// para no delatar al impostor (ver websockets.py::broadcast_room_view).
export const SafePlayerSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  is_online: z.boolean(),
  is_host: z.boolean(),
  is_alive: z.boolean(),
  score: z.number(),
  role: z.enum(["innocent", "impostor"]).nullable().optional(),
});

// --- ESQUEMA DE UNA ENTRADA DEL ROUND LOG (resumen post-partida) ---
export const RoundLogEntrySchema = z.object({
  round_number: z.number().int(),
  words: z.record(
    z.string().uuid(),
    z.object({ value: z.string(), timed_out: z.boolean() }),
  ),
  eliminated_id: z.string().uuid().nullable(),
  was_double_tie: z.boolean(),
});

// --- ESQUEMA DE LOS CAMPOS DE LA VISTA DE LA SALA (payload de room_update) ---
export const RoomViewSchema = z.object({
  id: z.string().length(4),
  status: z.enum(["waiting", "playing", "voting", "revealing"]),
  round_number: z.number().int(),
  current_turn_index: z.number().int(),
  turn_order: z.array(z.string().uuid()),

  // Timestamp de UNIX enviado por el servidor para la cuenta regresiva
  turn_deadline: z.number().nullable(),

  use_hints: z.boolean(),
  show_category: z.boolean(),
  current_category: z.string().nullable(),

  players: z.record(z.string().uuid(), SafePlayerSchema),

  // "Inocente" en el GDD; el backend usa "innocent" (no "civilian").
  your_role: z.enum(["innocent", "impostor"]).nullable(),
  your_word: z.string().nullable(),
  your_hint: z.string().nullable(),

  tied_players: z.array(z.string().uuid()),

  // La palabra dicha en el último turno (o su timeout) — no es información
  // secreta (ver 01_game_design.md), se transmite a todos por igual.
  last_submission: z
    .object({
      player_id: z.string().uuid(),
      word: z.string(),
      timed_out: z.boolean(),
      sequence: z.number().int(),
    })
    .nullable(),

  // Solo presentes cuando status === "revealing" (03_api_and_events.md, 4.3).
  winner: z.enum(["innocents", "impostors"]).optional(),
  round_log: z.array(RoundLogEntrySchema).optional(),
});

// El backend envuelve TODO mensaje en {"action": ..., "payload": ...},
// incluido el broadcast de estado — RoomViewSchema por sí solo describe
// el contenido de "payload", no el mensaje completo que llega por el
// socket. Sin este envelope, ningún room_update real pasaría nunca la
// validación (los campos estarían anidados donde el esquema no los busca).
export const RoomUpdateMessageSchema = z.object({
  action: z.literal("room_update"),
  payload: RoomViewSchema,
});

export const ServerMessageSchema = z.discriminatedUnion("action", [
  JoinedSuccessfullyMessageSchema,
  ServerErrorMessageSchema,
  RoomUpdateMessageSchema,
]);

// --- INFERENCIA DE TIPOS PARA TYPESCRIPT ---
export type SafePlayer = z.infer<typeof SafePlayerSchema>;
export type RoundLogEntry = z.infer<typeof RoundLogEntrySchema>;
export type RoomView = z.infer<typeof RoomViewSchema>;
export type LastSubmission = NonNullable<RoomView["last_submission"]>;
export type ErrorCode = z.infer<typeof ErrorCodeSchema>;
export type ServerMessage = z.infer<typeof ServerMessageSchema>;

// --- ESQUEMAS DE PAYLOAD POR ACCIÓN ---
export const JoinRoomPayloadSchema = z.object({
  room_id: z.string().length(4),
  player_name: z
    .string()
    .trim()
    .min(1, "El nombre no puede estar vacío")
    .max(20),
  // null en la primera conexión; string en reconexiones (ver playerIdentity)
  secret_token: z.string().uuid().nullable(),
});

export const StartGamePayloadSchema = z.object({
  topic_id: z.string(),
  // El servidor re-valida este rango de todas formas (ver game_service.start_game),
  // pero validamos aquí también para dar feedback inmediato en el panel del Host
  // sin esperar un roundtrip de red.
  imposters_count: z.number().int().min(1),
  use_hints: z.boolean(),
  show_category: z.boolean(),
  anonymous_voting: z.boolean(),
});

export const SendWordPayloadSchema = z.object({
  word: z.string().trim().min(1, "Debes escribir una palabra").max(60),
});

export const VotePayloadSchema = z.object({
  target_id: z.string().uuid(),
});

export const NextRoundPayloadSchema = z.null();

export const LeaveRoomPayloadSchema = z.null();

// --- UNIÓN DISCRIMINADA: UN MENSAJE VÁLIDO POR ACCIÓN ---
// Usamos z.discriminatedUnion en vez de z.union para que Zod (y TypeScript)
// puedan inferir el payload correcto a partir del valor de "action",
// en vez de probar cada esquema uno por uno.

export const ClientMessageSchema = z.discriminatedUnion("action", [
  z.object({ action: z.literal("join_room"), payload: JoinRoomPayloadSchema }),
  z.object({
    action: z.literal("start_game"),
    payload: StartGamePayloadSchema,
  }),
  z.object({ action: z.literal("send_word"), payload: SendWordPayloadSchema }),
  z.object({ action: z.literal("vote"), payload: VotePayloadSchema }),
  z.object({
    action: z.literal("next_round"),
    payload: NextRoundPayloadSchema,
  }),
  z.object({
    action: z.literal("leave_room"),
    payload: LeaveRoomPayloadSchema,
  }),
]);

export type ClientMessage = z.infer<typeof ClientMessageSchema>;

// Tipo utilitario: dado un action, obtiene el tipo de su payload específico.
// Permite que RoomSocket.send() tenga autocompletado y chequeo de tipos
// exacto por acción, en vez de aceptar "unknown" para todas.
export type ClientActionPayloadMap = {
  [K in ClientMessage["action"]]: Extract<
    ClientMessage,
    { action: K }
  >["payload"];
};
export type ClientAction = keyof ClientActionPayloadMap;
