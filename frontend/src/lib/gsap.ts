import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

// Registered once, here, so every call site (the hero focus-pull, the generic
// scroll-reveal hook) shares a single plugin registration instead of each
// component re-registering it.
gsap.registerPlugin(ScrollTrigger);

// The one JS-side reduced-motion guard. The CSS `prefers-reduced-motion` rule
// in index.css only disables CSS animation/transition — it never reaches
// GSAP's JS-driven tweens, so every GSAP hook checks this once, up front,
// instead of reimplementing a matchMedia check per component.
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export { gsap, ScrollTrigger };
