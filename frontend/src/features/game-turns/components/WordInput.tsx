// src/features/game-turns/components/WordInput.tsx
import { useState, type FormEvent } from 'react';
import { useSocket } from '@/context/SocketContext';
import { Button } from '@/components/ui/Button';

export function WordInput() {
  const socket = useSocket();
  const [word, setWord] = useState('');
  const [submitted, setSubmitted] = useState(false);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = word.trim();
    if (!trimmed || !socket || submitted) return;

    socket.send('send_word', { word: trimmed });
    setSubmitted(true);
  }

  if (submitted) {
    return (
      <p className="text-center text-sm text-[var(--color-text-muted)]">
        Palabra enviada. Esperando a los demás...
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={word}
        onChange={(e) => setWord(e.target.value)}
        maxLength={60}
        placeholder="Escribe tu palabra..."
        autoFocus
        className="flex-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
      />
      <Button type="submit" disabled={!word.trim()}>
        Enviar
      </Button>
    </form>
  );
}
