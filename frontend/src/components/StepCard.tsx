import { ImageBroken } from "@phosphor-icons/react";
import type { Step } from "../types/recipe";

interface StepCardProps {
  step: Step;
}

// Apple News recipe-card style: thumbnail and text sit side by side in one
// flat dark card — never a photo with text stacked/overlaid on top of it.
export function StepCard({ step }: StepCardProps) {
  return (
    <div className="flex items-start gap-3 rounded-lg bg-surface-tile-2 p-3">
      <div className="h-[76px] w-[76px] shrink-0 overflow-hidden rounded-md bg-surface-tile-1">
        {step.image_path ? (
          <img
            src={step.image_path}
            alt={`Step ${step.index}`}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageBroken size={24} className="text-body-muted" />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <span className="text-[11px] font-bold uppercase tracking-[0.06em] text-body-muted">
          Step {step.index}
        </span>
        <p className="mt-0.5 text-[15px] leading-snug text-body-on-dark">{step.instruction}</p>
      </div>
    </div>
  );
}
