/**
 * Manifest diff — produces a human-readable change list between two
 * manifests. The UI shows this to the operator before they hit Apply, and
 * the audit log persists it for rollback context.
 *
 * Format: a flat array of { op, path, before, after, summary } entries. Not
 * trying to be RFC 6902 JSON Patch — that's too pedantic for the AI editor's
 * needs and produces noisy output for nested array reshuffles. Instead we
 * surface intent-level changes: "brand.name: 'OASIS AI' → 'OASIS Pro'", "nav
 * item added: /leads (Leads)", "field 'commission_pct' added to entity 'deal'".
 *
 * Pure logic — no I/O, no rendering. The UI maps each entry to a list item.
 */

import type { TenantManifest } from "./schema";

export type DiffEntry = {
  op: "set" | "add" | "remove" | "update";
  path: string;
  before?: unknown;
  after?: unknown;
  summary: string;
};

function brandDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const b = before.brand;
  const a = after.brand;
  const keys: (keyof typeof b)[] = [
    "name", "logo", "logo_url", "subtitle", "footer_label", "footer_tagline", "primary_color",
  ];
  for (const k of keys) {
    if (b[k] !== a[k]) {
      out.push({
        op: "set",
        path: `brand.${k}`,
        before: b[k],
        after: a[k],
        summary: `brand.${k}: ${formatVal(b[k])} → ${formatVal(a[k])}`,
      });
    }
  }
  return out;
}

function navDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const beforeMap = new Map(before.nav.map((n) => [n.href, n] as const));
  const afterMap = new Map(after.nav.map((n) => [n.href, n] as const));

  for (const [href, item] of afterMap) {
    if (!beforeMap.has(href)) {
      out.push({
        op: "add",
        path: `nav[${href}]`,
        after: item,
        summary: `nav item added: ${href} (${item.label}) in ${item.group}`,
      });
    } else {
      const b = beforeMap.get(href)!;
      const changed: string[] = [];
      if (b.label !== item.label) changed.push(`label "${b.label}"→"${item.label}"`);
      if (b.icon !== item.icon) changed.push(`icon ${b.icon}→${item.icon}`);
      if (b.group !== item.group) changed.push(`group "${b.group}"→"${item.group}"`);
      if (b.badge_key !== item.badge_key) changed.push(`badge_key ${formatVal(b.badge_key)}→${formatVal(item.badge_key)}`);
      if (b.expandable !== item.expandable) changed.push(`expandable ${b.expandable}→${item.expandable}`);
      if (changed.length > 0) {
        out.push({
          op: "update",
          path: `nav[${href}]`,
          before: b,
          after: item,
          summary: `nav item ${href}: ${changed.join(", ")}`,
        });
      }
    }
  }
  for (const [href, item] of beforeMap) {
    if (!afterMap.has(href)) {
      out.push({
        op: "remove",
        path: `nav[${href}]`,
        before: item,
        summary: `nav item removed: ${href} (${item.label})`,
      });
    }
  }
  // Reorder detection — same hrefs but different sequence.
  const beforeOrder = before.nav.map((n) => n.href).join("|");
  const afterOrder = after.nav.map((n) => n.href).join("|");
  if (beforeOrder !== afterOrder && beforeMap.size === afterMap.size) {
    const stillSame = before.nav.every((n) => afterMap.has(n.href)) && after.nav.every((n) => beforeMap.has(n.href));
    if (stillSame) {
      out.push({
        op: "update",
        path: "nav.order",
        before: before.nav.map((n) => n.href),
        after: after.nav.map((n) => n.href),
        summary: `nav order changed`,
      });
    }
  }
  return out;
}

function agentDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const beforeMap = new Map(before.agents.map((a) => [a.slug, a] as const));
  const afterMap = new Map(after.agents.map((a) => [a.slug, a] as const));
  for (const [slug, a] of afterMap) {
    const b = beforeMap.get(slug);
    if (!b) {
      out.push({
        op: "add",
        path: `agent[${slug}]`,
        after: a,
        summary: `agent enabled: ${a.display_name} (${slug})${a.primary ? " — primary" : ""}`,
      });
      continue;
    }
    if (b.enabled !== a.enabled) {
      out.push({
        op: "update",
        path: `agent[${slug}].enabled`,
        before: b.enabled,
        after: a.enabled,
        summary: a.enabled ? `agent re-enabled: ${a.display_name}` : `agent disabled: ${a.display_name}`,
      });
    }
    if (b.display_name !== a.display_name) {
      out.push({
        op: "update",
        path: `agent[${slug}].display_name`,
        before: b.display_name,
        after: a.display_name,
        summary: `agent renamed: ${b.display_name} → ${a.display_name}`,
      });
    }
    if (!!b.primary !== !!a.primary) {
      out.push({
        op: "update",
        path: `agent[${slug}].primary`,
        before: b.primary,
        after: a.primary,
        summary: a.primary ? `${a.display_name} is now primary` : `${a.display_name} is no longer primary`,
      });
    }
  }
  for (const [slug, b] of beforeMap) {
    if (!afterMap.has(slug)) {
      out.push({
        op: "remove",
        path: `agent[${slug}]`,
        before: b,
        summary: `agent removed: ${b.display_name}`,
      });
    }
  }
  return out;
}

function entityDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const b = before.data_model || [];
  const a = after.data_model || [];
  const beforeMap = new Map(b.map((e) => [e.name, e] as const));
  const afterMap = new Map(a.map((e) => [e.name, e] as const));
  for (const [name, entity] of afterMap) {
    const prev = beforeMap.get(name);
    if (!prev) {
      out.push({
        op: "add",
        path: `entity[${name}]`,
        after: entity,
        summary: `entity created: ${entity.label} (${entity.fields.length} field${entity.fields.length === 1 ? "" : "s"})`,
      });
      continue;
    }
    const prevFields = new Map(prev.fields.map((f) => [f.name, f] as const));
    const newFields = new Map(entity.fields.map((f) => [f.name, f] as const));
    for (const [fname, f] of newFields) {
      if (!prevFields.has(fname)) {
        out.push({
          op: "add",
          path: `entity[${name}].fields[${fname}]`,
          after: f,
          summary: `field added: ${name}.${fname} (${f.type})`,
        });
      }
    }
    for (const [fname, f] of prevFields) {
      if (!newFields.has(fname)) {
        out.push({
          op: "remove",
          path: `entity[${name}].fields[${fname}]`,
          before: f,
          summary: `field removed: ${name}.${fname}`,
        });
      }
    }
  }
  for (const [name, entity] of beforeMap) {
    if (!afterMap.has(name)) {
      out.push({
        op: "remove",
        path: `entity[${name}]`,
        before: entity,
        summary: `entity removed: ${entity.label}`,
      });
    }
  }
  return out;
}

function pageDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const b = before.pages || [];
  const a = after.pages || [];
  const beforeMap = new Map(b.map((p) => [p.path, p] as const));
  const afterMap = new Map(a.map((p) => [p.path, p] as const));
  for (const [path, page] of afterMap) {
    if (!beforeMap.has(path)) {
      out.push({
        op: "add",
        path: `page[${path}]`,
        after: page,
        summary: `page added: ${page.label} (${page.kind}${page.entity ? `, entity=${page.entity}` : ""})`,
      });
    }
  }
  for (const [path, page] of beforeMap) {
    if (!afterMap.has(path)) {
      out.push({
        op: "remove",
        path: `page[${path}]`,
        before: page,
        summary: `page removed: ${page.label}`,
      });
    }
  }
  return out;
}

function promptDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  const out: DiffEntry[] = [];
  const key = (p: { agent_slug: string; label: string }) => `${p.agent_slug}::${p.label}`;
  const b = before.default_prompts || [];
  const a = after.default_prompts || [];
  const beforeMap = new Map(b.map((p) => [key(p), p] as const));
  const afterMap = new Map(a.map((p) => [key(p), p] as const));
  for (const [k, p] of afterMap) {
    const prev = beforeMap.get(k);
    if (!prev) {
      out.push({
        op: "add",
        path: `prompt[${k}]`,
        after: p,
        summary: `prompt added: ${p.agent_slug} · ${p.label}`,
      });
    } else if (prev.prompt !== p.prompt) {
      out.push({
        op: "update",
        path: `prompt[${k}]`,
        before: prev,
        after: p,
        summary: `prompt updated: ${p.agent_slug} · ${p.label}`,
      });
    }
  }
  for (const [k, p] of beforeMap) {
    if (!afterMap.has(k)) {
      out.push({
        op: "remove",
        path: `prompt[${k}]`,
        before: p,
        summary: `prompt removed: ${p.agent_slug} · ${p.label}`,
      });
    }
  }
  return out;
}

function industryDiff(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  if (before.onboarding_industry === after.onboarding_industry) return [];
  return [{
    op: "set",
    path: "onboarding_industry",
    before: before.onboarding_industry,
    after: after.onboarding_industry,
    summary: `industry: ${before.onboarding_industry || "unset"} → ${after.onboarding_industry || "unset"}`,
  }];
}

function formatVal(v: unknown): string {
  if (v === undefined) return "(unset)";
  if (v === null) return "(null)";
  if (typeof v === "string") return `"${v}"`;
  return String(v);
}

export function diffManifests(before: TenantManifest, after: TenantManifest): DiffEntry[] {
  return [
    ...brandDiff(before, after),
    ...navDiff(before, after),
    ...agentDiff(before, after),
    ...entityDiff(before, after),
    ...pageDiff(before, after),
    ...promptDiff(before, after),
    ...industryDiff(before, after),
  ];
}
