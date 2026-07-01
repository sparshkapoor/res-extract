import type { ReactNode } from "react";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
}

// Approximated "liquid glass" (there is no official liquid-glass.css — Apple
// documents this for native platforms only). Layered translucency + a thin
// highlight border + backdrop-blur, with a solid-fill fallback via the
// bg-black/40 base for browsers without backdrop-filter support.
export function GlassCard({ children, className = "" }: GlassCardProps) {
  return (
    <div
      className={`rounded-lg border border-white/15 bg-black/40 backdrop-blur-xl shadow-[inset_0_1px_0_rgba(255,255,255,0.1)] ${className}`}
    >
      {children}
    </div>
  );
}
