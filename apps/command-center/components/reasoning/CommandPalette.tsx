"use client";

import { useMemo, useState } from "react";
import { Copy, Check, ChevronDown } from "lucide-react";
import { AGENT_DISPLAY, commandsByCategory, type AgentSlug, type SlashCommand } from "@/lib/slash-commands";

export function CommandPalette({ commands, enabledAgents }: { commands: SlashCommand[]; enabledAgents: string[] }) {
  const [search, setSearch] = useState("");
  const [agentFilter, setAgentFilter] = useState<AgentSlug | "all">("all");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return commands.filter((c) => {
      if (agentFilter !== "all" && c.agent !== agentFilter) return false;
      if (!q) return true;
      return (
        c.slug.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.category?.toLowerCase().includes(q) ||
        false
      );
    });
  }, [commands, search, agentFilter]);

  const grouped = useMemo(() => commandsByCategory(filtered), [filtered]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          placeholder="Search commands…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input flex-1"
          autoFocus
        />
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value as AgentSlug | "all")}
          className="select sm:w-44"
        >
          <option value="all">All agents</option>
          {enabledAgents.map((a) => (
            <option key={a} value={a}>
              {AGENT_DISPLAY[a as AgentSlug]?.name || a}
            </option>
          ))}
        </select>
      </div>

      <div className="text-xs text-fg-dim">
        {filtered.length} command{filtered.length === 1 ? "" : "s"} ·{" "}
        {enabledAgents.length} agent{enabledAgents.length === 1 ? "" : "s"} enabled
      </div>

      {filtered.length === 0 ? (
        <div className="text-fg-muted text-sm py-8 text-center">
          No commands match. Try clearing the search or switching agent filter.
        </div>
      ) : (
        <div className="space-y-5">
          {Object.entries(grouped).map(([category, cmds]) => (
            <CategoryGroup key={category} name={category} commands={cmds} />
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryGroup({ name, commands }: { name: string; commands: SlashCommand[] }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.16em] font-bold text-fg-faint mb-2">
        {name} · {commands.length}
      </div>
      <ul className="space-y-1.5">
        {commands.map((c) => (
          <CommandRow key={`${c.agent}-${c.slug}`} command={c} />
        ))}
      </ul>
    </div>
  );
}

function CommandRow({ command }: { command: SlashCommand }) {
  const [open, setOpen] = useState(false);
  const agent = AGENT_DISPLAY[command.agent];

  return (
    <li className="rounded-md border border-bg-border bg-bg-elev overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-bg-hover transition-colors text-left"
      >
        <span
          className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
          style={{
            color: agent?.color || "#9ca0a8",
            background: `${agent?.color || "#9ca0a8"}1a`,
          }}
        >
          {agent?.name || command.agent}
        </span>
        <code className="text-accent text-xs font-mono">/{command.slug}</code>
        <span className="text-fg text-sm flex-1 truncate">{command.description}</span>
        <ChevronDown
          size={14}
          className={`text-fg-dim transition-transform shrink-0 ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <div className="border-t border-bg-border bg-bg-panel p-4 space-y-3">
          {command.notes && (
            <div className="text-xs text-fg-muted italic">
              <span className="text-fg-dim">Note → </span>
              {command.notes}
            </div>
          )}
          <CopyableLine label="cd to repo" value={`cd "${command.cwd_hint}"`} />
          <CopyableLine label="run command" value={command.cli_invocation} />
        </div>
      )}
    </li>
  );
}

function CopyableLine({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // ignore
    }
  }
  return (
    <div>
      <div className="label">{label}</div>
      <div className="flex items-stretch gap-2">
        <code className="flex-1 text-xs font-mono bg-bg border border-bg-border rounded px-3 py-2 text-fg overflow-x-auto whitespace-nowrap">
          {value}
        </code>
        <button
          onClick={copy}
          className="btn-secondary !px-3 !py-1 inline-flex items-center gap-1 shrink-0"
          title="Copy to clipboard"
        >
          {copied ? <Check size={12} className="text-status-engaged" /> : <Copy size={12} />}
          <span className="text-xs">{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
    </div>
  );
}
