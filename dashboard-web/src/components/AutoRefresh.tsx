"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AUTO_REFRESH_MS } from "@/lib/config";

// Render-nothing component: re-runs the Server Component tree on an
// interval so the dashboard stays roughly live without a full page reload
// or any client-side data-fetching code (see plan: "no auth, periodic
// refresh, simplicity preferred").
export default function AutoRefresh() {
  const router = useRouter();

  useEffect(() => {
    const id = setInterval(() => router.refresh(), AUTO_REFRESH_MS);
    return () => clearInterval(id);
  }, [router]);

  return null;
}
