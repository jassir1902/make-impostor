// src/components/ui/Button.tsx
import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost";
}

const BASE =
  "rounded-md px-4 py-2.5 font-semibold transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)] disabled:cursor-not-allowed disabled:opacity-40";

const VARIANTS = {
  primary: "bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90",
  ghost:
    "bg-[var(--color-surface)] border border-[var(--color-border)] text-[var(--color-text)] hover:bg-[var(--color-border)]/40",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={[BASE, VARIANTS[variant], className].join(" ")}
      {...props}
    />
  );
}
