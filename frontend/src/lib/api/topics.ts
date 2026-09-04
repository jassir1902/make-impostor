// src/lib/api/topics.ts

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface TopicWord {
  name: string;
  hint: string | null;
}

export interface Topic {
  id: string;
  name: string;
  words: TopicWord[];
  is_official: boolean;
}

/**
 * Obtiene el catálogo de temáticas oficiales ("quemadas" en el backend,
 * ver 04_roadmap_and_phases.md Fase 1) para poblar el selector del Host.
 */
export async function getOfficialTopics(): Promise<Topic[]> {
  const res = await fetch(`${API_URL}/api/topics/official`);
  if (!res.ok) {
    throw new Error('No se pudo cargar el catálogo de temáticas.');
  }
  return res.json();
}
