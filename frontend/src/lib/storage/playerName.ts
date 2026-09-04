// src/lib/storage/playerName.ts
const KEY = "impostor_player_name";

const isBrowser = () => typeof window !== "undefined";

export const playerName = {
  get: (): string | null => (isBrowser() ? localStorage.getItem(KEY) : null),
  set: (name: string): void => {
    if (isBrowser()) localStorage.setItem(KEY, name);
  },
};
