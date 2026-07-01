import { useEffect, useState } from "react";
import { CaretRight, ImageBroken, BookmarkSimple } from "@phosphor-icons/react";
import { listSavedRecipes } from "../api/client";
import type { SavedRecipeSummary } from "../types/recipe";

interface SavedRecipesListProps {
  onSelect: (urlHash: string) => void;
}

export function SavedRecipesList({ onSelect }: SavedRecipesListProps) {
  const [recipes, setRecipes] = useState<SavedRecipeSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSavedRecipes()
      .then(setRecipes)
      .catch(() => setError("Couldn't load your saved recipes."));
  }, []);

  if (error) {
    return <p className="text-[14px] text-red-600">{error}</p>;
  }

  if (recipes === null) {
    return <p className="text-[14px] text-ink-muted-48">Loading saved recipes...</p>;
  }

  if (recipes.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <BookmarkSimple size={28} className="text-ink-muted-48" />
        <p className="text-[15px] text-ink-muted-48">
          Recipes you extract are saved here automatically — nothing yet.
        </p>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3">
      {recipes.map((r) => (
        <button
          key={r.url_hash}
          type="button"
          onClick={() => onSelect(r.url_hash)}
          // Generous tap target: full-width row, min-h-[72px], py-3 — keeps
          // adjacent rows from being fat-finger-prone even on a small phone.
          className="press-scale flex min-h-[72px] w-full items-center gap-4 rounded-lg border border-hairline bg-white px-4 py-3 text-left"
        >
          <div className="h-14 w-14 shrink-0 overflow-hidden rounded-md bg-canvas-parchment">
            {r.thumbnail ? (
              <img src={r.thumbnail} alt="" className="h-full w-full object-cover" loading="lazy" />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <ImageBroken size={20} className="text-ink-muted-48" />
              </div>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[16px] font-medium text-ink">{r.title}</p>
            <p className="text-[13px] capitalize text-ink-muted-48">{r.platform}</p>
          </div>
          <CaretRight size={18} className="shrink-0 text-ink-muted-48" />
        </button>
      ))}
    </div>
  );
}
