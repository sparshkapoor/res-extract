import type { CSSProperties } from "react";

// csstype (the basis for React's CSSProperties) doesn't type custom properties,
// so this is the one sanctioned cast site for --stagger-index — see DESIGN.md
// "Motion": entrance stagger is 60ms per sibling via this property.
export function staggerStyle(index: number): CSSProperties {
  return { "--stagger-index": index } as unknown as CSSProperties;
}
