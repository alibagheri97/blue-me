import { quantity } from "../lib/format";

interface PointSplitProps {
  positive: number;
  negative: number;
  compact?: boolean;
}

export function PointSplit({ positive, negative, compact = false }: PointSplitProps) {
  const positiveValue = Math.max(0, positive);
  const negativeValue = Math.abs(Math.min(0, negative));

  return (
    <span
      className={`point-split ${compact ? "is-compact" : ""}`}
      role="group"
      aria-label={`امتیاز مثبت ${positiveValue} و امتیاز منفی ${negativeValue}`}
    >
      <span className="point-split-value is-positive" title="امتیاز مثبت">
        <small>+</small><strong>{quantity(positiveValue)}</strong>
      </span>
      <span className="point-split-value is-negative" title="امتیاز منفی">
        <small>−</small><strong>{quantity(negativeValue)}</strong>
      </span>
    </span>
  );
}
