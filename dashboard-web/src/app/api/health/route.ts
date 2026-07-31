import { sql } from "@/lib/db";

export async function GET() {
  const start = Date.now();
  try {
    await sql`SELECT 1`;
    return Response.json({ ok: true, latencyMs: Date.now() - start });
  } catch (err) {
    return Response.json(
      { ok: false, error: err instanceof Error ? err.message : String(err) },
      { status: 500 }
    );
  }
}
