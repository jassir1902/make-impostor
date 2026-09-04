// src/features/room-lobby/hooks/useHostControls.ts
import { useEffect, useState } from 'react';
import { useGameStore } from '@/store/gameStore';
import { useSocket } from '@/context/SocketContext';

const MIN_PLAYERS_TO_START = 3;

/**
 * floor((N - 1) / 2) — la misma fórmula que el servidor aplica como
 * autoridad final (01_game_design.md, sección 4). Se replica aquí
 * únicamente para dar feedback inmediato en el panel; el servidor sigue
 * siendo quien decide, y puede rechazar con INVALID_IMPOSTERS_COUNT si de
 * todos modos se envía un valor fuera de rango (ej. por una condición de
 * carrera con un jugador que se fue justo antes de iniciar).
 */
function maxImpostersFor(playerCount: number): number {
  if (playerCount < MIN_PLAYERS_TO_START) return 1;
  return Math.floor((playerCount - 1) / 2);
}

export function useHostControls() {
  const room = useGameStore((s) => s.room);
  const socket = useSocket();

  const [topicId, setTopicId] = useState<string | null>(null);
  const [impostersCount, setImpostersCount] = useState(1);
  const [useHints, setUseHints] = useState(true);
  const [showCategory, setShowCategory] = useState(true);
  const [anonymousVoting, setAnonymousVoting] = useState(false);

  const playerCount = room ? Object.keys(room.players).length : 0;
  const maxImposters = maxImpostersFor(playerCount);
  const hasEnoughPlayers = playerCount >= MIN_PLAYERS_TO_START;
  const canStart = hasEnoughPlayers && topicId !== null && socket !== null;

  // Si el máximo baja (ej. un jugador se fue del lobby), el valor elegido
  // no debe quedar apuntando por encima de lo que el servidor va a
  // aceptar cuando se presione "Iniciar partida".
  useEffect(() => {
    setImpostersCount((current) => Math.min(Math.max(current, 1), Math.max(maxImposters, 1)));
  }, [maxImposters]);

  function startGame() {
    if (!socket || !topicId) return;

    socket.send('start_game', {
      topic_id: topicId,
      imposters_count: impostersCount,
      use_hints: useHints,
      show_category: showCategory,
      anonymous_voting: anonymousVoting,
    });
  }

  return {
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
    minPlayersToStart: MIN_PLAYERS_TO_START,
    hasEnoughPlayers,
    canStart,
    startGame,
  };
}
