"use client";

import { useTransition } from "react";
import { useRouter } from "next/navigation";

// Mirrors dashboard.py's manual 🔄 button. Uses useTransition so the
// previous render stays visible while refreshing — no skeleton, no flash
// (dataviz skill's "refetch keeps the frame" rule).
export default function RefreshButton() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  return (
    <button
      type="button"
      onClick={() => startTransition(() => router.refresh())}
      disabled={isPending}
      style={{
        background: "var(--surface-1)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        padding: "8px 14px",
        fontSize: 13,
        whiteSpace: "nowrap",
        color: "var(--text-primary)",
        cursor: isPending ? "default" : "pointer",
        opacity: isPending ? 0.6 : 1,
      }}
    >
      {isPending ? "Refreshing…" : "🔄 Refresh"}
    </button>
  );
}
