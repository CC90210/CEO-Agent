/**
 * A3: Memory freshness reader. Reports whether the agent's brain/* and
 * memory/* state files are fresh or stale, per CLAUDE.md Rule 0 (>7 days
 * stale ⇒ treat as archived context, not current state).
 *
 * Reads mtime + the `last_updated:` frontmatter field if present; uses
 * whichever is more recent. Server-only — never exposes absolute paths
 * to client components.
 */

import { promises as fs } from "node:fs";
import path from "node:path";

export const STALE_DAYS = 7;

const REPO_ROOT = process.env.BRAVO_REPO_ROOT || path.resolve(process.cwd(), "..", "..");

const TRACKED_FILES: Array<{ label: string; rel: string }> = [
  { label: "brain/STATE.md", rel: path.join("brain", "STATE.md") },
  { label: "memory/ACTIVE_TASKS.md", rel: path.join("memory", "ACTIVE_TASKS.md") },
  { label: "memory/SESSION_LOG.md", rel: path.join("memory", "SESSION_LOG.md") },
  { label: "memory/MISTAKES.md", rel: path.join("memory", "MISTAKES.md") },
  { label: "memory/PATTERNS.md", rel: path.join("memory", "PATTERNS.md") },
];

export type MemoryFreshness = {
  label: string;
  exists: boolean;
  mtimeMs: number | null;
  ageDays: number | null;
  isStale: boolean;
  source: "frontmatter" | "mtime" | null;
};

let _cached: { rows: MemoryFreshness[]; at: number } | null = null;
const CACHE_MS = 30_000;

function _parseFrontmatterDate(text: string): number | null {
  // Match "last_updated: 2026-05-08" or "Last updated: 2026-05-08" — both forms
  // appear in the repo. Looks only in the first ~40 lines so we never read
  // body content.
  const head = text.split(/\r?\n/, 40).join("\n");
  const m = head.match(/^(?:last[_ ]updated|Last updated)\s*[:=]\s*([0-9]{4}-[0-9]{2}-[0-9]{2})/im);
  if (!m) return null;
  const t = Date.parse(m[1] + "T00:00:00Z");
  return Number.isFinite(t) ? t : null;
}

async function _readOne(label: string, abs: string): Promise<MemoryFreshness> {
  try {
    const stat = await fs.stat(abs);
    let frontmatterMs: number | null = null;
    try {
      // Read only the head — 4KB is plenty for any frontmatter we'd parse.
      const handle = await fs.open(abs, "r");
      try {
        const buf = Buffer.alloc(4096);
        const { bytesRead } = await handle.read(buf, 0, 4096, 0);
        const text = buf.toString("utf8", 0, bytesRead);
        frontmatterMs = _parseFrontmatterDate(text);
      } finally {
        await handle.close();
      }
    } catch {
      // ignore; fall through to mtime
    }
    const mtimeMs = stat.mtimeMs;
    const effectiveMs =
      frontmatterMs !== null && frontmatterMs > mtimeMs ? frontmatterMs : mtimeMs;
    const source: "frontmatter" | "mtime" =
      frontmatterMs !== null && frontmatterMs >= mtimeMs ? "frontmatter" : "mtime";
    const ageDays = (Date.now() - effectiveMs) / 86_400_000;
    return {
      label,
      exists: true,
      mtimeMs: effectiveMs,
      ageDays,
      isStale: ageDays > STALE_DAYS,
      source,
    };
  } catch {
    return {
      label,
      exists: false,
      mtimeMs: null,
      ageDays: null,
      isStale: false,
      source: null,
    };
  }
}

export async function getMemoryFreshness(): Promise<MemoryFreshness[]> {
  if (_cached && Date.now() - _cached.at < CACHE_MS) return _cached.rows;
  const rows = await Promise.all(
    TRACKED_FILES.map(({ label, rel }) => _readOne(label, path.join(REPO_ROOT, rel)))
  );
  _cached = { rows, at: Date.now() };
  return rows;
}

export function staleCount(rows: MemoryFreshness[]): number {
  return rows.filter((r) => r.isStale).length;
}

export function missingCount(rows: MemoryFreshness[]): number {
  return rows.filter((r) => !r.exists).length;
}
