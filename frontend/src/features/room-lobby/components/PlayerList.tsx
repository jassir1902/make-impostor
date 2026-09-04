// src/features/room-lobby/components/PlayerList.tsx
import type { SafePlayer } from '@/types/game';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

interface PlayerListProps {
  players: Record<string, SafePlayer>;
  myPlayerId: string | null;
}

export function PlayerList({ players, myPlayerId }: PlayerListProps) {
  const roster = Object.values(players);

  if (roster.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Nadie más ha entrado todavía. Comparte el código de la sala.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {roster.map((player) => {
        const isMe = player.id === myPlayerId;

        return (
          <li key={player.id}>
            <Card highlighted={isMe} className="relative flex items-center gap-3 py-3">
              {/* Anillo ámbar: solo se enciende si el jugador sigue en línea. */}
              <span
                aria-hidden
                className={[
                  'h-2.5 w-2.5 shrink-0 rounded-full',
                  player.is_online
                    ? 'bg-[var(--color-accent)] shadow-[0_0_6px_1px_var(--color-accent-glow)]'
                    : 'bg-[var(--color-border)]',
                ].join(' ')}
              />

              <span className="flex-1 truncate font-medium text-[var(--color-text)]">
                {player.name}
                {isMe && <span className="ml-2 text-xs font-normal text-[var(--color-text-muted)]">(Tú)</span>}
              </span>

              {!player.is_alive && <Badge tone="danger">Eliminado</Badge>}

              {player.is_host && (
                <Badge stamped aria-label="Anfitrión">
                  Host
                </Badge>
              )}
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
