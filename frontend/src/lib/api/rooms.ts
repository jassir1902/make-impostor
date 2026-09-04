// src/lib/api/rooms.ts

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface CreateRoomResponse {
  room_id: string;
}

export interface RoomExistsResponse {
  exists: boolean;
  status?: string;
  players_count?: number;
}

/**
 * Crea una nueva sala en el backend y devuelve su código único.
 * Este es el único lugar del frontend que debe llamar a este endpoint;
 * el código de sala NUNCA se genera en el cliente (ver auditoría de
 * generación de IDs en el backend).
 */
export async function createRoom(): Promise<CreateRoomResponse> {
  const res = await fetch(`${API_URL}/api/rooms`, { method: 'POST' });

  if (!res.ok) {
    // El backend solo devuelve 500 si agotó los reintentos de generación
    // de un código único (caso extremo, ver generate_unique_room_id).
    throw new Error('No se pudo crear la sala. Intenta de nuevo.');
  }

  return res.json();
}

/**
 * Verifica si un código de sala existe antes de intentar unirse.
 * Usado en el flujo de "Unirse a sala" para dar feedback inmediato
 * (ej. "código inválido") sin necesidad de abrir un WebSocket primero.
 */
export async function checkRoomExists(roomId: string): Promise<RoomExistsResponse> {
  const res = await fetch(`${API_URL}/api/rooms/${roomId}/exists`);
  if (!res.ok) {
    throw new Error('No se pudo verificar la sala.');
  }
  return res.json();
}