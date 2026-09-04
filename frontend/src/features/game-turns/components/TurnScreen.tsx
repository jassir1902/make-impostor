// src/features/game-turns/components/TurnScreen.tsx
import { useGameStore } from "@/store/gameStore";
import { Card } from "@/components/ui/Card";
import { useTurnTimer } from "../hooks/useTurnTimer";
import { TurnTimer } from "./TurnTimer";
import { WordInput } from "./WordInput";
import { WordAnnouncement } from "./WordAnnouncement";

export function TurnScreen() {
  const room = useGameStore((s) => s.room);
  const myPlayerId = useGameStore((s) => s.myPlayerId);
  const { remainingSeconds } = useTurnTimer(room?.turn_deadline ?? null);

  if (!room) return null;

  const currentTurnPlayerId = room.turn_order[room.current_turn_index];
  const currentTurnPlayer = room.players[currentTurnPlayerId];
  const isMyTurn = currentTurnPlayerId === myPlayerId;
  const isImpostor = room.your_role === "impostor";

  return (
    <div className="mx-auto flex w-full max-w-md flex-col items-center gap-6 px-4 py-10 text-[var(--color-text)]">
      <p className="font-mono text-xs uppercase tracking-widest text-[var(--color-text-muted)]">
        Ronda {room.round_number}
      </p>

      <TurnTimer remainingSeconds={remainingSeconds} />

      <WordAnnouncement
        lastSubmission={room.last_submission}
        players={room.players}
      />

      <Card className="w-full text-center">
        {room.show_category && room.current_category && (
          <p className="mb-2 font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]">
            {room.current_category}
          </p>
        )}

        {isImpostor ? (
          <>
            <p className="text-sm text-[var(--color-text-muted)]">
              Eres el impostor
            </p>
            <p className="mt-1 text-lg text-[var(--color-text)]">
              {room.your_hint
                ? `Pista: ${room.your_hint}`
                : "No conoces la palabra. Improvisa."}
            </p>
          </>
        ) : (
          <p className="mt-1 text-2xl font-bold text-[var(--color-accent)]">
            {room.your_word}
          </p>
        )}
      </Card>

      <div className="w-full">
        {isMyTurn ? (
          <>
            <p className="mb-2 text-center text-sm text-[var(--color-text)]">
              Es tu turno
            </p>
            <WordInput />
          </>
        ) : (
          <Card className="text-center text-sm text-[var(--color-text-muted)]">
            Le toca a{" "}
            <span className="font-medium text-[var(--color-text)]">
              {currentTurnPlayer?.name ?? "..."}
            </span>
          </Card>
        )}
      </div>
    </div>
  );
}
