import { ArrowLeft } from "@phosphor-icons/react";
import type { Recipe } from "../types/recipe";
import { StepCard } from "./StepCard";

interface RecipeCardProps {
  recipe: Recipe;
  onReset: () => void;
}

export function RecipeCard({ recipe, onReset }: RecipeCardProps) {
  const heroImage = recipe.steps.find((s) => s.image_path)?.image_path;

  return (
    <div className="flex w-full max-w-[560px] flex-col bg-surface-tile-1 pb-10">
      {/* Hero: full-bleed photo with the title overlaid via a gradient scrim,
          matching the Apple News recipe-card pattern — never text stacked
          on top of a photo inside a separate floating card. */}
      <div className="relative -mt-10 aspect-[4/3] w-full overflow-hidden bg-surface-tile-2">
        {heroImage && <img src={heroImage} alt={recipe.title} className="h-full w-full object-cover" />}
        <div className="absolute inset-0 bg-gradient-to-t from-surface-tile-1 via-surface-tile-1/10 to-transparent" />
        <button
          type="button"
          onClick={onReset}
          className="press-scale safe-top absolute left-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-black/40 text-white backdrop-blur-md"
          aria-label="Extract another recipe"
        >
          <ArrowLeft size={18} weight="bold" />
        </button>
        <h1 className="absolute inset-x-4 bottom-4 text-[28px] font-semibold leading-[1.1] tracking-[-0.374px] text-body-on-dark">
          {recipe.title}
        </h1>
      </div>

      <div className="flex flex-col gap-8 px-4 pt-6">
        <section>
          <h2 className="mb-3 text-[19px] font-semibold text-body-on-dark">Ingredients</h2>
          <div className="flex flex-col gap-2">
            {recipe.ingredients.map((ing) => (
              <div
                key={ing.name}
                className="flex items-center justify-between rounded-lg bg-surface-tile-2 px-4 py-3"
              >
                <span className="text-[15px] text-body-on-dark">{ing.name}</span>
                <span
                  className="ml-3 shrink-0 text-[13px] text-body-muted"
                  title={ing.is_estimated ? "Estimated — not stated in the video" : undefined}
                >
                  {ing.is_estimated && "~"}
                  {[ing.quantity, ing.unit].filter(Boolean).join(" ") || "to taste"}
                </span>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-[19px] font-semibold text-body-on-dark">Steps</h2>
          <div className="flex flex-col gap-2">
            {recipe.steps.map((step) => (
              <StepCard key={step.index} step={step} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
