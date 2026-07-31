import type { ReplyRow } from "@/types/dashboard";
import { formatShortDate } from "@/lib/format";

export default function RecentRepliesList({ replies }: { replies: ReplyRow[] }) {
  if (replies.length === 0) {
    return <div style={{ color: "var(--text-muted)", fontSize: 14 }}>No replies yet</div>;
  }

  return (
    <ul
      style={{
        listStyle: "none",
        // the UA's default list indent is 40px — real estate a phone can't spare
        margin: 0,
        padding: 0,
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      {replies.map((r, i) => (
        <li
          key={i}
          style={{ fontSize: 14, color: "var(--text-primary)", overflowWrap: "anywhere" }}
        >
          <span aria-hidden>{r.interested ? "✅" : "❌"}</span>{" "}
          <strong>{r.name}</strong>{" "}
          <span className="tabular-nums" style={{ color: "var(--text-muted)" }}>
            — {formatShortDate(r.repliedAt)}
          </span>
        </li>
      ))}
    </ul>
  );
}
