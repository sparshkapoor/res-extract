import { ArrowLeft } from "@phosphor-icons/react";
import type { Recipe } from "../types/recipe";
import { StepCard } from "./StepCard";
import { GlassCard } from "./ui/GlassCard";

interface RecipeCardProps {
  recipe: Recipe;
  onReset: () => void;
}

// The one place in the whole app where hero photography meets the metadata
// system directly: glass panel over the photo, monospace data row, flat
// precision list below. See DESIGN.md — glass is reserved for exactly this.
export function RecipeCard({ recipe, onReset }: RecipeCardProps) {
  const heroImage = recipe.steps.find((s) => s.image_path)?.image_path;

  const metadata: { label: string; highlight?: boolean }[] = [
    ...(recipe.cook_time_minutes != null
      ? [{ label: `${recipe.cook_time_minutes} min`, highlight: true }]
      : []),
    ...(recipe.servings != null ? [{ label: `Serves ${recipe.servings}` }] : []),
    ...(recipe.calories != null ? [{ label: `${recipe.calories} cal` }] : []),
    ...(recipe.oven_temp_f != null ? [{ label: `${recipe.oven_temp_f}°F` }] : []),
  ];

  return (
    <div className="flex w-full max-w-[560px] flex-col bg-canvas pb-10">
      <div className="relative -mt-10 aspect-[4/3] w-full overflow-hidden bg-surface-2 animate-fade-in-up" style={{ "--stagger-index": 0 }}>
        {heroImage && <img src={heroImage} alt={recipe.title} className="h-full w-full object-cover" />}
        {/* Scrim sits between the photo and the glass layer — protects title
            legibility without making the glass panel itself opaque. */}
        <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-glass-scrim to-transparent" />
        <button
          type="button"
          onClick={onReset}
          className="press-scale safe-top absolute left-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-black/50 text-white"
          aria-label="Extract another recipe"
        >
          <ArrowLeft size={18} weight="bold" />
        </button>

        <GlassCard className="absolute inset-x-4 bottom-4 px-5 py-4">
          <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-text-muted">
            {recipe.platform}
          </span>
          <h1 className="mt-1 text-[32px] font-bold leading-[1.1] tracking-[-0.03em] text-text">
            {recipe.title}
          </h1>
          {metadata.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[15px] font-semibold tracking-[-0.01em]">
              {metadata.map((m) => (
                <span key={m.label} className={m.highlight ? "text-accent" : "text-text-muted"}>
                  {m.label}
                </span>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      <div className="flex flex-col gap-8 px-4 pt-6">
        <section className="animate-fade-in-up" style={{ "--stagger-index": 1 }}>
          <h2 className="mb-3 text-[19px] font-semibold leading-[1.2] tracking-[-0.02em] text-text">
            Ingredients
          </h2>
          <div className="overflow-hidden rounded-md bg-surface-2">
            {recipe.ingredients.map((ing, i) => (
              <div
                key={ing.name}
                className={`flex items-center justify-between px-4 py-3 ${
                  i > 0 ? "border-t border-hairline" : ""
                }`}
              >
                <span className="text-[15px] text-text">{ing.name}</span>
                <span
                  className="ml-3 shrink-0 text-[15px] text-text-muted"
                  title={ing.is_estimated ? "Estimated — not stated in the video" : undefined}
                >
                  {ing.is_estimated && "~"}
                  {[ing.quantity, ing.unit].filter(Boolean).join(" ") || "to taste"}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="animate-fade-in-up" style={{ "--stagger-index": 2 }}>
          <h2 className="mb-3 text-[19px] font-semibold leading-[1.2] tracking-[-0.02em] text-text">Steps</h2>
          <div className="flex flex-col gap-2">
            {recipe.steps.map((step, i) => (
              <StepCard key={step.index} step={step} staggerIndex={i} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
