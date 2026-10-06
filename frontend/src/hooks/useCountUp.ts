import { useEffect, useRef, useState } from "react";

/** Animates a number from its previous value to `target` over `ms`.
 * Pure requestAnimationFrame — no dependency, cancels itself on unmount,
 * and jumps straight to the value on the very first render (no animating
 * in from zero, which would be misleading for a balance). */
export function useCountUp(target: number, ms = 600): number {
  const [value, setValue] = useState(target);
  const prev = useRef(target);
  const first = useRef(true);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      prev.current = target;
      setValue(target);
      return;
    }
    const from = prev.current;
    const delta = target - from;
    if (delta === 0) return;
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(from + delta * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else prev.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);

  return value;
}
