import type { IncomingMessage, ServerResponse } from "node:http";

import type { RunnerSession, SessionStore } from "./sessions.js";

export function attachSessionStream(
  req: IncomingMessage,
  res: ServerResponse,
  session: RunnerSession,
  store: SessionStore,
  corsHeaders: Record<string, string>
): void {
  const afterSeq = Number(req.headers["last-event-id"] || 0);

  res.writeHead(200, {
    ...corsHeaders,
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  });

  res.write(": connected\n\n");

  for (const event of store.replaySince(session.id, afterSeq)) {
    writeEvent(res, event.seq, event.type, event.data);
  }

  const unsubscribe = store.attach(session.id, (event) => {
    writeEvent(res, event.seq, event.type, event.data);
  });

  const heartbeat = setInterval(() => {
    res.write(`event: heartbeat\ndata: {"ts":"${new Date().toISOString()}"}\n\n`);
  }, 15000);

  req.on("close", () => {
    clearInterval(heartbeat);
    unsubscribe();
    res.end();
  });
}

function writeEvent(
  res: ServerResponse,
  seq: number,
  type: string,
  data: unknown
): void {
  res.write(`id: ${seq}\n`);
  res.write(`event: ${type}\n`);
  res.write(`data: ${JSON.stringify(data)}\n\n`);
}
