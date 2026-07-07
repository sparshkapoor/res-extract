import { useEffect } from "react";
import type { RefObject } from "react";
// Importing from lib/gsap (not the gsap package directly) ensures
// ScrollTrigger's one-time plugin registration always runs before this hook
// uses the `scrollTrigger` timeline config key below.
import { gsap, prefersReducedMotion } from "../lib/gsap";

// Apple "sheet" easing — used for the hero's load-in entrance below.
const HERO_EASE = "cubic-bezier(0.32, 0.72, 0, 1)";

// The recipe-detail hero: a load-triggered entrance (blur/zoom settling in
// once the image is actually ready to show), followed by a scroll-driven
// parallax once the user scrolls past it.
//
// This used to be a single scroll-scrubbed timeline: the image was set to
// blur(8px) unconditionally on mount, and ONLY cleared as scroll progress
// moved from "top top" to "bottom top". At scroll position 0 — i.e. every
// time this page loads — the image stayed fully blurred under the scrim,
// reading as a missing/empty photo (the reported "thumbnail missing" bug;
// the saved-recipes list rendered the identical file crisp, since it has no
// such scroll-gated reveal). Splitting the reveal (load-triggered) from the
// parallax (scroll-triggered) fixes this: the entrance always plays once
// per mount regardless of scroll position, and the scroll-scrub is a
// no-op at rest (progress 0) since it starts from the entrance's own end
// state — it can never re-blur the image, since it doesn't touch `filter`
// at all.
//
// Only `transform`/`opacity`/`filter` are tweened — compositor-friendly,
// per the plan's performance guardrail. No per-frame React state.
export function useHeroScrollReveal(
  imageRef: RefObject<HTMLElement | null>,
  panelRef: RefObject<HTMLElement | null>,
  containerRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const image = imageRef.current as HTMLImageElement | null;
    const panel = panelRef.current;
    const container = containerRef.current;
    if (!image || !panel || !container) return;

    let cancelled = false;

    const ctx = gsap.context(() => {
      gsap.set(image, { filter: "blur(8px)", scale: 1.12, transformOrigin: "center center" });
      gsap.set(panel, { y: 24, opacity: 0.6 });

      // Only created once the entrance below has finished — by then the
      // image's real dimensions are already known/settled, so this always
      // measures correct trigger bounds without a separate manual
      // ScrollTrigger.refresh() call.
      const attachScrollParallax = () => {
        if (cancelled) return;
        // Neutral at scroll progress 0 (picks up exactly where the entrance
        // left off: scale 1, no offset) — a pure parallax as the hero exits
        // the viewport. Deliberately never touches `filter`, so scrolling
        // can't re-introduce blur.
        gsap.fromTo(
          image,
          { yPercent: 0, scale: 1 },
          {
            yPercent: -8,
            scale: 1.06,
            ease: "none",
            scrollTrigger: { trigger: container, start: "top top", end: "bottom top", scrub: true },
          },
        );
      };

      const reveal = () => {
        if (cancelled) return;
        gsap.to(image, {
          filter: "blur(0px)",
          scale: 1,
          duration: 0.9,
          ease: HERO_EASE,
          onComplete: attachScrollParallax,
        });
        gsap.to(panel, { y: 0, opacity: 1, duration: 0.7, delay: 0.1, ease: HERO_EASE });
      };

      if (image.complete) {
        reveal();
      } else if (typeof image.decode === "function") {
        image.decode().then(reveal).catch(reveal);
      } else {
        image.addEventListener("load", reveal, { once: true });
      }
    });

    return () => {
      cancelled = true;
      ctx.revert();
    };
  }, [imageRef, panelRef, containerRef]);
}
