// src/features/voting/components/VotingScreen.tsx
import { useEffect, useState } from "react";
import { useGameStore } from "@/store/gameStore";
import { useSocket } from "@/context/SocketContext";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { VoteResults } from "./VoteResults";

export function VotingScreen() {
  const room = useGameStore((s) => s.room);
  const myPlayerId = useGameStore((s) => s.myPlayerId);
  const socket = useSocket();

  const [selectedTargetId, setSelectedTargetId] = useState<string | null>(null);
  const [voted, setVoted] = useState(false);

  // El componente permanece montado durante todo el ciclo votación → empate
  // → revoto (status sigue en "voting"). El "ya voté" local debe resetearse
  // al entrar a una nueva sub-ronda de desempate — se detecta por CONTENIDO
  // de tied_players, no por referencia, para no resetear el voto propio
  // ante un room_update no relacionado (ej. otro jugador cambia is_online).
  const tiedKey = room?.tied_players.join(",") ?? "";
  useEffect(() => {
    setVoted(false);
    setSelectedTargetId(null);
  }, [tiedKey]);

  if (!room) return null;

  const isTieBreak = room.tied_players.length > 0;
  const amIAlive =
    myPlayerId !== null && room.players[myPlayerId]?.is_alive === true;

  const candidateIds = isTieBreak
    ? room.tied_players
    : Object.values(room.players)
        .filter((p) => p.is_alive)
        .map((p) => p.id);

  function handleVote() {
    if (!socket || !selectedTargetId) return;
    socket.send("vote", { target_id: selectedTargetId });
    setVoted(true);
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6 px-4 py-10 text-[var(--color-text)]">
      <p className="text-center font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Ronda {room.round_number} — Votación
      </p>

      <VoteResults tiedPlayerIds={room.tied_players} players={room.players} />

      {!amIAlive ? (
        <Card className="text-center text-sm text-[var(--color-text-muted)]">
          Ya fuiste eliminado. Solo puedes observar el resto de la partida.
        </Card>
      ) : voted ? (
        <Card className="text-center text-sm text-[var(--color-text-muted)]">
          Voto registrado. Esperando a los demás...
        </Card>
      ) : (
        <>
          <ul className="flex flex-col gap-2">
            {candidateIds.map((id) => {
              const candidate = room.players[id];
              if (!candidate) return null;
              const isSelected = selectedTargetId === id;

              return (
                <li key={id}>
                  <button
                    type="button"
                    onClick={() => setSelectedTargetId(id)}
                    className={[
                      "w-full rounded-lg border px-4 py-3 text-left transition-colors",
                      isSelected
                        ? "border-[var(--color-accent)] bg-[var(--color-surface)] text-[var(--color-text)] ring-1 ring-[var(--color-accent)]"
                        : "border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] hover:border-[var(--color-accent)]/50",
                    ].join(" ")}
                  >
                    {candidate.name}
                  </button>
                </li>
              );
            })}
          </ul>

          <Button onClick={handleVote} disabled={!selectedTargetId}>
            Votar
          </Button>
        </>
      )}
    </div>
  );
}
