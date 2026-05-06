import { spawn } from "node:child_process";
import { StringDecoder } from "node:string_decoder";

import sodium from "libsodium-wrappers";

import type { AuthenticatedContext } from "./auth.js";
import { getSupabaseAdmin } from "./auth.js";
import type { RunnerSession, SessionStore } from "./sessions.js";

type AgentModelConfigRow = {
  id: string;
  credential_origin: string;
  auth_mode: string;
  secret_ciphertext: string | null;
  secret_nonce: string | null;
  secret_key_version: string | null;
  provider: string;
  model_slug: string;
  wrapper_command: string | null;
  wrapper_args: string[] | null;
  env_overrides: Record<string, string> | null;
  metadata: Record<string, unknown> | null;
};

type WrapperEvent =
  | { type: "assistant.delta"; text: string }
  | { type: "assistant.final"; text: string }
  | { type: "tool.started"; toolName: string; input?: unknown }
  | { type: "tool.completed"; toolName: string; result?: unknown }
  | { type: "provider.session"; sessionId: string }
  | { type: "usage"; inputTokens?: number; outputTokens?: number; costUsd?: number }
  | { type: "approval.requested"; payload: Record<string, unknown> }
  | { type: "runner.log"; message: string }
  | { type: "done" }
  | { type: "error"; message: string };

const OUTPUT_KEY_BY_PROVIDER: Record<string, string> = {
  claude_code: "ANTHROPIC_API_KEY",
  claude_api: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  codex: "OPENAI_API_KEY",
  gemini: "GEMINI_API_KEY",
};

export async function startSessionRun(
  auth: AuthenticatedContext,
  session: RunnerSession,
  store: SessionStore
): Promise<void> {
  await store.markRunning(session.id);

  const config = await resolveAgentModelConfig(auth, session);
  const wrapperCommand =
    config.wrapper_command ||
    process.env[`RUNNER_WRAPPER_${session.provider.toUpperCase()}`];

  if (!wrapperCommand) {
    throw new Error(
      `No wrapper command configured for provider ${session.provider}.`
    );
  }

  const wrapperArgs = config.wrapper_args || [];
  const child = spawn(wrapperCommand, wrapperArgs, {
    cwd: session.workspaceRoot,
    env: await buildProviderEnvironment(auth, session, config),
    stdio: "pipe",
  });

  session.child = child;
  await store.markRunning(session.id, child.pid);

  const stdout = new StringDecoder("utf8");
  const stderr = new StringDecoder("utf8");
  let stdoutBuffer = "";
  let stderrBuffer = "";
  let settled = false;
  const usage: { inputTokens?: number; outputTokens?: number; costUsd?: number } =
    {};

  child.stdin.write(
    `${JSON.stringify({
      sessionId: session.id,
      tenantId: auth.tenantId,
      profileId: auth.profileId,
      provider: session.provider,
      model: session.model,
      workspaceRoot: session.workspaceRoot,
      operationMode: session.operationMode,
      writeMode: session.writeMode,
      prompt: session.prompt,
      metadata: {
        tenantSlug: auth.tenantSlug,
        tenantName: auth.tenantName,
      },
    })}\n`
  );
  child.stdin.end();

  child.stdout.on("data", async (chunk: Buffer) => {
    stdoutBuffer += stdout.write(chunk);
    stdoutBuffer = await flushStructuredLines(
      stdoutBuffer,
      store,
      session,
      usage
    );
  });

  child.stderr.on("data", async (chunk: Buffer) => {
    stderrBuffer += stderr.write(chunk);
    const lines = stderrBuffer.split(/\r?\n/);
    stderrBuffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      await store.pushEvent(
        session.id,
        "runner.stderr",
        { message: trimmed },
        true
      );
    }
  });

  const settleFailure = async (message: string) => {
    if (settled) return;
    settled = true;
    await store.fail(session.id, message);
  };

  child.on("error", async (error) => {
    await settleFailure(error.message);
  });

  child.on("close", async (code) => {
    const trailingStdout = stdout.end();
    if (trailingStdout) {
      stdoutBuffer += trailingStdout;
      stdoutBuffer = await flushStructuredLines(
        stdoutBuffer,
        store,
        session,
        usage
      );
    }

    const trailingStderr = stderr.end();
    if (trailingStderr.trim()) {
      await store.pushEvent(
        session.id,
        "runner.stderr",
        { message: trailingStderr.trim() },
        true
      );
    }

    if (settled) {
      return;
    }

    if (code === 0) {
      settled = true;
      await store.complete(session.id, usage);
      return;
    }

    const message =
      stderrBuffer.trim() ||
      stdoutBuffer.trim() ||
      `Wrapper exited with code ${code ?? -1}.`;
    await settleFailure(message);
  });
}

async function flushStructuredLines(
  buffer: string,
  store: SessionStore,
  session: RunnerSession,
  usage: { inputTokens?: number; outputTokens?: number; costUsd?: number }
): Promise<string> {
  const lines = buffer.split(/\r?\n/);
  const remainder = lines.pop() ?? "";

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    let event: WrapperEvent;
    try {
      event = JSON.parse(trimmed) as WrapperEvent;
    } catch {
      event = {
        type: "assistant.delta",
        text: trimmed,
      };
    }

    switch (event.type) {
      case "assistant.delta":
        await store.markStreaming(session.id);
        await store.appendMessage(session.id, "assistant", "delta", event.text);
        break;
      case "assistant.final":
        await store.markStreaming(session.id);
        session.finalAssistantChunks = [event.text];
        await store.pushEvent(
          session.id,
          "assistant.final",
          { content: event.text },
          true
        );
        break;
      case "tool.started":
        await store.pushEvent(
          session.id,
          "tool.started",
          {
            toolName: event.toolName,
            input: event.input ?? null,
          },
          true
        );
        break;
      case "tool.completed":
        await store.pushEvent(
          session.id,
          "tool.completed",
          {
            toolName: event.toolName,
            result: event.result ?? null,
          },
          true
        );
        break;
      case "provider.session":
        session.providerSessionId = event.sessionId;
        await store.markStreaming(session.id, event.sessionId);
        break;
      case "usage":
        usage.inputTokens = event.inputTokens ?? usage.inputTokens;
        usage.outputTokens = event.outputTokens ?? usage.outputTokens;
        usage.costUsd = event.costUsd ?? usage.costUsd;
        await store.pushEvent(
          session.id,
          "usage.updated",
          {
            inputTokens: usage.inputTokens ?? null,
            outputTokens: usage.outputTokens ?? null,
            costUsd: usage.costUsd ?? null,
          },
          true
        );
        break;
      case "approval.requested":
        await store.markApprovalRequired(session.id, event.payload);
        break;
      case "runner.log":
        await store.pushEvent(
          session.id,
          "runner.log",
          { message: event.message },
          true
        );
        break;
      case "error":
        await store.pushEvent(
          session.id,
          "runner.error",
          { message: event.message },
          true
        );
        break;
      case "done":
        break;
    }
  }

  return remainder;
}

async function resolveAgentModelConfig(
  auth: AuthenticatedContext,
  session: RunnerSession
): Promise<AgentModelConfigRow> {
  const admin = getSupabaseAdmin();
  const result = await admin
    .from("agent_model_config")
    .select(
      "id, credential_origin, auth_mode, secret_ciphertext, secret_nonce, secret_key_version, provider, model_slug, wrapper_command, wrapper_args, env_overrides, metadata"
    )
    .eq("tenant_id", auth.tenantId)
    .eq("agent_key", session.agentKey)
    .eq("provider", session.provider)
    .eq("model_slug", session.model)
    .eq("enabled", true)
    .maybeSingle();

  const config = result.data as AgentModelConfigRow | null;
  if (!config) {
    throw new Error(
      `No enabled agent_model_config row for ${session.agentKey}/${session.provider}/${session.model}.`
    );
  }

  if (
    (config.credential_origin === "platform_subscription" ||
      config.credential_origin === "platform_api_key") &&
    !auth.canUseManagedAuth
  ) {
    throw new Error(
      "This tenant is not allowed to use platform-managed credentials."
    );
  }

  return config;
}

async function buildProviderEnvironment(
  auth: AuthenticatedContext,
  session: RunnerSession,
  config: AgentModelConfigRow
): Promise<NodeJS.ProcessEnv> {
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    RUNNER_SESSION_ID: session.id,
    RUNNER_TENANT_ID: auth.tenantId,
    RUNNER_PROFILE_ID: auth.profileId,
    RUNNER_AGENT_KEY: session.agentKey,
    RUNNER_PROVIDER: session.provider,
    RUNNER_MODEL: session.model,
    RUNNER_WRITE_MODE: session.writeMode,
    RUNNER_OPERATION_MODE: session.operationMode,
  };

  if (config.env_overrides) {
    for (const [key, value] of Object.entries(config.env_overrides)) {
      env[key] = value;
    }
  }

  const outputKey = OUTPUT_KEY_BY_PROVIDER[session.provider];
  const decryptedSecret = await decryptSecret(config);

  if (config.credential_origin === "platform_subscription") {
    if (!auth.canUseManagedAuth) {
      throw new Error("Managed subscription auth is not enabled for this tenant.");
    }
    if (outputKey) delete env[outputKey];
    return env;
  }

  if (decryptedSecret && outputKey) {
    env[outputKey] = decryptedSecret;
  }

  return env;
}

async function decryptSecret(config: AgentModelConfigRow): Promise<string | null> {
  if (!config.secret_ciphertext || !config.secret_nonce) {
    return null;
  }

  const keyB64 = process.env.RUNNER_SECRETBOX_KEY_B64;
  if (!keyB64) {
    throw new Error("RUNNER_SECRETBOX_KEY_B64 is required to decrypt tenant keys.");
  }

  await sodium.ready;
  const key = sodium.from_base64(keyB64, sodium.base64_variants.ORIGINAL);
  const nonce = sodium.from_base64(
    config.secret_nonce,
    sodium.base64_variants.ORIGINAL
  );
  const cipher = sodium.from_base64(
    config.secret_ciphertext,
    sodium.base64_variants.ORIGINAL
  );

  const opened = sodium.crypto_secretbox_open_easy(cipher, nonce, key);
  return sodium.to_string(opened);
}
