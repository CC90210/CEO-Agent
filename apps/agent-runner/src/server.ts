import "dotenv/config";

import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { URL } from "node:url";

import {
  buildCorsHeaders,
  requireAuth,
  resolveCorsOrigin,
  type AuthenticatedContext,
} from "./auth.js";
import {
  listWorkspaceTree,
  readWorkspaceFile,
  resolveWorkspaceRoot,
  watchWorkspaceTree,
} from "./files.js";
import { attachSessionStream } from "./sse.js";
import { startSessionRun } from "./spawner.js";
import {
  SessionStore,
  type ChatStartRequest,
} from "./sessions.js";
import { z } from "zod";

const sessionStore = new SessionStore();
const PROVIDER_VALUES = [
  "claude_code",
  "claude_api",
  "openai",
  "gemini",
  "codex",
] as const;
const OPERATION_VALUES = [
  "chat",
  "task",
  "review",
  "adversarial_review",
] as const;
const WRITE_VALUES = [
  "read_only",
  "approval_required",
  "approved",
] as const;

const StartChatSchema = z.object({
  agentKey: z.string().min(1),
  provider: z.enum(PROVIDER_VALUES),
  model: z.string().min(1),
  prompt: z.string().default(""),
  operationMode: z.enum(OPERATION_VALUES).default("chat"),
  writeMode: z.enum(WRITE_VALUES).default("read_only"),
  parentSessionId: z.string().uuid().optional().nullable(),
  watchFiles: z.boolean().default(true),
});

const WriteRequestSchema = z.object({
  sessionId: z.string().uuid(),
  relativePath: z.string().min(1),
  reason: z.string().min(1),
  patch: z.string().min(1),
});

const ApproveWriteSchema = z.object({
  sessionId: z.string().uuid(),
  requestSeq: z.number().int().positive(),
});

createServer(async (req, res) => {
  try {
    const url = new URL(req.url || "/", "http://runner.local");
    const origin = resolveCorsOrigin(req);
    const corsHeaders = buildCorsHeaders(origin);

    if (req.method === "OPTIONS") {
      return writeJson(res, 204, { ok: true }, corsHeaders);
    }

    if (req.method === "GET" && url.pathname === "/healthz") {
      return writeJson(
        res,
        200,
        {
          ok: true,
          service: "oasis-agent-runner",
          ts: new Date().toISOString(),
        },
        corsHeaders
      );
    }

    if (!url.pathname.startsWith("/v1/")) {
      return writeJson(res, 404, { error: "not_found" }, corsHeaders);
    }

    const auth = await requireAuth(req);

    if (req.method === "POST" && url.pathname === "/v1/chat") {
      return handleStartChat(req, res, corsHeaders, auth);
    }

    const streamMatch = url.pathname.match(/^\/v1\/chat\/([0-9a-f-]+)\/stream$/i);
    if (req.method === "GET" && streamMatch) {
      return handleStream(res, req, corsHeaders, auth, streamMatch[1]);
    }

    if (req.method === "GET" && url.pathname === "/v1/files/tree") {
      return handleFileTree(url, res, corsHeaders, auth);
    }

    if (req.method === "GET" && url.pathname === "/v1/files/blob") {
      return handleFileRead(url, res, corsHeaders, auth);
    }

    if (req.method === "POST" && url.pathname === "/v1/files/write-requests") {
      return handleWriteRequest(req, res, corsHeaders, auth);
    }

    if (req.method === "POST" && url.pathname === "/v1/files/write-requests/approve") {
      return handleWriteApprove(req, res, corsHeaders, auth);
    }

    return writeJson(res, 404, { error: "not_found" }, corsHeaders);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown runner error.";
    return writeJson(
      res,
      401,
      { error: "runner_request_rejected", message },
      buildCorsHeaders(resolveCorsOrigin(req))
    );
  }
}).listen(Number(process.env.RUNNER_PORT || 8787), "0.0.0.0", () => {
  process.stdout.write(
    `agent-runner listening on :${process.env.RUNNER_PORT || 8787}\n`
  );
});

async function handleStartChat(
  req: IncomingMessage,
  res: ServerResponse,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext
): Promise<void> {
  const body = StartChatSchema.parse(await readJson(req));
  const workspaceRoot = resolveWorkspaceRoot(body.agentKey, auth.tenantSlug);
  const session = await sessionStore.createSession(
    auth,
    body as ChatStartRequest,
    workspaceRoot
  );

  if (body.watchFiles) {
    const stopWatching = await watchWorkspaceTree(workspaceRoot, (event) => {
      void sessionStore.pushEvent(session.id, event.type, event, true);
    });
    sessionStore.attach(session.id, (event) => {
      if (event.type === "runner.cancelled" || event.type === "runner.failed") {
        stopWatching();
      }
    });
  }

  void startSessionRun(auth, session, sessionStore).catch(async (error) => {
    const message =
      error instanceof Error ? error.message : "Unknown session start failure.";
    await sessionStore.fail(session.id, message);
  });

  writeJson(
    res,
    202,
    {
      sessionId: session.id,
      status: session.status,
      streamUrl: `/v1/chat/${session.id}/stream`,
    },
    corsHeaders
  );
}

function handleStream(
  res: ServerResponse,
  req: IncomingMessage,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext,
  sessionId: string
): void {
  const session = sessionStore.get(sessionId);
  if (!session || session.tenantId !== auth.tenantId) {
    writeJson(res, 404, { error: "unknown_session" }, corsHeaders);
    return;
  }
  attachSessionStream(req, res, session, sessionStore, corsHeaders);
}

async function handleFileTree(
  url: URL,
  res: ServerResponse,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext
): Promise<void> {
  const agentKey = url.searchParams.get("agentKey");
  if (!agentKey) {
    return writeJson(res, 400, { error: "agentKey_required" }, corsHeaders);
  }
  const workspaceRoot = resolveWorkspaceRoot(agentKey, auth.tenantSlug);
  const maxDepth = Number(url.searchParams.get("depth") || "4");
  const tree = await listWorkspaceTree(workspaceRoot, { maxDepth });
  writeJson(res, 200, { root: workspaceRoot, tree }, corsHeaders);
}

async function handleFileRead(
  url: URL,
  res: ServerResponse,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext
): Promise<void> {
  const agentKey = url.searchParams.get("agentKey");
  const relativePath = url.searchParams.get("path");
  if (!agentKey || !relativePath) {
    return writeJson(res, 400, { error: "agentKey_and_path_required" }, corsHeaders);
  }
  const workspaceRoot = resolveWorkspaceRoot(agentKey, auth.tenantSlug);
  const content = await readWorkspaceFile(workspaceRoot, relativePath);
  writeJson(res, 200, { path: relativePath, content }, corsHeaders);
}

async function handleWriteRequest(
  req: IncomingMessage,
  res: ServerResponse,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext
): Promise<void> {
  const body = WriteRequestSchema.parse(await readJson(req));
  const session = sessionStore.get(body.sessionId);
  if (!session || session.tenantId !== auth.tenantId) {
    return writeJson(res, 404, { error: "unknown_session" }, corsHeaders);
  }
  await sessionStore.markApprovalRequired(session.id, {
    relativePath: body.relativePath,
    reason: body.reason,
    patch: body.patch,
  });
  writeJson(res, 202, { ok: true, status: "waiting_approval" }, corsHeaders);
}

async function handleWriteApprove(
  req: IncomingMessage,
  res: ServerResponse,
  corsHeaders: Record<string, string>,
  auth: AuthenticatedContext
): Promise<void> {
  const body = ApproveWriteSchema.parse(await readJson(req));
  const session = sessionStore.get(body.sessionId);
  if (!session || session.tenantId !== auth.tenantId) {
    return writeJson(res, 404, { error: "unknown_session" }, corsHeaders);
  }

  await sessionStore.pushEvent(
    session.id,
    "approval.granted",
    {
      requestSeq: body.requestSeq,
      approverProfileId: auth.profileId,
    },
    true
  );

  writeJson(res, 200, { ok: true }, corsHeaders);
}

async function readJson(req: IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw.trim()) return {};
  return JSON.parse(raw);
}

function writeJson(
  res: ServerResponse,
  statusCode: number,
  body: unknown,
  headers: Record<string, string>
): void {
  res.writeHead(statusCode, {
    ...headers,
    "Content-Type": "application/json; charset=utf-8",
  });
  res.end(JSON.stringify(body));
}
