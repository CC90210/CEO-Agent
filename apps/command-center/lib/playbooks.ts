/**
 * Playbook markdown loader.
 *
 * Server-only. Reads files from apps/command-center/content/playbooks/<slug>.md,
 * extracts the H1 title (first line starting with "# "), and returns the body
 * for client-side rendering via <ReactMarkdown remarkPlugins={[remarkGfm]}>.
 *
 * No frontmatter parser — the existing playbooks use plain markdown with H1
 * as the title. Keeping it simple avoids adding gray-matter just for a few
 * files.
 */

import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

export type PlaybookSlug = string;

export type PlaybookFile = {
  slug: PlaybookSlug;
  title: string;
  body: string;
  audience: "operator" | "client" | "internal";
};

const CONTENT_DIR = path.join(process.cwd(), "content", "playbooks");

// Audience inferred from the file's # heading suffix / known slugs. Keeps the
// content files free of frontmatter while still letting the index page filter.
function inferAudience(slug: string, body: string): PlaybookFile["audience"] {
  const lowered = `${slug} ${body.slice(0, 200)}`.toLowerCase();
  if (lowered.includes("customer-facing") || lowered.includes("verbatim script")) {
    return "client";
  }
  if (lowered.includes("internal-only") || lowered.includes("operator dev")) {
    return "internal";
  }
  return "operator";
}

function extractTitle(body: string, fallback: string): string {
  const firstH1 = body.match(/^#\s+(.+?)\s*$/m);
  return firstH1?.[1]?.trim() || fallback;
}

export async function listPlaybooks(): Promise<PlaybookFile[]> {
  let entries: string[] = [];
  try {
    entries = await readdir(CONTENT_DIR);
  } catch {
    return [];
  }
  const files = entries.filter((n) => n.endsWith(".md") && n !== "INDEX.md").sort();
  const out: PlaybookFile[] = [];
  for (const name of files) {
    const slug = name.replace(/\.md$/, "");
    try {
      const body = await readFile(path.join(CONTENT_DIR, name), "utf8");
      out.push({
        slug,
        title: extractTitle(body, slug),
        body,
        audience: inferAudience(slug, body),
      });
    } catch {
      // Skip unreadable file but don't crash the index.
    }
  }
  return out;
}

export async function loadPlaybook(slug: PlaybookSlug): Promise<PlaybookFile | null> {
  // Defense against path traversal: slug must be a simple filename component.
  if (!/^[a-zA-Z0-9_\-]+$/.test(slug)) return null;
  try {
    const body = await readFile(path.join(CONTENT_DIR, `${slug}.md`), "utf8");
    return {
      slug,
      title: extractTitle(body, slug),
      body,
      audience: inferAudience(slug, body),
    };
  } catch {
    return null;
  }
}
