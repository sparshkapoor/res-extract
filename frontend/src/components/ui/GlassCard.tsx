import { forwardRef } from "react";
import type { ReactNode } from "react";

type Variant = "default" | "vibrant";

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  /** Grid tiles get the hover-intensify glass treatment; the static hero panel doesn't. */
  interactive?: boolean;
  /** "vibrant" reaches for the stronger .vibrancy treatment (blur 28px,
      saturate 190%, see index.css) instead of the standard glass-tile
      blur/saturate — for a surface that wants more presence than the usual
      photo-backed panel (e.g. a landing-page glass accent), still over
      real photography/imagery per the glass-only-over-photos rule. */
  variant?: Variant;
}

// Genuine glass — reserved for panels sitting directly over recipe photography.
// Translucent WHITE tint (never a dark scrim, which kills the "glass" read),
// backdrop-blur + saturate, a brighter top edge to fake the refracted highlight
// real glass has, and a soft lift shadow. See DESIGN.md "Elevation & Depth": if a
// panel isn't sitting over a photo, it doesn't get blur or shadow — full stop.
// forwardRef so GSAP hooks (useHeroScrollReveal) can tween this panel directly.
export const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(function GlassCard(
  { children, className = "", interactive = false, variant = "default" },
  ref,
) {
  return (
    <div
      ref={ref}
      className={`rounded-lg border border-t-[var(--color-glass-border-top)] border-x-[var(--color-glass-border)] border-b-[var(--color-glass-border)] shadow-[0_20px_40px_-12px_rgba(0,0,0,0.45)] ${
        variant === "vibrant" ? "vibrancy" : "bg-white/[0.08] backdrop-blur-[22px] backdrop-saturate-[1.65]"
      } ${
        interactive
          ? "press-scale transition-[transform,backdrop-filter] duration-200 ease-spring hover:-translate-y-1 hover:scale-[1.015] hover:backdrop-blur-[26px] hover:backdrop-saturate-[1.8]"
          : ""
      } ${className}`}
    >
      {children}
    </div>
  );
});
