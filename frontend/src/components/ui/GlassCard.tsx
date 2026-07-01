import type { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  /** Grid tiles get the hover-intensify glass treatment; the static hero panel doesn't. */
  interactive?: boolean;
}

// Genuine glass — reserved for panels sitting directly over recipe photography.
// Translucent WHITE tint (never a dark scrim, which kills the "glass" read),
// backdrop-blur + saturate, a brighter top edge to fake the refracted highlight
// real glass has, and a soft lift shadow. See DESIGN.md "Elevation & Depth": if a
// panel isn't sitting over a photo, it doesn't get blur or shadow — full stop.
export function GlassCard({ children, className = "", interactive = false }: GlassCardProps) {
  return (
    <div
      className={`rounded-lg border border-t-[var(--color-glass-border-top)] border-x-[var(--color-glass-border)] border-b-[var(--color-glass-border)] bg-white/[0.08] backdrop-blur-[22px] backdrop-saturate-[1.65] shadow-[0_20px_40px_-12px_rgba(0,0,0,0.45)] ${
        interactive
          ? "press-scale transition-[transform,backdrop-filter] duration-200 ease-out hover:-translate-y-1 hover:scale-[1.015] hover:backdrop-blur-[26px] hover:backdrop-saturate-[1.8]"
          : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}
