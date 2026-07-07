import type { CSSProperties } from "react";
import { ImageBroken } from "@phosphor-icons/react";
import type { SavedRecipeSummary } from "../../types/recipe";

interface RecipeThumbnailTileProps {
  recipe: SavedRecipeSummary;
  onSelect: (urlHash: string) => void;
  /** "grid" (SavedRecipesList's 2-up card grid) sizes captions for a ~170px
      tile; "strip" (RecentStrip's horizontal rail) sizes them for a ~112px
      square — the same glass-thumbnail treatment, tuned for scale. */
  size?: "grid" | "strip";
  className?: string;
  style?: CSSProperties;
}

// Shared glass-thumbnail tile — SavedRecipesList's grid and RecentStrip's
// horizontal rail are the same visual object (photo + glass caption strip)
// at two different sizes, so this is the one place that treatment lives.
export function RecipeThumbnailTile({
  recipe,
  onSelect,
  size = "grid",
  className = "",
  style,
}: RecipeThumbnailTileProps) {
  const isStrip = size === "strip";

  return (
    <button
      type="button"
      onClick={() => onSelect(recipe.url_hash)}
      className={`group press-scale animate-fade-in-up relative overflow-hidden rounded-lg bg-surface-2 shadow-[0_8px_24px_-8px_rgba(0,0,0,0.35)] transition-[transform,box-shadow] duration-200 ease-spring hover:-translate-y-1 hover:scale-[1.015] hover:shadow-[0_20px_40px_-12px_rgba(0,0,0,0.5)] ${className}`}
      style={style}
    >
      {recipe.thumbnail ? (
        <img src={recipe.thumbnail} alt="" className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <ImageBroken size={isStrip ? 22 : 24} className="text-text-faint" />
        </div>
      )}
      <div
        className={`absolute inset-x-0 bottom-0 border-t border-t-[var(--color-glass-border-top)] bg-white/[0.08] text-left backdrop-blur-[22px] backdrop-saturate-[1.65] transition-[backdrop-filter] duration-200 ease-spring group-hover:backdrop-blur-[26px] group-hover:backdrop-saturate-[1.8] ${
          isStrip ? "px-2 py-1.5" : "px-3 py-2.5"
        }`}
      >
        <span className="block truncate text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
          {recipe.platform}
        </span>
        <p
          className={`font-editorial truncate font-semibold leading-[1.2] text-text ${
            isStrip ? "text-[14px]" : "text-[16px]"
          }`}
        >
          {recipe.title}
        </p>
      </div>
    </button>
  );
}
