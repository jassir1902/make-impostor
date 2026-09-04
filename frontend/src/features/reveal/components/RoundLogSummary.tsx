// src/features/reveal/components/RoundLogSummary.tsx
import type { RoundLogEntry, SafePlayer } from '@/types/game';
import { Card } from '@/components/ui/Card';

interface RoundLogSummaryProps {
  roundLog: RoundLogEntry[];
  players: Record<string, SafePlayer>;
}

export function RoundLogSummary({ roundLog, players }: RoundLogSummaryProps) {
  if (roundLog.length === 0) {
    return <p className="text-center text-sm text-[var(--color-text-muted)]">Sin rondas registradas.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {roundLog.map((round) => {
        const eliminatedName = round.eliminated_id ? players[round.eliminated_id]?.name : null;

        return (
          <Card key={round.round_number}>
            <p className="mb-2 font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
              Ronda {round.round_number}
            </p>

            <ul className="mb-3 flex flex-col gap-1">
              {Object.entries(round.words).map(([playerId, entry]) => (
                <li key={playerId} className="flex items-center justify-between text-sm">
                  <span className="text-[var(--color-text)]">{players[playerId]?.name ?? '???'}</span>
                  <span
                    className={
                      entry.timed_out ? 'italic text-[var(--color-text-muted)]' : 'text-[var(--color-text)]'
                    }
                  >
                    {entry.timed_out ? 'Tiempo agotado' : entry.value}
                  </span>
                </li>
              ))}
            </ul>

            <p className="text-xs text-[var(--color-text-muted)]">
              {round.was_double_tie
                ? 'Doble empate — nadie fue eliminado.'
                : eliminatedName
                  ? `Eliminado: ${eliminatedName}`
                  : 'Sin eliminación.'}
            </p>
          </Card>
        );
      })}
    </div>
  );
}
