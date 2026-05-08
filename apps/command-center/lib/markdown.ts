/**
 * Markdown → safe HTML — single source of truth for rendering agent
 * messages anywhere in the app.
 *
 * Two render targets share this:
 *   - Chat bubble (apps/command-center/components/ChatWidget.tsx) — was
 *     plain text + fenced code only; now headings/bold/italic/lists/
 *     blockquotes/links render the same as the export so what you see
 *     equals what you download.
 *   - Download menu (apps/command-center/components/chat/MessageDownloadMenu.tsx)
 *     for HTML / PDF export.
 *
 * SECURITY: this is the only place an agent message becomes HTML in
 * the app. The input is HTML-escaped FIRST, then markdown patterns are
 * applied to the escaped string. Markdown syntax characters (#, *, -,
 * `, [, ], _) survive escaping; embedded HTML becomes literal text.
 * Link hrefs are filtered against javascript: / data: / vbscript: /
 * file: schemes. Don't replace the escape step. Don't switch to
 * dangerouslySetInnerHTML on raw input.
 */

export function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeHref(raw: string): string {
  // After escapeHtml, raw is already HTML-encoded. Decode just enough
  // to sanity-check the scheme.
  const decoded = raw.replace(/&amp;/g, "&");
  if (/^\s*(javascript|data|vbscript|file):/i.test(decoded)) return "#";
  return raw;
}

export function mdToHtml(md: string): string {
  // 1) Escape the WHOLE input upfront. Markdown syntax chars (`*-#[]>`
  //    etc) are preserved; HTML-injection chars are neutralized.
  let body = escapeHtml(md);

  // 2) Pull out fenced code blocks BEFORE other patterns so backticks
  //    inside them don't trigger inline-code matching. After escapeHtml
  //    the original ``` is still ```, and the contents are already
  //    escaped — so we don't double-escape.
  const codeBlocks: string[] = [];
  body = body.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
    const safeLang = String(lang || "text").replace(/[^a-z0-9_-]/gi, "");
    codeBlocks.push(`<pre><code class="language-${safeLang}">${code}</code></pre>`);
    return ` CODEBLOCK${codeBlocks.length - 1} `;
  });

  // 3) Block-level patterns. Blockquote `>` got escaped to `&gt;`.
  body = body.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  body = body.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  body = body.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  body = body.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // 4) Lists (very light: contiguous - or 1. lines).
  body = body.replace(/(?:^|\n)((?:- .+(?:\n|$))+)/g, (_m, block: string) => {
    const items = block
      .trim()
      .split(/\n/)
      .map((l) => l.replace(/^- /, "").trim())
      .map((l) => `<li>${l}</li>`)
      .join("");
    return `\n<ul>${items}</ul>`;
  });
  body = body.replace(/(?:^|\n)((?:\d+\. .+(?:\n|$))+)/g, (_m, block: string) => {
    const items = block
      .trim()
      .split(/\n/)
      .map((l) => l.replace(/^\d+\. /, "").trim())
      .map((l) => `<li>${l}</li>`)
      .join("");
    return `\n<ol>${items}</ol>`;
  });

  // 5) Inline patterns. Capture groups are already HTML-escaped.
  body = body.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  body = body.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  body = body.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>");
  body = body.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, text: string, url: string) => {
    return `<a href="${safeHref(url)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  });

  // 6) Paragraphs.
  body = body
    .split(/\n{2,}/)
    .map((chunk) => {
      const trimmed = chunk.trim();
      if (!trimmed) return "";
      if (/^<(h\d|ul|ol|pre|blockquote)/.test(trimmed)) return trimmed;
      return `<p>${trimmed.replace(/\n/g, "<br/>")}</p>`;
    })
    .join("\n");

  // 7) Restore code blocks.
  body = body.replace(/ CODEBLOCK(\d+) /g, (_m, idx) => codeBlocks[Number(idx)]);

  return body;
}
