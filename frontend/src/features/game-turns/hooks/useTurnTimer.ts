// src/features/game-turns/hooks/useTurnTimer.ts
import { useEffect, useState } from 'react';

interface UseTurnTimerResult {
  /** Segundos restantes, redondeados hacia arriba. null si no hay turno activo. */
  remainingSeconds: number | null;
}

/**
 * `turn_deadline` es un timestamp Unix en segundos (reloj absoluto del
 * servidor). Compararlo directamente contra `Date.now()` en cada tick
 * asume que el reloj del sistema del cliente no tiene deriva — no
 * siempre cierto, y en un temporizador de 20s el margen de error importa.
 *
 * En vez de eso: al recibir `turn_deadline`, se calcula UNA sola vez el
 * offset entre el reloj de época (Date.now()) y el reloj monotónico
 * (performance.now()), y se deriva un "deadline monotónico". A partir de
 * ahí, cada tick solo usa `performance.now()` — inmune a que el reloj del
 * sistema salte o derive durante el turno (ver 05_frontend_architecture.md,
 * sección 8).
 */
export function useTurnTimer(turnDeadline: number | null): UseTurnTimerResult {
  const [remainingMs, setRemainingMs] = useState<number | null>(null);

  useEffect(() => {
    if (turnDeadline === null) {
      setRemainingMs(null);
      return;
    }

    const deadlineEpochMs = turnDeadline * 1000;
    const deadlineMonotonic = performance.now() + (deadlineEpochMs - Date.now());

    const tick = () => {
      setRemainingMs(Math.max(0, deadlineMonotonic - performance.now()));
    };

    tick();
    const interval = setInterval(tick, 200);
    return () => clearInterval(interval);
  }, [turnDeadline]);

  return {
    remainingSeconds: remainingMs === null ? null : Math.ceil(remainingMs / 1000),
  };
}
