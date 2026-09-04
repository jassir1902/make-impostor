// src/components/ui/Card.tsx
import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  /** Anillo de acento — usado para resaltar "esta es tu fila" (ver PlayerList). */
  highlighted?: boolean;
}

export function Card({ children, className = '', highlighted = false }: CardProps) {
  return (
    <div
      className={[
        'rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-5',
        highlighted ? 'ring-1 ring-[var(--color-accent)]/60' : '',
        className,
      ].join(' ')}
    >
      {children}
    </div>
  );
}
