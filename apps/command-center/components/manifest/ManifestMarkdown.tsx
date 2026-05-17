import { Card } from "@/components/Card";
import type { ManifestPageDef } from "@/lib/manifest/schema";

type Props = {
  page: ManifestPageDef;
};

/**
 * Inline-markdown page — for manifest entries with kind="markdown".
 * Content comes from `page.config.body` (a markdown-ish string).
 *
 * Renders a small subset of markdown without pulling in a parser
 * library: `## headers`, `**bold**`, `- bullets` / `* bullets`,
 * numbered lists `1. `, and blank-line-separated paragraphs. That's
 * exactly what the SunBiz playbook (and the OASIS HQ inline playbook)
 * actually use — anything richer goes through a real .md file rendered
 * by /playbook/[slug] instead.
 *
 * Why not a full markdown lib: pulling in react-markdown + remark
 * adds ~70kB for a feature only used on operator-facing static guidance
 * pages. The renderer below is ~50 lines, handles every construct the
 * current operator copy uses, and renders cleanly within the prose
 * Tailwind styles.
 */
export function ManifestMarkdown({ page }: Props) {
  const body =
    (typeof page.config?.body === "string" && page.config.body) ||
    "_This page has no body yet._";

  return (
    <Card title={page.label}>
      <div className="prose prose-invert max-w-none text-fg-muted leading-relaxed">
        {renderMarkdownBlocks(body)}
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------------- *
 * Tiny markdown block renderer — paragraphs, headers, lists.
 * ----------------------------------------------------------------- */

type Block =
  | { kind: "h2"; text: string }
  | { kind: "h3"; text: string }
  | { kind: "p"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "ol"; items: string[] };

function renderMarkdownBlocks(src: string): React.ReactNode {
  const blocks = parseMarkdown(src);
  return blocks.map((b, i) => {
    if (b.kind === "h2") {
      return (
        <h2 key={i} className="text-base font-bold text-fg mt-5 first:mt-0 mb-2">
          {renderInline(b.text)}
        </h2>
      );
    }
    if (b.kind === "h3") {
      return (
        <h3 key={i} className="text-sm font-bold text-fg mt-4 first:mt-0 mb-1.5">
          {renderInline(b.text)}
        </h3>
      );
    }
    if (b.kind === "ul") {
      return (
        <ul key={i} className="list-disc pl-5 space-y-1 my-2">
          {b.items.map((item, j) => (
            <li key={j}>{renderInline(item)}</li>
          ))}
        </ul>
      );
    }
    if (b.kind === "ol") {
      return (
        <ol key={i} className="list-decimal pl-5 space-y-1 my-2">
          {b.items.map((item, j) => (
            <li key={j}>{renderInline(item)}</li>
          ))}
        </ol>
      );
    }
    // p
    return (
      <p key={i} className="my-2 first:mt-0 last:mb-0">
        {renderInline(b.text)}
      </p>
    );
  });
}

function parseMarkdown(src: string): Block[] {
  const lines = src.split(/\r?\n/);
  const blocks: Block[] = [];
  let buffer: string[] = [];
  let listItems: string[] = [];
  let listKind: "ul" | "ol" | null = null;

  const flushPara = () => {
    if (buffer.length === 0) return;
    blocks.push({ kind: "p", text: buffer.join(" ").trim() });
    buffer = [];
  };
  const flushList = () => {
    if (listItems.length === 0 || listKind === null) return;
    blocks.push({ kind: listKind, items: listItems });
    listItems = [];
    listKind = null;
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line === "") {
      flushPara();
      flushList();
      continue;
    }
    const h2 = /^##\s+(.*)/.exec(line);
    if (h2) {
      flushPara();
      flushList();
      blocks.push({ kind: "h2", text: h2[1] });
      continue;
    }
    const h3 = /^###\s+(.*)/.exec(line);
    if (h3) {
      flushPara();
      flushList();
      blocks.push({ kind: "h3", text: h3[1] });
      continue;
    }
    const ul = /^[-*]\s+(.*)/.exec(line);
    if (ul) {
      flushPara();
      if (listKind && listKind !== "ul") flushList();
      listKind = "ul";
      listItems.push(ul[1]);
      continue;
    }
    const ol = /^(\d+)\.\s+(.*)/.exec(line);
    if (ol) {
      flushPara();
      if (listKind && listKind !== "ol") flushList();
      listKind = "ol";
      listItems.push(ol[2]);
      continue;
    }
    // Plain paragraph line.
    flushList();
    buffer.push(line);
  }
  flushPara();
  flushList();
  return blocks;
}

/**
 * Inline pass — bold (**text**), italic (*text*), code (`text`), and
 * autolinks ([label](url)). Returns an array of React nodes so callers
 * can drop it into <p>/<li>/<h2> children.
 */
function renderInline(text: string): React.ReactNode {
  const nodes: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  const pattern = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)/;
  while (remaining.length > 0) {
    const m = pattern.exec(remaining);
    if (!m) {
      nodes.push(remaining);
      break;
    }
    if (m.index > 0) nodes.push(remaining.slice(0, m.index));
    if (m[1] !== undefined) {
      nodes.push(<strong key={key++} className="text-fg font-bold">{m[1]}</strong>);
    } else if (m[2] !== undefined) {
      nodes.push(
        <code key={key++} className="font-mono text-[12.5px] text-fg bg-bg-deep px-1 py-0.5 rounded">
          {m[2]}
        </code>,
      );
    } else if (m[3] !== undefined && m[4] !== undefined) {
      nodes.push(
        <a
          key={key++}
          href={m[4]}
          className="text-accent hover:text-accent/80 underline underline-offset-2"
          target={m[4].startsWith("http") ? "_blank" : undefined}
          rel={m[4].startsWith("http") ? "noopener noreferrer" : undefined}
        >
          {m[3]}
        </a>,
      );
    }
    remaining = remaining.slice(m.index + m[0].length);
  }
  return nodes;
}
