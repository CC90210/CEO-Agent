import { randomUUID } from "node:crypto";
import type { ChildProcessWithoutNullStreams } from "node:child_process";

import type { AuthenticatedContext } from "./auth.js";
import { getSupabaseAdmin } from "./auth.js";

export type ProviderKind =
  | "claude_code"
  | "claude_api"
  | "openai"
  | "gemini"
  | "codex";

export type OperationMode =
  | "chat"
  | "task"
  | "review"
  | "adversarial_review";

export type WriteMode =
  | "read_only"
  | "approval_required"
  | "approved";

export type SessionStatus =
  | "queued"
  | "running"
  | "streaming"
  | "completed"
  | "failed"
  | "cancelled"
  | "waiting_approval";

export type ChatStartRequest = {
  agentKey: string;
  provider: ProviderKind;
  model: string;
  prompt: string;
  operationMode: OperationMode;
  writeMode: WriteMode;
  parentSessionId?: string | null;
};

export type RunnerEvent = {
  id: string;
  seq: number;
  type: string;
  data: unknown;
  createdAt: string;
};

type SessionListener = (event: RunnerEvent) => void;

export type RunnerSession = {
  id: string;
  tenantId: string;
  profileId: string;
  agentKey: string;
  provider: ProviderKind;
  model: string;
  prompt: string;
  operationMode: OperationMode;
  writeMode: WriteMode;
  workspaceRoot: string;
  status: SessionStatus;
  createdAt: string;
  updatedAt: string;
  lastEventSeq: number;
  providerSessionId: string | null;
  listeners: Set<SessionListener>;
  events: RunnerEvent[];
  finalAssistantChunks: string[];
  child: ChildProcessWithoutNullStreams | null;
  lastError: string | null;
};

type ChatSessionInsert = {
  id: string;
  tenant_id: string;
  profile_id: string;
  parent_session_id: string | null;
  agent_key: string;
  provider: ProviderKind;
  model_slug: string;
  workspace_root: string;
  operation_mode: OperationMode;
  write_mode: WriteMode;
  status: SessionStatus;
  metadata: Record<string, unknown>;
};

type ChatMessageInsert = {
  session_id: string;
  tenant_id: string;
  seq: number;
  role: "user" | "assistant" | "system" | "tool" | "runner";
  message_kind: string;
  content: string;
  content_json?: Record<string, unknown> | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  cost_usd?: number | null;
  latency_ms?: number | null;
};

type AuditInsert = {
  tenant_id: string;
  session_id?: string | null;
  actor_profile_id?: string | null;
  actor_type: string;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  status: string;
  metadata?: Record<string, unknown>;
};

async function insertAudit(payload: AuditInsert): Promise<void> {
  const admin = getSupabaseAdmin();
  await admin.from("audit_log").insert(payload);
}

async function insertMessage(payload: ChatMessageInsert): Promise<void> {
  const admin = getSupabaseAdmin();
  await admin.from("chat_messages").insert({
    ...payload,
    content_json: payload.content_json ?? null,
    input_tokens: payload.input_tokens ?? null,
    output_tokens: payload.output_tokens ?? null,
    cost_usd: payload.cost_usd ?? null,
    latency_ms: payload.latency_ms ?? null,
  });
}

async function updateSessionRow(
  sessionId: string,
  patch: Record<string, unknown>
): Promise<void> {
  const admin = getSupabaseAdmin();
  await admin
    .from("chat_sessions")
    .update({
      ...patch,
      updated_at: new Date().toISOString(),
    })
    .eq("id", sessionId);
}

export class SessionStore {
  private readonly sessions = new Map<string, RunnerSession>();
  private readonly maxReplayEvents = 500;

  async createSession(
    auth: AuthenticatedContext,
    request: ChatStartRequest,
    workspaceRoot: string
  ): Promise<RunnerSession> {
    const now = new Date().toISOString();
    const session: RunnerSession = {
      id: randomUUID(),
      tenantId: auth.tenantId,
      profileId: auth.profileId,
      agentKey: request.agentKey,
      provider: request.provider,
      model: request.model,
      prompt: request.prompt,
      operationMode: request.operationMode,
      writeMode: request.writeMode,
      workspaceRoot,
      status: "queued",
      createdAt: now,
      updatedAt: now,
      lastEventSeq: 0,
      providerSessionId: null,
      listeners: new Set(),
      events: [],
      finalAssistantChunks: [],
      child: null,
      lastError: null,
    };

    const row: ChatSessionInsert = {
      id: session.id,
      tenant_id: session.tenantId,
      profile_id: session.profileId,
      parent_session_id: request.parentSessionId ?? null,
      agent_key: session.agentKey,
      provider: session.provider,
      model_slug: session.model,
      workspace_root: session.workspaceRoot,
      operation_mode: session.operationMode,
      write_mode: session.writeMode,
      status: session.status,
      metadata: {
        requested_origin: auth.origin,
      },
    };

    const admin = getSupabaseAdmin();
    await admin.from("chat_sessions").insert(row);
    await insertAudit({
      tenant_id: auth.tenantId,
      session_id: session.id,
      actor_profile_id: auth.profileId,
      actor_type: "user",
      action: "chat.session.created",
      target_type: "chat_session",
      target_id: session.id,
      status: "accepted",
      metadata: {
        agent_key: session.agentKey,
        provider: session.provider,
        model: session.model,
        operation_mode: session.operationMode,
        write_mode: session.writeMode,
      },
    });

    this.sessions.set(session.id, session);

    if (request.prompt.trim()) {
      await this.appendMessage(session.id, "user", "prompt", request.prompt);
    }

    return session;
  }

  get(sessionId: string): RunnerSession | undefined {
    return this.sessions.get(sessionId);
  }

  attach(sessionId: string, listener: SessionListener): (() => void) {
    const session = this.mustGet(sessionId);
    session.listeners.add(listener);
    return () => {
      session.listeners.delete(listener);
    };
  }

  replaySince(sessionId: string, afterSeq: number): RunnerEvent[] {
    const session = this.mustGet(sessionId);
    return session.events.filter((event) => event.seq > afterSeq);
  }

  async appendMessage(
    sessionId: string,
    role: "user" | "assistant" | "system" | "tool" | "runner",
    messageKind: string,
    content: string,
    extras?: Partial<ChatMessageInsert>
  ): Promise<RunnerEvent> {
    const session = this.mustGet(sessionId);
    const event = this.buildEvent(session, `${role}.${messageKind}`, {
      role,
      messageKind,
      content,
    });

    if (role === "assistant" && messageKind === "delta") {
      session.finalAssistantChunks.push(content);
    }

    await insertMessage({
      session_id: session.id,
      tenant_id: session.tenantId,
      seq: event.seq,
      role,
      message_kind: messageKind,
      content,
      content_json: extras?.content_json ?? null,
      input_tokens: extras?.input_tokens ?? null,
      output_tokens: extras?.output_tokens ?? null,
      cost_usd: extras?.cost_usd ?? null,
      latency_ms: extras?.latency_ms ?? null,
    });

    this.emit(session, event);
    return event;
  }

  async pushEvent(
    sessionId: string,
    type: string,
    data: Record<string, unknown>,
    persist = false
  ): Promise<RunnerEvent> {
    const session = this.mustGet(sessionId);
    const event = this.buildEvent(session, type, data);

    if (persist) {
      await insertMessage({
        session_id: session.id,
        tenant_id: session.tenantId,
        seq: event.seq,
        role: "runner",
        message_kind: "event",
        content: JSON.stringify(data),
        content_json: data,
      });
    }

    this.emit(session, event);
    return event;
  }

  async markRunning(sessionId: string, childPid?: number): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "running";
    session.updatedAt = new Date().toISOString();
    await updateSessionRow(sessionId, {
      status: session.status,
      metadata: {
        child_pid: childPid ?? null,
      },
    });
  }

  async markStreaming(
    sessionId: string,
    providerSessionId?: string | null
  ): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "streaming";
    session.providerSessionId = providerSessionId ?? session.providerSessionId;
    session.updatedAt = new Date().toISOString();
    await updateSessionRow(sessionId, {
      status: session.status,
      provider_session_id: session.providerSessionId,
      last_event_seq: session.lastEventSeq,
    });
  }

  async complete(
    sessionId: string,
    usage?: {
      inputTokens?: number;
      outputTokens?: number;
      costUsd?: number;
    }
  ): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "completed";
    session.updatedAt = new Date().toISOString();

    const finalText = session.finalAssistantChunks.join("");
    if (finalText) {
      await this.appendMessage(sessionId, "assistant", "final", finalText, {
        input_tokens: usage?.inputTokens ?? null,
        output_tokens: usage?.outputTokens ?? null,
        cost_usd: usage?.costUsd ?? null,
      });
    }

    await updateSessionRow(sessionId, {
      status: session.status,
      completed_at: new Date().toISOString(),
      last_event_seq: session.lastEventSeq,
      budget_estimated_input_tokens: usage?.inputTokens ?? null,
      budget_estimated_output_tokens: usage?.outputTokens ?? null,
      estimated_cost_usd: usage?.costUsd ?? null,
      provider_session_id: session.providerSessionId,
    });

    await insertAudit({
      tenant_id: session.tenantId,
      session_id: session.id,
      actor_profile_id: session.profileId,
      actor_type: "runner",
      action: "chat.session.completed",
      target_type: "chat_session",
      target_id: session.id,
      status: "completed",
      metadata: {
        provider_session_id: session.providerSessionId,
        input_tokens: usage?.inputTokens ?? null,
        output_tokens: usage?.outputTokens ?? null,
        cost_usd: usage?.costUsd ?? null,
      },
    });
  }

  async fail(sessionId: string, errorMessage: string): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "failed";
    session.lastError = errorMessage;
    session.updatedAt = new Date().toISOString();

    await this.pushEvent(sessionId, "runner.failed", { message: errorMessage }, true);
    await updateSessionRow(sessionId, {
      status: session.status,
      completed_at: new Date().toISOString(),
      last_error: errorMessage,
      last_event_seq: session.lastEventSeq,
      provider_session_id: session.providerSessionId,
    });

    await insertAudit({
      tenant_id: session.tenantId,
      session_id: session.id,
      actor_profile_id: session.profileId,
      actor_type: "runner",
      action: "chat.session.failed",
      target_type: "chat_session",
      target_id: session.id,
      status: "failed",
      metadata: {
        message: errorMessage,
      },
    });
  }

  async markApprovalRequired(
    sessionId: string,
    payload: Record<string, unknown>
  ): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "waiting_approval";
    session.updatedAt = new Date().toISOString();
    await this.pushEvent(sessionId, "approval.requested", payload, true);
    await updateSessionRow(sessionId, {
      status: session.status,
      last_event_seq: session.lastEventSeq,
    });
  }

  async cancel(sessionId: string, reason: string): Promise<void> {
    const session = this.mustGet(sessionId);
    session.status = "cancelled";
    session.updatedAt = new Date().toISOString();
    await this.pushEvent(sessionId, "runner.cancelled", { reason }, true);
    await updateSessionRow(sessionId, {
      status: session.status,
      completed_at: new Date().toISOString(),
      last_error: reason,
      last_event_seq: session.lastEventSeq,
    });
  }

  private mustGet(sessionId: string): RunnerSession {
    const session = this.sessions.get(sessionId);
    if (!session) {
      throw new Error(`Unknown session: ${sessionId}`);
    }
    return session;
  }

  private buildEvent(
    session: RunnerSession,
    type: string,
    data: unknown
  ): RunnerEvent {
    session.lastEventSeq += 1;
    session.updatedAt = new Date().toISOString();
    const event: RunnerEvent = {
      id: `${session.id}:${session.lastEventSeq}`,
      seq: session.lastEventSeq,
      type,
      data,
      createdAt: new Date().toISOString(),
    };

    session.events.push(event);
    if (session.events.length > this.maxReplayEvents) {
      session.events = session.events.slice(-this.maxReplayEvents);
    }

    return event;
  }

  private emit(session: RunnerSession, event: RunnerEvent): void {
    for (const listener of session.listeners) {
      listener(event);
    }
  }
}
