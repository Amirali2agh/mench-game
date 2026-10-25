/**
 * Motion preferences.
 *
 * Read at the moment an animation starts rather than at module load, so a
 * change of the OS setting (or DevTools emulation) applies to the next move
 * without a reload.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
