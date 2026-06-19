import { useEffect, useRef } from 'react';

/**
 * Calls the callback every `delay` milliseconds.
 * Equivalent to setInterval but cleared automatically.
 */
export function useInterval(callback: () => void, delay: number | null) {
  const savedCallback = useRef<(() => void) | null>(null);

  // Remember the latest callback.
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  // Set up the interval.
  useEffect(() => {
    if (delay === null) {
      return;
    }
    const tick = () => {
      savedCallback.current?.();
    };
    const id = setInterval(tick, delay);
    return () => clearInterval(id);
  }, [delay]);
}