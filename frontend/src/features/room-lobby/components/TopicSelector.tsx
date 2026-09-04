// src/features/room-lobby/components/TopicSelector.tsx
import { useEffect, useState } from "react";
import { getOfficialTopics, type Topic } from "@/lib/api/topics";

// Caché a nivel de módulo, fuera del ciclo de vida de React. El catálogo
// oficial es prácticamente estático dentro de una sesión — no hay razón
// para volver a pedirlo cada vez que este componente se remonta (ej. si
// HostSettingsPanel se desmonta y remonta por un cambio momentáneo de
// is_host). Sin esto, cada remontaje reinicia `topicId` a null durante la
// ventana en que el fetch está en vuelo, y un clic en "Iniciar partida"
// justo en ese instante queda deshabilitado sin ninguna explicación visible.
let cachedTopics: Topic[] | null = null;
let inFlightRequest: Promise<Topic[]> | null = null;

function loadTopicsOnce(): Promise<Topic[]> {
  if (cachedTopics) return Promise.resolve(cachedTopics);
  if (!inFlightRequest) {
    inFlightRequest = getOfficialTopics().then((data) => {
      cachedTopics = data;
      inFlightRequest = null;
      return data;
    });
  }
  return inFlightRequest;
}

interface TopicSelectorProps {
  value: string | null;
  onChange: (topicId: string) => void;
}

export function TopicSelector({ value, onChange }: TopicSelectorProps) {
  const [topics, setTopics] = useState<Topic[] | null>(cachedTopics);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (cachedTopics) {
      // Ya en caché (ej. remontaje) — nada que pedir, solo asegurar el
      // valor por defecto si todavía no hay uno elegido.
      if (!value && cachedTopics.length > 0) onChange(cachedTopics[0].id);
      return;
    }

    let cancelled = false;
    loadTopicsOnce()
      .then((data) => {
        if (cancelled) return;
        setTopics(data);
        if (!value && data.length > 0) onChange(data[0].id);
      })
      .catch(() => {
        if (!cancelled)
          setLoadError("No se pudo cargar el catálogo. Intenta de nuevo.");
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loadError) {
    return (
      <p className="font-mono text-sm text-[var(--color-danger)]">
        {loadError}
      </p>
    );
  }

  if (!topics) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        Cargando temáticas...
      </p>
    );
  }

  if (topics.length === 0) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">
        No hay temáticas disponibles todavía.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <label
        htmlFor="topic-select"
        className="font-mono text-xs uppercase tracking-wide text-[var(--color-text-muted)]"
      >
        Temática
      </label>
      <select
        id="topic-select"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[var(--color-text)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
      >
        {topics.map((topic) => (
          <option key={topic.id} value={topic.id}>
            {topic.name}
          </option>
        ))}
      </select>
    </div>
  );
}
