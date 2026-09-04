// src/features/game-turns/components/TurnTimer.tsx
interface TurnTimerProps {
  remainingSeconds: number | null;
  totalSeconds?: number;
}

export function TurnTimer({ remainingSeconds, totalSeconds = 20 }: TurnTimerProps) {
  if (remainingSeconds === null) return null;

  const pct = Math.max(0, Math.min(1, remainingSeconds / totalSeconds));
  const urgent = remainingSeconds <= 5;
  const accentVar = urgent ? 'var(--color-danger)' : 'var(--color-accent)';

  return (
    <div className="flex flex-col items-center gap-1.5">
      <span
        className="font-mono text-3xl font-bold tabular-nums"
        style={{ color: accentVar }}
        aria-live="polite"
      >
        {remainingSeconds}
      </span>
      <div className="h-1.5 w-32 overflow-hidden rounded-full bg-[var(--color-border)]">
        <div
          className="h-full rounded-full transition-[width] duration-200 ease-linear"
          style={{ width: `${pct * 100}%`, backgroundColor: accentVar }}
        />
      </div>
    </div>
  );
}
