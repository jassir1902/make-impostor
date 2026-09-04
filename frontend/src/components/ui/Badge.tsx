// src/components/ui/Badge.tsx
import type { HTMLAttributes, ReactNode } from 'react';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  children: ReactNode;
  tone?: 'accent' | 'danger';
  /** Sello diagonal (ver el badge "Host" en PlayerList) — usar con moderación. */
  stamped?: boolean;
}

const TONES = {
  accent: 'bg-[var(--color-accent)] text-[var(--color-bg)]',
  danger: 'text-[var(--color-danger)]',
};

export function Badge({ children, tone = 'accent', stamped = false, className = '', ...rest }: BadgeProps) {
  const stampStyles = stamped
    ? 'absolute -right-2 -top-2 rotate-[-8deg] rounded-sm px-2 py-0.5 shadow-sm'
    : 'rounded px-1.5 py-0.5';

  return (
    <span
      className={[
        'font-mono text-[10px] font-bold uppercase tracking-wider',
        tone === 'accent' ? TONES.accent : TONES.danger,
        stampStyles,
        className,
      ].join(' ')}
      {...rest}
    >
      {children}
    </span>
  );
}
