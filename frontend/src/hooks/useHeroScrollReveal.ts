import { useEffect } from "react";
import type { RefObject } from "react";
// Importing from lib/gsap (not the gsap package directly) ensures
// ScrollTrigger's one-time plugin registration always runs before this hook
// uses the `scrollTrigger` timeline config key below.
import { gsap, prefersReducedMotion } from "../lib/gsap";

// The recipe-detail "focus pull": the hero image starts slightly blurred and
// zoomed in, then sharpens/settles to its native (still soft — see DESIGN.md
// Known Gaps re: the 360x640 source ceiling) resolution as the user scrolls
// past it. The glass panel translates/settles in the same scrub. This is the
// mechanism behind DESIGN.md's `hero-focus-pull` motion token.
//
// Only `transform`/`opacity`/`filter` are tweened — compositor-friendly,
// per the plan's performance guardrail. Scrubbed to scroll progress (no
// per-frame React state).
export function useHeroScrollReveal(
  imageRef: RefObject<HTMLElement | null>,
  panelRef: RefObject<HTMLElement | null>,
  containerRef: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (prefersReducedMotion()) return;
    const image = imageRef.current;
    const panel = panelRef.current;
    const container = containerRef.current;
    if (!image || !panel || !container) return;

    const ctx = gsap.context(() => {
      gsap.set(image, { filter: "blur(8px)", scale: 1.15, transformOrigin: "center center" });
      gsap.set(panel, { y: 24, opacity: 0.6 });

      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: container,
          start: "top top",
          end: "bottom top",
          scrub: true,
        },
      });

      tl.to(
        image,
        { filter: "blur(0px)", scale: 1.0, ease: "none" },
        0,
      ).to(
        panel,
        { y: 0, opacity: 1, ease: "none" },
        0,
      );
    });

    return () => ctx.revert();
  }, [imageRef, panelRef, containerRef]);
}
