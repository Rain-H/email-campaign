"use client";

import { useSyncExternalStore } from "react";

// Recharts sizes and labels are props, not CSS, so the phone breakpoint has to
// be readable from JS too. Keep this in sync with the 560px media query in
// src/app/globals.css.
export const NARROW_QUERY = "(max-width: 560px)";

// matchMedia is an external store, so it's read with useSyncExternalStore
// rather than useEffect + setState (which would cascade an extra render on
// every mount, and trips react-hooks/set-state-in-effect).
function subscribe(onStoreChange: () => void): () => void {
  const mql = window.matchMedia(NARROW_QUERY);
  mql.addEventListener("change", onStoreChange);
  return () => mql.removeEventListener("change", onStoreChange);
}

function getSnapshot(): boolean {
  return window.matchMedia(NARROW_QUERY).matches;
}

// There's no viewport during SSR. Returning false means the server HTML and the
// first client render agree (no hydration mismatch); React then immediately
// re-renders with the real value.
function getServerSnapshot(): boolean {
  return false;
}

export function useIsNarrow(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
