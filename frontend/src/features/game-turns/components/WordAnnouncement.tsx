// src/features/game-turns/components/WordAnnouncement.tsx
import { useEffect, useState } from 'react';
import type { LastSubmission, RoomView } from '@/types/game';
import { Card } from '@/components/ui/Card';

const DISPLAY_MS = 5000;

interface WordAnnouncementProps {
  lastSubmission: LastSubmission | null;
  players: RoomView['players'];
}

export function WordAnnouncement({ lastSubmission, players }: WordAnnouncementProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!lastSubmission) return;
    setVisible(true);
    const timeout = setTimeout(() => setVisible(false), DISPLAY_MS);
    return () => clearTimeout(timeout);
    // Se re-dispara únicamente cuando cambia `sequence` (un contador, no un
    // timestamp) — así el mismo jugador diciendo la misma palabra en otro
    // turno sigue contando como un anuncio nuevo, sin depender del reloj.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastSubmission?.sequence]);

  if (!visible || !lastSubmission) return null;

  const name = players[lastSubmission.player_id]?.name ?? '???';

  return (
    <Card className="w-full text-center">
      {lastSubmission.timed_out ? (
        <p className="text-sm text-[var(--color-text-muted)]">
          <span className="font-medium text-[var(--color-text)]">{name}</span> se quedó sin tiempo.
        </p>
      ) : (
        <p className="text-sm text-[var(--color-text)]">
          <span className="font-medium">{name}</span> dijo:{' '}
          <span className="font-bold text-[var(--color-accent)]">&ldquo;{lastSubmission.word}&rdquo;</span>
        </p>
      )}
    </Card>
  );
}
