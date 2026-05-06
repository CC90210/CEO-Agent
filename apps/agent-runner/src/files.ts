import { watch, promises as fs } from "node:fs";
import path from "node:path";

import ignore from "ignore";

export type WorkspaceNode = {
  name: string;
  path: string;
  kind: "file" | "dir";
  size?: number;
  children?: WorkspaceNode[];
};

type TreeOptions = {
  maxDepth?: number;
  maxBytes?: number;
};

const DEFAULT_MAX_DEPTH = 4;
const DEFAULT_MAX_BYTES = 256 * 1024;
const HIDDEN_ALLOWLIST = new Set([
  ".github",
  ".gitignore",
  ".npmrc",
  ".nvmrc",
]);

const HARD_BLOCKED_SEGMENTS = new Set([
  ".git",
  ".hg",
  ".svn",
  "node_modules",
  ".next",
  ".vercel",
  ".env",
  ".env.local",
  ".env.production",
  ".claude",
  ".codex",
]);

export function resolveWorkspaceRoot(
  agentKey: string,
  tenantSlug?: string | null
): string {
  const template = process.env.RUNNER_TENANT_ROOT_TEMPLATE;
  if (template && tenantSlug) {
    return template
      .replace("{tenant}", tenantSlug)
      .replace("{agent}", agentKey);
  }

  const envKey = `RUNNER_WORKSPACE_${agentKey.toUpperCase()}`;
  const configured = process.env[envKey];
  if (!configured) {
    throw new Error(
      `Workspace root missing for agent ${agentKey}. Set ${envKey} or RUNNER_TENANT_ROOT_TEMPLATE.`
    );
  }

  return configured;
}

export async function listWorkspaceTree(
  root: string,
  options: TreeOptions = {}
): Promise<WorkspaceNode[]> {
  const matcher = await loadIgnoreMatcher(root);
  return walkDirectory(root, root, matcher, 0, {
    maxDepth: options.maxDepth ?? DEFAULT_MAX_DEPTH,
    maxBytes: options.maxBytes ?? DEFAULT_MAX_BYTES,
  });
}

export async function readWorkspaceFile(
  root: string,
  relativePath: string,
  maxBytes = DEFAULT_MAX_BYTES
): Promise<string> {
  const absolute = assertSafePath(root, relativePath);
  const stat = await fs.stat(absolute);
  if (!stat.isFile()) {
    throw new Error("Requested path is not a file.");
  }
  if (stat.size > maxBytes) {
    throw new Error(
      `File exceeds max size (${stat.size} bytes > ${maxBytes} bytes).`
    );
  }
  return fs.readFile(absolute, "utf8");
}

export async function watchWorkspaceTree(
  root: string,
  onChange: (event: {
    type: "workspace.changed";
    path: string;
    change: string;
  }) => void,
  maxDepth = DEFAULT_MAX_DEPTH
): Promise<() => void> {
  const matcher = await loadIgnoreMatcher(root);
  const closers: Array<() => void> = [];

  async function attach(directory: string, depth: number): Promise<void> {
    if (depth > maxDepth) return;

    const relativeDir = normalizeRelative(root, directory);
    if (relativeDir && shouldHide(relativeDir, matcher)) {
      return;
    }

    const watcher = watch(directory, async (_eventType, fileName) => {
      const name = String(fileName || "").trim();
      if (!name) return;
      const rel = normalizeRelative(root, path.join(directory, name));
      if (shouldHide(rel, matcher)) return;
      onChange({
        type: "workspace.changed",
        path: rel,
        change: "modified",
      });
    });

    closers.push(() => watcher.close());

    const children = await fs.readdir(directory, { withFileTypes: true });
    await Promise.all(
      children
        .filter((entry) => entry.isDirectory())
        .map((entry) => attach(path.join(directory, entry.name), depth + 1))
    );
  }

  await attach(root, 0);
  return () => {
    for (const close of closers) {
      close();
    }
  };
}

function normalizeRelative(root: string, absolute: string): string {
  return path.relative(root, absolute).replace(/\\/g, "/");
}

function assertSafePath(root: string, relativePath: string): string {
  const absolute = path.resolve(root, relativePath);
  const normalizedRoot = path.resolve(root);
  if (
    absolute !== normalizedRoot &&
    !absolute.startsWith(`${normalizedRoot}${path.sep}`)
  ) {
    throw new Error("Path escapes the workspace root.");
  }
  return absolute;
}

async function loadIgnoreMatcher(root: string) {
  const matcher = ignore();
  try {
    const raw = await fs.readFile(path.join(root, ".gitignore"), "utf8");
    matcher.add(raw);
  } catch {
    // No .gitignore is fine.
  }
  return matcher;
}

async function walkDirectory(
  root: string,
  directory: string,
  matcher: ignore.Ignore,
  depth: number,
  options: Required<TreeOptions>
): Promise<WorkspaceNode[]> {
  if (depth > options.maxDepth) return [];

  const entries = await fs.readdir(directory, { withFileTypes: true });
  const results: WorkspaceNode[] = [];

  for (const entry of entries) {
    const absolute = path.join(directory, entry.name);
    const relative = normalizeRelative(root, absolute);

    if (shouldHide(relative, matcher)) {
      continue;
    }

    if (entry.isDirectory()) {
      results.push({
        name: entry.name,
        path: relative,
        kind: "dir",
        children: await walkDirectory(root, absolute, matcher, depth + 1, options),
      });
      continue;
    }

    const stat = await fs.stat(absolute);
    if (stat.size > options.maxBytes) {
      continue;
    }

    results.push({
      name: entry.name,
      path: relative,
      kind: "file",
      size: stat.size,
    });
  }

  return results.sort((left, right) => {
    if (left.kind !== right.kind) {
      return left.kind === "dir" ? -1 : 1;
    }
    return left.name.localeCompare(right.name);
  });
}

function shouldHide(relativePath: string, matcher: ignore.Ignore): boolean {
  if (!relativePath || relativePath === ".") return false;

  const segments = relativePath.split("/");
  for (const segment of segments) {
    if (HARD_BLOCKED_SEGMENTS.has(segment)) return true;
    if (segment.startsWith(".") && !HIDDEN_ALLOWLIST.has(segment)) {
      return true;
    }
  }

  return matcher.ignores(relativePath);
}
