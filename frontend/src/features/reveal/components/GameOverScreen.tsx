// src/features/reveal/components/GameOverScreen.tsx
import { useState } from 'react';
import { useGameStore } from '@/store/gameStore';
import { useSocket } from '@/context/SocketContext';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { RoundLogSummary } from './RoundLogSummary';

export function GameOverScreen() {
  const room = useGameStore((s) => s.room);
  const myPlayerId = useGameStore((s) => s.myPlayerId);
  const socket = useSocket();
  const [showLog, setShowLog] = useState(false);

  if (!room || room.status !== 'revealing') return null;

  const amIHost = myPlayerId !== null && room.players[myPlayerId]?.is_host === true;
  const winnerLabel = room.winner === 'innocents' ? 'Ganaron los Inocentes' : 'Ganó el Impostor';

  // El score es efímero de sala (01_game_design.md, sección 7.1) — se
  // muestra ordenado como un cierre competitivo de la partida, no como
  // una estadística persistente (eso es aparte, Fase 4, y solo por
  // victorias de rol, nunca por este número).
  const rankedPlayers = Object.values(room.players).sort((a, b) => b.score - a.score);

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6 px-4 py-10 text-[var(--color-text)]">
      <header className="text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Fin de la partida
        </p>
        <h1 className="mt-1 text-3xl font-bold text-[var(--color-accent)]">{winnerLabel}</h1>
      </header>

      <Card>
        <h2 className="mb-3 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Roles
        </h2>
        <ul className="flex flex-col gap-2">
          {rankedPlayers.map((player) => (
            <li key={player.id} className="flex items-center justify-between gap-3">
              <span className="truncate text-sm text-[var(--color-text)]">
                {player.name}
                {player.id === myPlayerId && (
                  <span className="ml-1 text-xs text-[var(--color-text-muted)]">(Tú)</span>
                )}
              </span>
              <div className="flex shrink-0 items-center gap-2">
                <span className="font-mono text-xs text-[var(--color-text-muted)]">{player.score} pts</span>
                {player.role && (
                  <Badge tone={player.role === 'impostor' ? 'danger' : 'accent'}>
                    {player.role === 'impostor' ? 'Impostor' : 'Inocente'}
                  </Badge>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Button variant="ghost" onClick={() => setShowLog((v) => !v)}>
        {showLog ? 'Ocultar resumen de rondas' : 'Ver resumen de rondas'}
      </Button>

      {showLog && <RoundLogSummary roundLog={room.round_log ?? []} players={room.players} />}

      {amIHost ? (
        <Button onClick={() => socket?.send('next_round', null)}>Jugar de nuevo</Button>
      ) : (
        <Card className="text-center text-sm text-[var(--color-text-muted)]">
          Esperando a que el anfitrión inicie una revancha...
        </Card>
      )}
    </div>
  );
}
