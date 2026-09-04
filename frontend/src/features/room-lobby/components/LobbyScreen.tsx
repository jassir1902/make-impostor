// src/features/room-lobby/components/LobbyScreen.tsx
import { useState } from 'react';
import { useGameStore } from '@/store/gameStore';
import { Card } from '@/components/ui/Card';
import { PlayerList } from './PlayerList';
import { HostSettingsPanel } from './HostSettingsPanel';

export function LobbyScreen() {
  const room = useGameStore((s) => s.room);
  const myPlayerId = useGameStore((s) => s.myPlayerId);
  const [copied, setCopied] = useState(false);

  if (!room) return null;

  const amIHost = myPlayerId !== null && room.players[myPlayerId]?.is_host === true;

  async function copyRoomCode() {
    try {
      await navigator.clipboard.writeText(room!.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Portapapeles no disponible (ej. contexto no seguro) — el código
      // sigue visible en pantalla para copiarlo a mano.
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-6 px-4 py-10 text-[var(--color-text)]">
      <header className="text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">Código de la sala</p>
        <button
          type="button"
          onClick={copyRoomCode}
          className="mt-1 font-mono text-4xl font-bold tracking-[0.3em] text-[var(--color-accent)] transition-opacity hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
        >
          {room.id}
        </button>
        <p className="mt-1 h-4 text-xs text-[var(--color-text-muted)]">{copied ? 'Copiado' : 'Toca para copiar'}</p>
      </header>

      <section>
        <h1 className="mb-2 font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
          Jugadores
        </h1>
        <PlayerList players={room.players} myPlayerId={myPlayerId} />
      </section>

      <section>
        {amIHost ? (
          <HostSettingsPanel />
        ) : (
          <Card className="text-center text-sm text-[var(--color-text-muted)]">
            Esperando a que el anfitrión inicie la partida...
          </Card>
        )}
      </section>
    </div>
  );
}
