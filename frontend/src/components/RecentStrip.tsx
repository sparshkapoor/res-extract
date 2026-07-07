import { useEffect, useState } from "react";
import { listSavedRecipes } from "../api/client";
import type { SavedRecipeSummary } from "../types/recipe";
import { RecipeThumbnailTile } from "./ui/RecipeThumbnailTile";
import { staggerStyle } from "../lib/motion";

interface RecentStripProps {
  onSelect: (urlHash: string) => void;
  /** Stagger continues from wherever the landing hero's own entrance left
      off, so this reads as the next beat in one sequence, not a second,
      separately-timed animation. */
  staggerOffset?: number;
}

const MAX_RECENT = 8;

// Horizontal glass-thumbnail rail on the landing screen — the most recent
// extractions, one tap away, so "view saved recipes" isn't the only path
// back to something you already made. Renders nothing at all (not even a
// heading) when there's no saved history yet, rather than an empty rail.
export function RecentStrip({ onSelect, staggerOffset = 0 }: RecentStripProps) {
  const [recipes, setRecipes] = useState<SavedRecipeSummary[] | null>(null);

  useEffect(() => {
    listSavedRecipes()
      .then((r) => setRecipes(r.slice(0, MAX_RECENT)))
      .catch(() => setRecipes([]));
  }, []);

  if (!recipes || recipes.length === 0) return null;

  return (
    <div className="animate-fade-in-up flex w-full flex-col gap-2" style={staggerStyle(staggerOffset)}>
      <span className="px-1 text-[11px] font-bold uppercase tracking-[0.08em] text-text-muted">Recent</span>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {recipes.map((r, i) => (
          <RecipeThumbnailTile
            key={r.url_hash}
            recipe={r}
            onSelect={onSelect}
            size="strip"
            className="aspect-square h-28 w-28 shrink-0"
            style={staggerStyle(staggerOffset + i * 0.5)}
          />
        ))}
      </div>
    </div>
  );
}
