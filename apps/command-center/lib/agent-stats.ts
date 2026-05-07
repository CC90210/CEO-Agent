/**
 * Real-time stats for the Capabilities card. Replaces the lie that
 * lib/agent-catalog.ts told ("Bravo has 10 entries") with the truth:
 * how many skills, scripts, brain files, sub-agents, workflows, and
 * chat-callable tools actually exist for each agent.
 *
 * The "curated 10" stays — it's the highlighted-capabilities list.
 * These stats sit underneath as the honest denominator.
 *
 * Reads:
 *   - scripts/_bridge_manifest.json (290 entries) — chat-callable
 *   - skills/<name>/SKILL.md         (153 skills)
 *   - scripts/*.py                   (120 scripts)
 *   - brain/*.md                     (48 brain files)
 *   - memory/*.md                    (16 memory files)
 *   - .agents/workflows/*.md         (36 workflows)
 *
 * For sibling agents (Atlas, Maven, Aura, Hermes), we report THIS repo's
 * counts because the dashboard runs from this repo. The chat widget
 * already cd's to the correct sibling repo via the bridge when the
 * operator switches agents — those repos have their own brains.
 *
 * Cached per-request via Next.js's default fetch/fs caching; the file
 * system walk is cheap (a few hundred direntries, no file content reads).
 */

import { promises as fs } from "node:fs";
import path from "node:path";

export type AgentStats = {
  skills: number;
  scripts: number;
  chat_tools: number;
  brain_files: number;
  memory_files: number;
  workflows: number;
  sub_agents: number;
};

const REPO_ROOT = process.env.BRAVO_REPO_ROOT || path.resolve(process.cwd(), "..", "..");

async function _safeCount(dir: string, predicate: (name: string) => boolean): Promise<number> {
  try {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    return entries.filter((e) => predicate(e.name)).length;
  } catch {
    return 0;
  }
}

async function _countSkills(): Promise<number> {
  // skills/ has one subdir per skill, each with a SKILL.md inside.
  try {
    const skillsDir = path.join(REPO_ROOT, "skills");
    const entries = await fs.readdir(skillsDir, { withFileTypes: true });
    let count = 0;
    for (const e of entries) {
      if (!e.isDirectory()) continue;
      try {
        await fs.access(path.join(skillsDir, e.name, "SKILL.md"));
        count += 1;
      } catch {
        // No SKILL.md in this subdir — skip
      }
    }
    return count;
  } catch {
    return 0;
  }
}

async function _countChatTools(): Promise<number> {
  try {
    const manifestPath = path.join(REPO_ROOT, "scripts", "_bridge_manifest.json");
    const raw = await fs.readFile(manifestPath, "utf-8");
    const data = JSON.parse(raw) as { entries?: unknown[] };
    return Array.isArray(data.entries) ? data.entries.length : 0;
  } catch {
    return 0;
  }
}

let _cached: { stats: AgentStats; at: number } | null = null;
const CACHE_MS = 30_000;

/**
 * Returns the stats. The agentSlug arg is reserved for future per-agent
 * filtering (e.g. only count scripts whose path matches a sibling agent's
 * canonical prefix). Today we report this repo's totals for every slug
 * since each sibling repo runs the same dashboard concept.
 */
export async function getAgentStats(_agentSlug: string): Promise<AgentStats> {
  if (_cached && Date.now() - _cached.at < CACHE_MS) return _cached.stats;

  const scriptsDir = path.join(REPO_ROOT, "scripts");
  const brainDir = path.join(REPO_ROOT, "brain");
  const memoryDir = path.join(REPO_ROOT, "memory");
  const agentsDir = path.join(REPO_ROOT, "agents");
  const workflowsDir = path.join(REPO_ROOT, ".agents", "workflows");

  const [skills, scripts, chat_tools, brain_files, memory_files, sub_agents, workflows] =
    await Promise.all([
      _countSkills(),
      _safeCount(scriptsDir, (n) => n.endsWith(".py") && !n.startsWith("_") && !n.startsWith("test_")),
      _countChatTools(),
      _safeCount(brainDir, (n) => n.endsWith(".md")),
      _safeCount(memoryDir, (n) => n.endsWith(".md")),
      _safeCount(agentsDir, (n) => n.endsWith(".md")),
      _safeCount(workflowsDir, (n) => n.endsWith(".md")),
    ]);

  const stats: AgentStats = {
    skills,
    scripts,
    chat_tools,
    brain_files,
    memory_files,
    workflows,
    sub_agents,
  };
  _cached = { stats, at: Date.now() };
  return stats;
}
