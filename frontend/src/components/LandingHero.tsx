import { BookmarkSimple } from "@phosphor-icons/react";
import { UrlSubmitForm } from "./UrlSubmitForm";
import { RecentStrip } from "./RecentStrip";
import { staggerStyle } from "../lib/motion";

interface LandingHeroProps {
  onSubmit: (url: string) => void;
  submitting: boolean;
  error: string | null;
  onViewSaved: () => void;
  onSelectSaved: (urlHash: string) => void;
}

// The landing moment — eyebrow, a two-line display headline, one support
// line, the URL form, "view saved" link, and (if any exist) a strip of
// recent extractions. Extracted from App.tsx's idle-phase inline JSX so
// this composition lives in one place instead of split across App.tsx's
// phase-branching render.
export function LandingHero({ onSubmit, submitting, error, onViewSaved, onSelectSaved }: LandingHeroProps) {
  return (
    <div className="flex w-full max-w-[560px] flex-col items-center gap-8">
      <div className="flex flex-col items-center gap-3 text-center">
        <span
          className="animate-fade-in-up text-[11px] font-bold uppercase tracking-[0.08em] text-text-muted"
          style={staggerStyle(0)}
        >
          res-extract
        </span>
        {/* Per-line reveal (each span its own stagger index) rather than one
            block fade — .animate-fade-in-up already respects
            prefers-reduced-motion globally (index.css's kill-switch), so no
            extra JS-side guard is needed for this to be reduced-motion safe. */}
        <h1 className="font-editorial text-display-xl font-bold leading-[0.98] tracking-[-0.01em] text-text">
          <span className="animate-fade-in-up block" style={staggerStyle(1)}>
            Reels in.
          </span>
          <span className="animate-fade-in-up block" style={staggerStyle(2)}>
            Recipes out.
          </span>
        </h1>
        <p className="animate-fade-in-up max-w-[360px] text-[15px] text-text-muted" style={staggerStyle(3)}>
          Paste a cooking Short or Reel — get the recipe, step by step.
        </p>
      </div>

      <div className="animate-fade-in-up w-full" style={staggerStyle(4)}>
        <UrlSubmitForm onSubmit={onSubmit} submitting={submitting} error={error} />
      </div>

      <button
        type="button"
        onClick={onViewSaved}
        className="animate-fade-in-up press-scale flex min-h-[44px] items-center gap-2 px-2 text-[15px] font-medium text-accent"
        style={staggerStyle(5)}
      >
        <BookmarkSimple size={18} weight="bold" />
        View saved recipes
      </button>

      <RecentStrip onSelect={onSelectSaved} staggerOffset={6} />
    </div>
  );
}
