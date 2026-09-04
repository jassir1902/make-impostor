// src/features/room-lobby/components/HostSettingsPanel.tsx
import { useGameStore } from '@/store/gameStore';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Toggle } from '@/components/ui/Toggle';
import { useHostControls } from '../hooks/useHostControls';
import { TopicSelector } from './TopicSelector';

export function HostSettingsPanel() {
  const lastError = useGameStore((s) => s.lastError);
  const {
    topicId,
    setTopicId,
    impostersCount,
    setImpostersCount,
    maxImposters,
    useHints,
    setUseHints,
    showCategory,
    setShowCategory,
    anonymousVoting,
    setAnonymousVoting,
    playerCount,
    minPlayersToStart,
    hasEnoughPlayers,
    canStart,
    startGame,
  } = useHostControls();

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Configuración de la partida
      </h2>

      <TopicSelector value={topicId} onChange={setTopicId} />

      <div className="flex flex-col gap-1.5">
        <label htmlFor="imposters-count" className="font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
          Impostores ({playerCount} jugadores en la sala)
        </label>
        <input
          id="imposters-count"
          type="number"
          min={1}
          max={Math.max(maxImposters, 1)}
          value={impostersCount}
          onChange={(e) => setImpostersCount(Number(e.target.value))}
          disabled={!hasEnoughPlayers}
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 font-mono text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] disabled:opacity-50"
        />
        <p className="text-xs text-[var(--color-text-muted)]">Máximo permitido para esta sala: {maxImposters}</p>
      </div>

      <div className="flex flex-col divide-y divide-[var(--color-border)]">
        <Toggle label="Dar pista al impostor" checked={useHints} onChange={setUseHints} />
        <Toggle label="Mostrar la temática a todos" checked={showCategory} onChange={setShowCategory} />
        <Toggle label="Votación anónima" checked={anonymousVoting} onChange={setAnonymousVoting} />
      </div>

      {!hasEnoughPlayers && (
        <p className="font-mono text-xs text-[var(--color-danger)]">
          Se necesitan al menos {minPlayersToStart} jugadores para iniciar.
        </p>
      )}

      {lastError && (
        <p role="alert" className="font-mono text-xs text-[var(--color-danger)]">
          {lastError}
        </p>
      )}

      <Button onClick={startGame} disabled={!canStart} className="mt-2 w-full">
        Iniciar partida
      </Button>
    </Card>
  );
}
