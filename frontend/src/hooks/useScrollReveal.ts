import { useEffect } from "react";
import type { RefObject } from "react";
// Importing from lib/gsap (not the gsap package directly) ensures
// ScrollTrigger's one-time plugin registration always runs before this hook
// uses the `scrollTrigger` timeline config key below.
import { gsap, prefersReducedMotion } from "../lib/gsap";

// Generic "fade + rise as this element enters the viewport" reveal — a thin
// ScrollTrigger wrapper. Scoped to the recipe-detail page only (ingredient
// rows, step cards); the grid/idle screens keep their existing CSS
// mount-stagger (`animate-fade-in-up` / `staggerStyle`) untouched, since that
// content is short enough that scroll-triggering it adds nothing.
//
// Only `transform`/`opacity` are tweened — compositor-friendly, per the
// plan's performance guardrail.
export function useScrollReveal<T extends HTMLElement>(ref: RefObject<T | null>) {
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const el = ref.current;
    if (!el) return;

    const ctx = gsap.context(() => {
      gsap.set(el, { opacity: 0, y: 24 });
      gsap.to(el, {
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: "power2.out",
        scrollTrigger: {
          trigger: el,
          start: "top 90%",
          toggleActions: "play none none none",
        },
      });
    });

    return () => ctx.revert();
  }, [ref]);
}
