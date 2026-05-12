import fs from "node:fs/promises";
import path from "node:path";
import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft, BookOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const dynamic = "force-dynamic";

/**
 * /playbook/onboarding — operator-facing V6.0 SOPs rendered from
 * docs/playbooks/*.md so non-technical clients can read them in the
 * dashboard without opening the repo.
 *
 * The four files are loaded at build time; updating the markdown +
 * redeploying is the canonical update path.
 */

const PLAYBOOK_DIR = path.join(process.cwd(), "..", "..", "docs", "playbooks");

const ORDER = [
  "01-getting-started.md",
  "02-safe-interaction.md",
  "03-when-to-call-cc.md",
  "04-pause-and-rollback.md",
];

async function loadPlaybook(): Promise<Array<{ slug: string; title: string; body: string }>> {
  const out: Array<{ slug: string; title: string; body: string }> = [];
  for (const filename of ORDER) {
    const filePath = path.join(PLAYBOOK_DIR, filename);
    try {
      const raw = await fs.readFile(filePath, "utf-8");
      // Title is the first H1 line; fall back to filename without prefix.
      const titleMatch = raw.match(/^#\s+(.+?)\s*$/m);
      const title = titleMatch
        ? titleMatch[1]
        : filename.replace(/^\d+-/, "").replace(/\.md$/, "").replace(/-/g, " ");
      out.push({ slug: filename.replace(/\.md$/, ""), title, body: raw });
    } catch {
      // Missing file is non-fatal — render a placeholder card.
      out.push({
        slug: filename.replace(/\.md$/, ""),
        title: filename,
        body: `_Playbook file \`docs/playbooks/${filename}\` is missing. Run the setup wizard or pull the latest from the OASIS repo._`,
      });
    }
  }
  return out;
}

export default async function PlaybookOnboardingPage() {
  const sections = await loadPlaybook();

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider text-fg-dim hover:text-accent transition"
      >
        <ArrowLeft size={12} />
        Back to Playbook
      </Link>

      <PageHeader
        title="Operator Onboarding"
        subtitle="Four short SOPs covering what your agent does, what's safe to ask, when to escalate, and how to pause."
        action={<Tag tone="accent">v6.0</Tag>}
      />

      {sections.map((section) => (
        <Card key={section.slug} id={section.slug}>
          <article className="prose prose-invert prose-sm max-w-none
                              prose-headings:text-fg prose-headings:font-bold
                              prose-h1:text-xl prose-h1:mb-3
                              prose-h2:text-base prose-h2:mt-6 prose-h2:mb-2 prose-h2:uppercase prose-h2:tracking-wider prose-h2:text-fg-muted
                              prose-p:text-fg-muted prose-p:leading-relaxed
                              prose-li:text-fg-muted prose-li:my-0.5
                              prose-code:text-accent prose-code:bg-bg-elev prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono
                              prose-pre:bg-bg-elev prose-pre:border prose-pre:border-bg-border
                              prose-strong:text-fg prose-strong:font-bold
                              prose-a:text-accent prose-a:no-underline hover:prose-a:underline">
            <div className="flex items-center gap-2 mb-3 text-xs text-fg-dim uppercase tracking-wider not-prose">
              <BookOpen size={12} />
              <span className="font-mono">{section.slug}</span>
            </div>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {section.body}
            </ReactMarkdown>
          </article>
        </Card>
      ))}
    </div>
  );
}
