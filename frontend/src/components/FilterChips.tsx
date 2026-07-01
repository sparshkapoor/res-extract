import type { Platform } from "../types/recipe";

export type PlatformFilter = "all" | Platform;

interface FilterChipsProps {
  value: PlatformFilter;
  onChange: (value: PlatformFilter) => void;
}

const OPTIONS: { value: PlatformFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "youtube", label: "YouTube" },
  { value: "instagram", label: "Instagram" },
];

// The brief's "filter rail" adapted to a phone-width single-column PWA: a
// horizontal chip row, not a desktop sidebar. Flat, hairline — precision mode.
export function FilterChips({ value, onChange }: FilterChipsProps) {
  return (
    <div className="flex items-center gap-2 overflow-x-auto">
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`press-scale shrink-0 rounded-full border px-4 py-2 text-[13px] font-medium transition-colors ${
              active
                ? "border-accent bg-accent text-accent-on"
                : "border-hairline bg-surface-2 text-text-muted"
            }`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
