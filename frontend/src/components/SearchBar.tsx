import { MagnifyingGlass } from "@phosphor-icons/react";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

// Flat precision input — never blurred. Search/filter chrome lives outside the
// glass system entirely; see DESIGN.md "Elevation & Depth".
export function SearchBar({ value, onChange }: SearchBarProps) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-hairline bg-surface-2 px-4 py-2.5 transition-colors duration-200 ease-spring focus-within:border-accent">
      <MagnifyingGlass size={16} weight="bold" className="shrink-0 text-text-muted" />
      <input
        type="search"
        inputMode="search"
        placeholder="Search saved recipes"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-transparent text-[15px] text-text outline-none placeholder:text-text-faint"
      />
    </div>
  );
}
