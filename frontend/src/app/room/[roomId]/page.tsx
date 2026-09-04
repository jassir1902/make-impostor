// src/app/room/[roomId]/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { SocketProvider, useSocket } from "@/context/SocketContext";
import { useGameStore } from "@/store/gameStore";
import { playerIdentity } from "@/lib/storage/playerIdentity";
import { playerName } from "@/lib/storage/playerName";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { LobbyScreen } from "@/features/room-lobby/components/LobbyScreen";
import { TurnScreen } from "@/features/game-turns/components/TurnScreen";
import { VotingScreen } from "@/features/voting/components/VotingScreen";
import { GameOverScreen } from "@/features/reveal/components/GameOverScreen";

export default function RoomPage() {
  const params = useParams<{ roomId: string }>();
  const roomId = (params.roomId ?? "").toUpperCase();

  // Si ya existe un secret_token guardado para ESTA sala, es una
  // reconexión legítima — no hace falta pedir nombre de nuevo. Si no
  // existe (ej. alguien pegó la URL de la sala directamente, sin pasar
  // por la landing page), se pide confirmar el nombre ANTES de abrir el
  // socket — de lo contrario se conecta silenciosamente con el nombre
  // por defecto ("Jugador"), sin que la persona se entere ni pueda elegir.
  const [nameConfirmed, setNameConfirmed] = useState(false);

  useEffect(() => {
    if (playerIdentity.get(roomId) !== null) {
      setNameConfirmed(true);
    }
  }, [roomId]);

  if (!nameConfirmed) {
    return (
      <NameGate roomId={roomId} onConfirmed={() => setNameConfirmed(true)} />
    );
  }

  return (
    <SocketProvider roomId={roomId}>
      <RoomGate />
    </SocketProvider>
  );
}

function NameGate({
  roomId,
  onConfirmed,
}: {
  roomId: string;
  onConfirmed: () => void;
}) {
  const [name, setName] = useState("");

  useEffect(() => {
    const stored = playerName.get();
    if (stored) setName(stored);
  }, []);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    playerName.set(trimmed);
    onConfirmed();
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="flex w-full max-w-sm flex-col gap-4">
        <div className="text-center">
          <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
            Unirse a la sala
          </p>
          <p className="mt-1 font-mono text-2xl font-bold tracking-[0.2em] text-[var(--color-accent)]">
            {roomId}
          </p>
        </div>
        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={20}
            placeholder="Tu nombre"
            autoFocus
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-center text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          />
          <Button type="submit" disabled={!name.trim()}>
            Unirse
          </Button>
        </form>
      </Card>
    </main>
  );
}

function RoomGate() {
  const router = useRouter();
  const connectionStatus = useGameStore((s) => s.connectionStatus);
  const rejection = useGameStore((s) => s.rejection);
  const room = useGameStore((s) => s.room);

  // 'left' se confirma únicamente cuando el servidor ya procesó nuestro
  // leave_room y cerró el socket con código 1000 — recién ahí navegamos,
  // nunca antes (ver LeaveRoomHeader).
  useEffect(() => {
    if (connectionStatus === "left") {
      router.push("/");
    }
  }, [connectionStatus, router]);

  if (connectionStatus === "left") {
    return <CenteredMessage text="Saliste de la sala." />;
  }

  if (connectionStatus === "rejected") {
    return (
      <CenteredMessage
        text={
          rejection?.message ?? "La conexión fue finalizada por el servidor."
        }
        showHomeLink
      />
    );
  }

  if (connectionStatus === "idle" || connectionStatus === "connecting") {
    return <CenteredMessage text="Conectando..." />;
  }

  if (connectionStatus === "reconnecting") {
    return <CenteredMessage text="Conexión perdida. Reconectando..." />;
  }

  if (connectionStatus === "disconnected") {
    return <CenteredMessage text="Desconectado." showHomeLink />;
  }

  // connected, pero la rehidratación todavía no llegó.
  if (!room) {
    return <CenteredMessage text="Cargando sala..." />;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <LeaveRoomHeader />

      {room.status === "waiting" && <LobbyScreen />}
      {room.status === "playing" && <TurnScreen />}
      {room.status === "voting" && <VotingScreen />}
      {room.status === "revealing" && <GameOverScreen />}
    </div>
  );
}

function LeaveRoomHeader() {
  const socket = useSocket();
  const router = useRouter();

  function handleLeave() {
    // Deliberadamente NO navegamos ni cerramos el socket aquí. Si lo
    // hiciéramos de inmediato, el cierre local podría ganarle la carrera
    // al envío del mensaje leave_room por la red — el servidor nunca lo
    // recibiría, y solo vería una desconexión abrupta (que NO elimina al
    // jugador, solo lo marca offline). La navegación ocurre en RoomGate,
    // reaccionando al connectionStatus 'left' que confirma que el
    // servidor ya procesó el leave_room y cerró el socket él mismo.
    socket?.send("leave_room", null);

    // Red de seguridad: si por lo que sea (paquete perdido, backend caído)
    // el servidor nunca confirma el cierre, no dejamos a la persona
    // esperando para siempre — forzamos la salida de todos modos.
    setTimeout(() => {
      if (useGameStore.getState().connectionStatus !== "left") {
        router.push("/");
      }
    }, 3000);
  }

  return (
    <div className="flex justify-end px-4 pt-4">
      <button
        type="button"
        onClick={handleLeave}
        className="font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)] hover:text-[var(--color-danger)]"
      >
        Salir de la sala
      </button>
    </div>
  );
}

function CenteredMessage({
  text,
  showHomeLink = false,
}: {
  text: string;
  showHomeLink?: boolean;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <Card className="flex max-w-sm flex-col items-center gap-4 text-center">
        <p className="text-sm text-[var(--color-text)]">{text}</p>
        {showHomeLink && (
          <Button variant="ghost" onClick={() => (window.location.href = "/")}>
            Volver al inicio
          </Button>
        )}
      </Card>
    </main>
  );
}
