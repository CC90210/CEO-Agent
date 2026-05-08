"use client";

/**
 * MessageDownloadMenu — pulldown rendered next to the copy button on
 * completed assistant messages. Lets CC export the agent's reply as
 * Markdown, HTML, or PDF without server round-trip.
 *
 * Approach (deliberately zero-dep):
 *   - MD: trivially the source of truth — Blob, download, done.
 *   - HTML: render the markdown to a simple HTML doc with embedded styles
 *     so the file looks decent when opened locally or shared.
 *   - PDF: open a print window with the rendered HTML and call
 *     window.print(). The user gets the browser's native "Save as PDF"
 *     dialog. No puppeteer, no jsPDF, no html2pdf.js — just print CSS.
 *
 * Rationale: the model returns markdown. If we add a PDF library, the
 * bundle balloons (jsPDF + html2canvas ≈ 600KB) and we still have to
 * reimplement formatting. window.print → "Save as PDF" is what every
 * pro doc tool (Notion, Linear, GitHub gists) actually does for
 * print-quality exports. Cost: zero. Quality: identical to print preview.
 */

import { useState } from "react";
import { Download, Check, FileText, FileCode, Printer } from "lucide-react";
// Single canonical markdown renderer — same logic the chat bubble uses,
// so what the operator sees in the chat equals what they download.
import { mdToHtml, escapeHtml } from "@/lib/markdown";

const PRINT_STYLES = `
  @media print {
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; line-height: 1.6; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #111; }
    h1, h2, h3 { line-height: 1.3; margin-top: 1.5em; }
    h1 { font-size: 1.6em; border-bottom: 1px solid #ddd; padding-bottom: 0.3em; }
    h2 { font-size: 1.3em; }
    h3 { font-size: 1.1em; }
    code { background: #f4f4f4; padding: 0.15em 0.35em; border-radius: 3px; font-size: 0.9em; }
    pre { background: #f4f4f4; padding: 1em; border-radius: 6px; overflow-x: auto; }
    pre code { background: transparent; padding: 0; }
    blockquote { border-left: 3px solid #ccc; padding-left: 1em; color: #555; font-style: italic; }
    a { color: #0366d6; }
    table { border-collapse: collapse; width: 100%; margin: 1em 0; }
    th, td { border: 1px solid #ddd; padding: 0.5em; text-align: left; }
    th { background: #f4f4f4; }
    ul, ol { padding-left: 1.5em; }
    .header-meta { font-size: 0.85em; color: #666; border-bottom: 1px solid #eee; padding-bottom: 0.5em; margin-bottom: 1em; }
    @page { margin: 0.75in; }
  }
  @media screen {
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; line-height: 1.6; max-width: 720px; margin: 2rem auto; padding: 0 1rem; color: #111; background: #fff; }
    h1, h2, h3 { line-height: 1.3; margin-top: 1.5em; }
    h1 { font-size: 1.6em; border-bottom: 1px solid #ddd; padding-bottom: 0.3em; }
    h2 { font-size: 1.3em; }
    h3 { font-size: 1.1em; }
    code { background: #f4f4f4; padding: 0.15em 0.35em; border-radius: 3px; font-size: 0.9em; }
    pre { background: #f4f4f4; padding: 1em; border-radius: 6px; overflow-x: auto; }
    pre code { background: transparent; padding: 0; }
    blockquote { border-left: 3px solid #ccc; padding-left: 1em; color: #555; font-style: italic; }
    a { color: #0366d6; }
    .header-meta { font-size: 0.85em; color: #666; border-bottom: 1px solid #eee; padding-bottom: 0.5em; margin-bottom: 1em; }
  }
`;

function buildHtmlDoc(content: string, agent: string): string {
  const renderedAt = new Date().toLocaleString();
  const inner = mdToHtml(content);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>${escapeHtml(agent.toUpperCase())} — chat reply</title>
<style>${PRINT_STYLES}</style>
</head>
<body>
<div class="header-meta">From <strong>${escapeHtml(agent.toUpperCase())}</strong> · ${escapeHtml(renderedAt)}</div>
${inner}
</body>
</html>`;
}

function downloadBlob(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function safeSlug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "reply";
}

export function MessageDownloadMenu({
  content,
  agent,
}: {
  content: string;
  agent: string;
}) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState<"md" | "html" | "pdf" | null>(null);

  function flashDone(kind: "md" | "html" | "pdf"): void {
    setDone(kind);
    setOpen(false);
    setTimeout(() => setDone(null), 1500);
  }

  function downloadMd(): void {
    const stamp = new Date().toISOString().slice(0, 10);
    const firstLine = content.split("\n").find((l) => l.trim()) || "reply";
    const name = `${stamp}-${agent}-${safeSlug(firstLine)}.md`;
    downloadBlob(name, content, "text/markdown;charset=utf-8");
    flashDone("md");
  }

  function downloadHtml(): void {
    const html = buildHtmlDoc(content, agent);
    const stamp = new Date().toISOString().slice(0, 10);
    const firstLine = content.split("\n").find((l) => l.trim()) || "reply";
    const name = `${stamp}-${agent}-${safeSlug(firstLine)}.html`;
    downloadBlob(name, html, "text/html;charset=utf-8");
    flashDone("html");
  }

  function printPdf(): void {
    const html = buildHtmlDoc(content, agent);
    // Use a hidden iframe so we don't lose the chat window's state. Some
    // pop-up blockers nuke window.open() too.
    const iframe = document.createElement("iframe");
    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    document.body.appendChild(iframe);
    const doc = iframe.contentDocument;
    if (!doc) {
      document.body.removeChild(iframe);
      return;
    }
    doc.open();
    doc.write(html);
    doc.close();
    // Wait for the iframe to render before invoking print.
    setTimeout(() => {
      try {
        iframe.contentWindow?.focus();
        iframe.contentWindow?.print();
      } finally {
        // Leave it mounted briefly; some browsers detach the print
        // dialog if we yank the iframe immediately. Cleanup at 30s.
        setTimeout(() => {
          if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
        }, 30_000);
      }
    }, 250);
    flashDone("pdf");
  }

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="hover:text-accent transition-colors inline-flex items-center gap-0.5"
        title="Download this reply"
      >
        {done ? <Check className="w-3 h-3 text-status-engaged" /> : <Download className="w-3 h-3" />}
        {done ? `${done.toUpperCase()} ✓` : "download"}
      </button>
      {open && (
        <div
          className="absolute z-20 mt-1 right-0 w-44 rounded-md border border-bg-border bg-bg-deep shadow-lg overflow-hidden"
          onMouseLeave={() => setOpen(false)}
        >
          <button
            type="button"
            onClick={downloadMd}
            className="w-full text-left px-3 py-2 text-xs text-fg-muted hover:bg-bg-elev/60 hover:text-fg flex items-center gap-2"
          >
            <FileText className="w-3.5 h-3.5" /> Markdown (.md)
          </button>
          <button
            type="button"
            onClick={downloadHtml}
            className="w-full text-left px-3 py-2 text-xs text-fg-muted hover:bg-bg-elev/60 hover:text-fg flex items-center gap-2"
          >
            <FileCode className="w-3.5 h-3.5" /> HTML (.html)
          </button>
          <button
            type="button"
            onClick={printPdf}
            className="w-full text-left px-3 py-2 text-xs text-fg-muted hover:bg-bg-elev/60 hover:text-fg flex items-center gap-2"
          >
            <Printer className="w-3.5 h-3.5" /> PDF (print)
          </button>
        </div>
      )}
    </div>
  );
}
