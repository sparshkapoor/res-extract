interface SkeletonProps {
  className?: string;
}

// Shimmer sweep, never a flat opacity pulse — size it via className to match
// exactly what it's standing in for (a grid tile, an ingredient row, ...).
export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`skeleton-shimmer rounded-md ${className}`} />;
}
