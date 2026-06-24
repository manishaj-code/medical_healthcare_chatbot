import type { CSSProperties, ReactNode } from "react";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  className?: string;
  circle?: boolean;
  rounded?: boolean;
  style?: CSSProperties;
}

export function Skeleton({
  width,
  height,
  className = "",
  circle,
  rounded,
  style,
}: SkeletonProps) {
  const classes = [
    "ui-skeleton",
    circle ? "ui-skeleton--circle" : "",
    rounded ? "ui-skeleton--rounded" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={classes}
      style={{ width, height, ...style }}
      aria-hidden="true"
    />
  );
}

export function SkeletonPage({
  children,
  label = "Loading content",
}: {
  children: ReactNode;
  label?: string;
}) {
  return (
    <div className="ui-skeleton-page" role="status" aria-live="polite" aria-busy="true">
      <span className="ui-sr-only">{label}</span>
      {children}
    </div>
  );
}
