import { useEffect, useMemo, useState } from "react";
import { BookmarkSimple } from "@phosphor-icons/react";
import { listSavedRecipes } from "../api/client";
import type { SavedRecipeSummary } from "../types/recipe";
import { SearchBar } from "./SearchBar";
import { FilterChips, type PlatformFilter } from "./FilterChips";
import { Skeleton } from "./ui/Skeleton";
import { RecipeThumbnailTile } from "./ui/RecipeThumbnailTile";
import { staggerStyle } from "../lib/motion";

interface SavedRecipesListProps {
  onSelect: (urlHash: string) => void;
}

// The recipe card grid: photo-backed glass tiles, search + platform filter chrome
// above it. This is the brief's "recipe card grid" screen, built over the real
// GET /api/recipes data — no new backend endpoint needed, filtering is client-side.
export function SavedRecipesList({ onSelect }: SavedRecipesListProps) {
  const [recipes, setRecipes] = useState<SavedRecipeSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<PlatformFilter>("all");

  useEffect(() => {
    listSavedRecipes()
      .then(setRecipes)
      .catch(() => setError("Couldn't load your saved recipes."));
  }, []);

  const filtered = useMemo(() => {
    if (!recipes) return null;
    return recipes.filter((r) => {
      const matchesPlatform = platform === "all" || r.platform === platform;
      const matchesQuery = r.title.toLowerCase().includes(query.trim().toLowerCase());
      return matchesPlatform && matchesQuery;
    });
  }, [recipes, query, platform]);

  if (error) {
    return <p className="text-[14px] text-danger">{error}</p>;
  }

  return (
    <div className="flex w-full flex-col gap-4">
      <SearchBar value={query} onChange={setQuery} />
      <FilterChips value={platform} onChange={setPlatform} />

      {recipes === null && (
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="aspect-[4/5] rounded-lg" />
          ))}
        </div>
      )}

      {recipes !== null && recipes.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <BookmarkSimple size={28} className="text-text-faint" />
          <p className="text-[15px] text-text-muted">
            Recipes you extract are saved here automatically — nothing yet.
          </p>
        </div>
      )}

      {filtered !== null && recipes !== null && recipes.length > 0 && filtered.length === 0 && (
        <p className="py-8 text-center text-[15px] text-text-muted">
          No saved recipes match "{query}".
        </p>
      )}

      {filtered !== null && filtered.length > 0 && (
        <div className="grid grid-cols-2 gap-3">
          {filtered.map((r, i) => (
            <RecipeThumbnailTile
              key={r.url_hash}
              recipe={r}
              onSelect={onSelect}
              size="grid"
              className="aspect-[4/5]"
              style={staggerStyle(i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
