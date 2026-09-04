// src/lib/storage/playerIdentity.ts
const key = (roomId: string) => `impostor_player_id_${roomId}`;

const isBrowser = () => typeof window !== "undefined";

export const playerIdentity = {
  get: (roomId: string) =>
    isBrowser() ? localStorage.getItem(key(roomId)) : null,
  set: (roomId: string, playerId: string) => {
    if (isBrowser()) localStorage.setItem(key(roomId), playerId);
  },
  clear: (roomId: string) => {
    if (isBrowser()) localStorage.removeItem(key(roomId));
  },
};
