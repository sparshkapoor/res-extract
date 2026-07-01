import { ImageBroken } from "@phosphor-icons/react";
import type { Step } from "../types/recipe";

interface StepCardProps {
  step: Step;
  staggerIndex?: number;
}

// Flat precision card — thumbnail and text side by side, hairline border, no
// shadow/blur (this isn't a photo-backed glass surface, it's chrome around one).
export function StepCard({ step, staggerIndex = 0 }: StepCardProps) {
  return (
    <div
      className="animate-fade-in-up flex items-start gap-3 rounded-md border border-hairline bg-surface-2 p-3"
      style={{ "--stagger-index": staggerIndex }}
    >
      <div className="h-[76px] w-[76px] shrink-0 overflow-hidden rounded-sm bg-surface-1">
        {step.image_path ? (
          <img
            src={step.image_path}
            alt={`Step ${step.index}`}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            <ImageBroken size={24} className="text-text-muted" />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-accent">
          Step {step.index}
        </span>
        <p className="mt-0.5 text-[15px] leading-snug text-text">{step.instruction}</p>
      </div>
    </div>
  );
}
