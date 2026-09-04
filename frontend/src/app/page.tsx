// src/app/page.tsx
'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createRoom, checkRoomExists } from '@/lib/api/rooms';
import { playerName } from '@/lib/storage/playerName';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

type PendingAction = 'create' | 'join' | null;

export default function HomePage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction>(null);

  // localStorage no existe durante el render en servidor — se lee recién
  // en el efecto, no en el estado inicial (ver playerName.ts).
  useEffect(() => {
    const stored = playerName.get();
    if (stored) setName(stored);
  }, []);

  function persistName(): boolean {
    const trimmed = name.trim();
    if (!trimmed) {
      setError('Escribe tu nombre antes de continuar.');
      return false;
    }
    playerName.set(trimmed);
    return true;
  }

  async function handleCreate() {
    if (!persistName()) return;
    setError(null);
    setPending('create');
    try {
      const { room_id } = await createRoom();
      router.push(`/room/${room_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear la sala.');
      setPending(null);
    }
  }

  async function handleJoin() {
    if (!persistName()) return;

    const code = joinCode.trim().toUpperCase();
    if (code.length !== 4) {
      setError('El código de sala tiene 4 caracteres.');
      return;
    }

    setError(null);
    setPending('join');
    try {
      const result = await checkRoomExists(code);
      if (!result.exists) {
        setError('Esa sala no existe o ya terminó.');
        setPending(null);
        return;
      }
      router.push(`/room/${code}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo verificar la sala.');
      setPending(null);
    }
  }

  const isBusy = pending !== null;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center gap-8 px-4 py-10 text-[var(--color-text)]">
      <header className="text-center">
        <h1 className="font-mono text-4xl font-bold uppercase tracking-widest text-[var(--color-accent)]">
          El Impostor
        </h1>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">Descubre quién no conoce la palabra.</p>
      </header>

      <div className="flex flex-col gap-2">
        <label htmlFor="player-name" className="font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
          Tu nombre
        </label>
        <input
          id="player-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={20}
          placeholder="Jassir"
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        />
      </div>

      <Card className="flex flex-col gap-3">
        <Button onClick={handleCreate} disabled={isBusy}>
          {pending === 'create' ? 'Creando...' : 'Crear una sala'}
        </Button>
      </Card>

      <Card className="flex flex-col gap-3">
        <label htmlFor="join-code" className="font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
          Código de sala
        </label>
        <input
          id="join-code"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          maxLength={4}
          placeholder="X7K2"
          className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-center font-mono text-lg tracking-widest text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
        />
        <Button variant="ghost" onClick={handleJoin} disabled={isBusy}>
          {pending === 'join' ? 'Verificando...' : 'Unirse a sala'}
        </Button>
      </Card>

      {error && (
        <p role="alert" className="text-center font-mono text-xs text-[var(--color-danger)]">
          {error}
        </p>
      )}
    </main>
  );
}
