import { neon } from "@neondatabase/serverless";

if (!process.env.DATABASE_URL) {
  throw new Error(
    "DATABASE_URL is not set. Add it to .env.local for local dev, " +
      "or as a Vercel Environment Variable for deployments."
  );
}

// Neon's HTTP driver: no persistent connection to manage, safe for a public
// unauthenticated page under arbitrary concurrent serverless invocations.
export const sql = neon(process.env.DATABASE_URL);
