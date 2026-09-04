// src/context/SocketContext.tsx
"use client";
import { createContext, useContext, ReactNode } from "react";
import { RoomSocket } from "@/lib/socket/RoomSocket";
import { useRoomConnection } from "@/hooks/useRoomConnection";

// `undefined` = "no hay SocketProvider en el árbol" (error real de uso).
// `null` = "el Provider existe, pero el socket todavía se está conectando"
// (estado legítimo durante el primer render, antes de que el efecto de
// useRoomConnection cree la instancia). Antes estos dos casos se
// confundían bajo `null`, así que cualquier consumidor de useSocket()
// crasheaba en el primer render de cada montaje.
const SocketContext = createContext<RoomSocket | null | undefined>(undefined);

export function SocketProvider({
  roomId,
  children,
}: {
  roomId: string;
  children: ReactNode;
}) {
  const socket = useRoomConnection(roomId);

  return (
    <SocketContext.Provider value={socket}>{children}</SocketContext.Provider>
  );
}

// Hook de conveniencia para que cualquier botón pueda usar el socket.
// Devuelve `null` mientras la conexión se establece — quien lo consuma
// debe manejar ese caso (ej. deshabilitar el botón), no asumir que
// siempre hay un socket listo.
export function useSocket(): RoomSocket | null {
  const context = useContext(SocketContext);
  if (context === undefined) {
    throw new Error("useSocket debe usarse dentro de un SocketProvider");
  }
  return context;
}
