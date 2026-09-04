// src/features/voting/components/VoteResults.tsx
import type { SafePlayer } from '@/types/game';
import { Card } from '@/components/ui/Card';

interface VoteResultsProps {
  tiedPlayerIds: string[];
  players: Record<string, SafePlayer>;
}

/**
 * El contrato de red no expone conteo de votos en vivo ni quién votó por
 * quién antes de resolverse (ver 03_api_and_events.md, 4.1) — solo
 * `tied_players`, poblado exactamente durante la fase de desempate (GDD,
 * sección 5, "Regla del Primer Empate"). Este componente refleja
 * únicamente esa señal real del servidor, sin inventar un estado de
 * "resultados en vivo" que el backend no soporta.
 */
export function VoteResults({ tiedPlayerIds, players }: VoteResultsProps) {
  if (tiedPlayerIds.length === 0) return null;

  const names = tiedPlayerIds
    .map((id) => players[id]?.name)
    .filter((name): name is string => Boolean(name))
    .join(', ');

  return (
    <Card className="text-center">
      <p className="font-mono text-xs uppercase tracking-wide text-[var(--color-accent)]">Empate</p>
      <p className="mt-1 text-sm text-[var(--color-text)]">
        Hubo un empate entre <span className="font-medium">{names}</span>. Vuelvan a votar solo entre ellos.
      </p>
    </Card>
  );
}
