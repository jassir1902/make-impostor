// src/store/gameStore.ts
import { create } from "zustand";
import type { RoomView } from "@/types/game";

interface RejectionInfo {
  code: number;
  message: string;
}

interface GameState {
  room: RoomView | null;
  connectionStatus:
    | "idle"
    | "connecting"
    | "connected"
    | "reconnecting"
    | "disconnected"
    | "rejected"
    | "left";
  lastError: string | null;
  rejection: RejectionInfo | null;
  // El player_id propio, recibido en joined_successfully. Sin esto ningún
  // componente puede saber cuál entrada de room.players es "yo" (para
  // mostrar "Tú", o para derivar si soy el Host).
  myPlayerId: string | null;
  setRoom: (room: RoomView) => void;
  setConnectionStatus: (status: GameState["connectionStatus"]) => void;
  setError: (msg: string | null) => void;
  setRejection: (rejection: RejectionInfo | null) => void;
  setMyPlayerId: (playerId: string) => void;
  resetStore: () => void;
}

export const useGameStore = create<GameState>((set) => ({
  room: null,
  connectionStatus: "idle",
  lastError: null,
  rejection: null,
  myPlayerId: null,

  setRoom: (room) => set({ room }),
  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setError: (lastError) => set({ lastError }),
  setRejection: (rejection) => set({ rejection }),
  setMyPlayerId: (myPlayerId) => set({ myPlayerId }),

  resetStore: () =>
    set({
      room: null,
      connectionStatus: "idle",
      lastError: null,
      rejection: null,
      myPlayerId: null,
    }),
}));
