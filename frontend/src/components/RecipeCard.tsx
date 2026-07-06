import { useRef } from "react";
import { ArrowLeft, Timer, UsersThree, Flame, Thermometer } from "@phosphor-icons/react";
import type { Recipe, Ingredient } from "../types/recipe";
import { StepCard } from "./StepCard";
import { GlassCard } from "./ui/GlassCard";
import { useHeroScrollReveal } from "../hooks/useHeroScrollReveal";
import { useScrollReveal } from "../hooks/useScrollReveal";

interface RecipeCardProps {
  recipe: Recipe;
  onReset: () => void;
}

// "To taste" is only ever true for seasonings (salt, pepper, a generic
// "spices" category) — a whole ingredient like "tomatoes" missing a
// quantity is a data gap, not something you'd season by feel, so labeling
// it "to taste" is actively misleading. name_is_generic already flags the
// generic-category case (backend sets it for "spices"/"seasoning"); this
// regex catches named seasonings that aren't generic.
const SEASONING_NAME_RE = /\b(salt|pepper|spice|spices|seasoning|herbs|garnish)\b/i;

// One ingredient row, scroll-revealed independently via useScrollReveal — this
// is why it's split out of the map() body below (hooks need a stable
// per-element ref, not a ref array hand-rolled inline).
function IngredientRow({ ing, showDivider }: { ing: Ingredient; showDivider: boolean }) {
  const rowRef = useRef<HTMLDivElement>(null);
  useScrollReveal(rowRef);

  const amount = [ing.quantity, ing.unit].filter(Boolean).join(" ");
  const isSeasoning = ing.name_is_generic || SEASONING_NAME_RE.test(ing.name);
  const displayAmount = amount || (isSeasoning ? "to taste" : "");

  return (
    <div
      ref={rowRef}
      className={`flex items-center justify-between px-4 py-3 ${showDivider ? "border-t border-hairline" : ""}`}
    >
      <span className="text-[15px] text-text">
        {ing.name}
        {ing.note && <span className="ml-2 text-[13px] text-text-faint">{ing.note}</span>}
      </span>
      {displayAmount && (
        <span
          className="ml-3 shrink-0 text-[15px] text-text-muted"
          title={ing.is_estimated ? "Estimated — not stated in the video" : undefined}
        >
          {ing.is_estimated && "~"}
          {displayAmount}
        </span>
      )}
    </div>
  );
}

// A single step, scroll-revealed independently via useScrollReveal — mirrors
// IngredientRow's shape so StepCard itself can stay a plain forwardRef card.
function RevealedStepCard({ step }: { step: Recipe["steps"][number] }) {
  const stepRef = useRef<HTMLDivElement>(null);
  useScrollReveal(stepRef);
  return <StepCard ref={stepRef} step={step} />;
}

// The one place in the whole app where hero photography meets the metadata
// system directly: glass panel over the photo, monospace data row, flat
// precision list below. See DESIGN.md — glass is reserved for exactly this.
export function RecipeCard({ recipe, onReset }: RecipeCardProps) {
  // Prefer the dedicated hero shot (VLM-selected finished-dish frame,
  // independent of any step's own instructional moment) — falls back to the
  // last step's frame for recipes extracted before hero_image_path existed.
  // See DESIGN.md Known Gaps re: the 360x640 source-resolution ceiling this
  // doesn't (and can't) fix, only avoids compounding.
  const heroImage =
    recipe.hero_image_path ?? [...recipe.steps].reverse().find((s) => s.image_path)?.image_path;

  const heroContainerRef = useRef<HTMLDivElement>(null);
  const heroImageRef = useRef<HTMLImageElement>(null);
  const heroPanelRef = useRef<HTMLDivElement>(null);
  useHeroScrollReveal(heroImageRef, heroPanelRef, heroContainerRef);

  const metadata: { label: string; highlight?: boolean; icon: typeof Timer }[] = [
    ...(recipe.cook_time_minutes != null
      ? [{ label: `${recipe.cook_time_minutes} min`, highlight: true, icon: Timer }]
      : []),
    ...(recipe.servings != null ? [{ label: `Serves ${recipe.servings}`, icon: UsersThree }] : []),
    ...(recipe.calories != null ? [{ label: `${recipe.calories} cal`, icon: Flame }] : []),
    ...(recipe.oven_temp_f != null ? [{ label: `${recipe.oven_temp_f}°F`, icon: Thermometer }] : []),
  ];

  return (
    <div className="flex w-full max-w-[560px] flex-col bg-canvas pb-10">
      <div ref={heroContainerRef} className="relative -mt-10 aspect-[3/4] w-full overflow-hidden bg-surface-2">
        {heroImage && (
          <img ref={heroImageRef} src={heroImage} alt={recipe.title} className="h-full w-full object-cover" />
        )}
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

        <GlassCard ref={heroPanelRef} className="absolute inset-x-4 bottom-4 px-5 py-4">
          <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-text-muted">
            {recipe.platform}
          </span>
          <h1 className="mt-1 font-editorial text-[40px] font-bold leading-[1.05] tracking-[-0.01em] text-text">
            {recipe.title}
          </h1>
          {metadata.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              {metadata.map((m) => (
                <span
                  key={m.label}
                  className={`inline-flex items-center gap-1.5 font-mono text-[15px] font-semibold tracking-[-0.01em] ${
                    m.highlight ? "text-accent" : "text-text-muted"
                  }`}
                >
                  <m.icon size={15} weight="bold" />
                  {m.label}
                </span>
              ))}
            </div>
          )}
        </GlassCard>
      </div>

      <div className="flex flex-col gap-8 px-4 pt-6">
        <section>
          <h2 className="mb-3 font-editorial text-[21px] font-semibold italic leading-[1.2] text-text">
            Ingredients
          </h2>
          <div className="overflow-hidden rounded-md bg-surface-2">
            {recipe.ingredients.map((ing, i) => (
              // Index in the key, not just ing.name — the same ingredient name
              // can legitimately appear twice in one recipe (e.g. "garlic" used
              // separately in a filling and a sauce), which isn't unique on its
              // own and produced real React key-collision warnings.
              <IngredientRow key={`${ing.name}-${i}`} ing={ing} showDivider={i > 0} />
            ))}
          </div>
        </section>

        <section>
          <h2 className="mb-3 font-editorial text-[21px] font-semibold italic leading-[1.2] text-text">Steps</h2>
          <div className="flex flex-col gap-2">
            {recipe.steps.map((step) => (
              <RevealedStepCard key={step.index} step={step} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
