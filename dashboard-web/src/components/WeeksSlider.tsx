"use client";

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { WEEKS_MIN, WEEKS_MAX } from "@/lib/config";

export default function WeeksSlider({ value }: { value: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function onChange(next: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("weeks", String(next));
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13 }}>
      <span style={{ color: "var(--text-secondary)" }}>Weeks to show</span>
      <input
        type="range"
        min={WEEKS_MIN}
        max={WEEKS_MAX}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ accentColor: "var(--series-1)" }}
      />
      <span className="tabular-nums" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
        {value}
      </span>
    </label>
  );
}
