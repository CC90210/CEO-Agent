/**
 * Shared SSE parser — `event:` + `data:` framed streams.
 *
 * Used by every server-side bit that consumes an SSE response body. Lives
 * here as a single source instead of being duplicated:
 *   - lib/providers.ts (Anthropic/OpenAI/Google/OpenRouter/Ollama adapters)
 *   - lib/cloud-tool-runner.ts (native Anthropic tool_use loop)
 *
 * The parser is generic over Anthropic's vs OpenAI's framing because both
 * use the same wire shape:
 *   event: NAME     ← optional; defaults to "message" (OpenAI omits it)
 *   data: JSON     ← may be `[DONE]` to signal end (OpenAI convention)
 *   <blank line>   ← frame separator
 *
 * Yields `{ event, data }` where data is either a parsed object, the raw
 * string (if JSON parse fails — keeps callers in control of strictness),
 * or the literal `"[DONE]"` sentinel.
 */

export type SSEFrame = { event: string; data: any };

export async function* parseSSE(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<SSEFrame> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (!dataLines.length) continue;
      const raw = dataLines.join("\n");
      if (raw === "[DONE]") {
        yield { event, data: "[DONE]" };
        continue;
      }
      try {
        yield { event, data: JSON.parse(raw) };
      } catch {
        yield { event, data: raw };
      }
    }
  }
}

/**
 * Read up to 500 chars from a Response body for use in an error message.
 * Swallows errors — this is best-effort surface area, not load-bearing.
 */
export async function safeText(r: Response): Promise<string> {
  try {
    return (await r.text()).slice(0, 500);
  } catch {
    return "";
  }
}
