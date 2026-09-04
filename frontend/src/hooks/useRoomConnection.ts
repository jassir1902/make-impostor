// src/hooks/useRoomConnection.ts
import { useEffect, useState } from "react";
import { RoomSocket } from "@/lib/socket/RoomSocket";
import { useGameStore } from "@/store/gameStore";
import { ServerMessageSchema } from "@/types/game";
import { playerIdentity } from "@/lib/storage/playerIdentity";
import { playerName } from "@/lib/storage/playerName";

// Mensajes de UI para cada código de cierre de aplicación (>= 4000). Ver
// 03_api_and_events.md sección 3.1 y 05_frontend_architecture.md sección 5.1
// para el mapeo completo acordado.
const CLOSE_CODE_MESSAGES: Record<number, string> = {
  4003: "La partida ya ha comenzado.",
  4004: "La sala no existe o ha expirado.",
  4006: "La sala ha alcanzado el límite de 10 jugadores.",
  4009: "Sesión iniciada en otra pestaña o dispositivo. Reconecta para recuperar el control.",
  4029: "Desconexión por seguridad (actividad sospechosa detectada).",
};

function messageForCloseCode(code: number): string {
  return (
    CLOSE_CODE_MESSAGES[code] ?? "La conexión fue finalizada por el servidor."
  );
}

export function useRoomConnection(roomId: string) {
  // useState (no useRef): un ref mutado dentro de un efecto no dispara
  // re-render, así que el Provider de Context nunca vería el socket una
  // vez creado — solo el valor `null` de la primera renderización.
  const [socket, setSocket] = useState<RoomSocket | null>(null);

  useEffect(() => {
    // El store de Zustand es un singleton a nivel de módulo — no se
    // reinicia solo al navegar de una sala a otra dentro de la misma
    // sesión de la SPA. Sin este reset, un `connectionStatus` como
    // 'left' (dejado por la sala anterior) sobrevive al montar la sala
    // nueva, y el primer render de RoomGate lo lee como si aplicara a
    // ESTA conexión — rebotando de vuelta a "/" antes de que el socket
    // nuevo tenga oportunidad de establecerse.
    useGameStore.getState().resetStore();

    const name = playerName.get() || "Jugador";
    const secretToken = playerIdentity.get(roomId);

    const socketInstance = new RoomSocket(
      `${process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000"}/ws/room/${roomId}`,
      { playerName: name, secretToken },
      {
        onIdentityConfirmed: (playerId, newSecretToken) => {
          playerIdentity.set(roomId, newSecretToken);
          useGameStore.getState().setMyPlayerId(playerId);
        },
        onValidationError: (_action, message) => {
          useGameStore.getState().setError(message);
        },
        onStatusChange: (status, meta) => {
          useGameStore.getState().setConnectionStatus(status);

          if (status === "rejected" && meta) {
            useGameStore.getState().setRejection({
              code: meta.code,
              message: messageForCloseCode(meta.code),
            });
          }
        },
      },
    );

    const unsubscribe = socketInstance.onMessage((raw: unknown) => {
      const parsed = ServerMessageSchema.safeParse(raw);
      if (!parsed.success) {
        console.error("Mensaje entrante inválido del servidor", parsed.error);
        return;
      }

      const data = parsed.data;

      switch (data.action) {
        case "error":
          useGameStore.getState().setError(data.payload.message);
          break;
        case "joined_successfully":
          // La persistencia del token ya la maneja RoomSocket internamente
          // vía onIdentityConfirmed; aquí no hace falta hacer nada más.
          break;
        case "room_update":
          useGameStore.getState().setRoom(data.payload);
          break;
      }
    });

    socketInstance.connect();
    setSocket(socketInstance);

    return () => {
      unsubscribe();
      socketInstance.close();
      setSocket(null);
    };
  }, [roomId]);

  return socket;
}
