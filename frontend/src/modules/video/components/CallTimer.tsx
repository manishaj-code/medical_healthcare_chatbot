import { useCallTimer } from "../hooks/useCallTimer";

interface Props {
  active: boolean;
  className?: string;
}

export function CallTimer({ active, className = "" }: Props) {
  const duration = useCallTimer(active);
  if (!active) return null;

  return (
    <span
      className={`video-call-timer${className ? ` ${className}` : ""}`}
      aria-live="off"
      aria-label={`Call duration ${duration}`}
    >
      {duration}
    </span>
  );
}
