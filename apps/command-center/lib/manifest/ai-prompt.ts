/**
 * Manifest editor system prompt builder.
 *
 * The chat endpoint asks the LLM to respond with a strict JSON envelope:
 *
 *   { "explanation": "...", "mutations": [ { "name": "...", "args": {...} } ] }
 *
 * If the user is just asking a question (no edits needed), the AI replies
 * with the explanation and `mutations: []`. The frontend renders the
 * explanation and shows a diff preview only when mutations is non-empty.
 *
 * We avoid native Anthropic tool-use / OpenAI function-calling on purpose:
 * keeping the surface text-only means the same code path works for
 * OpenRouter (any model), local Ollama, and Google — not just Anthropic
 * direct. Reliability is high because the prompt explicitly anchors the
 * envelope shape and provides examples for every mutator.
 *
 * The system prompt is constructed per-call so the AI sees the LIVE manifest
 * as context. We keep the manifest body compact: only fields it might want
 * to mutate (no audit history, no internal metadata).
 */

import type { TenantManifest } from "./schema";

/** Mutation surface — JSON-Schema-ish description. */
const TOOL_SURFACE = `
Available mutations (call by setting "name" and "args"):

UPDATE_BRAND        update_brand({ name?, subtitle?, footer_label?, footer_tagline?, primary_color?, logo?, logo_url? })
                    primary_color must be a hex like "#1b1f23". logo is one of: "oasis","sunbiz","suga","custom".

ADD_NAV_ITEM        add_nav_item({ href, label, icon, group, badge_key?, expandable?, position? })
                    icon must be one of the supported keys (LayoutDashboard, GitBranch, Brain, BookOpen, Bot, BarChart3,
                    Plug, Settings, Activity, Inbox, History, ShieldCheck, ShieldAlert, Radio, Users, BookUser, FileText,
                    Upload, HandCoins, BadgeDollarSign, RefreshCcw, DollarSign, MessageSquare, Mail, Landmark, FileCode2,
                    UsersRound, Code2, Megaphone, ShoppingBag, Heart, Sparkles).
                    group is a free-form heading like "Pipeline" / "System" / "Outreach".
                    position is the 0-based insertion index; omit for end of list.

REMOVE_NAV_ITEM     remove_nav_item({ href })
UPDATE_NAV_ITEM     update_nav_item({ href, changes: { label?, icon?, group?, badge_key?, expandable? } })
REORDER_NAV         reorder_nav({ order: ["/", "/leads", "/deals", ...] })   — order MUST list every nav href exactly once.

ENABLE_AGENT        enable_agent({ slug, display_name?, primary? })
                    Setting primary:true demotes the previous primary automatically.
DISABLE_AGENT       disable_agent({ slug })
UPDATE_AGENT        update_agent({ slug, changes: { display_name?, enabled?, prompt_overlay?, primary? } })
                    model_override is intentionally NOT editable from chat — that's a human-only setting.

ADD_DATA_ENTITY     add_data_entity({ name, label, fields?: [{name, type, required?, enum_values?, default?}] })
                    name must be snake_case [a-z][a-z0-9_]{0,62}. type is one of:
                    string | number | boolean | date | datetime | enum | json.
                    enum requires enum_values: ["..."].

REMOVE_DATA_ENTITY  remove_data_entity({ name })
ADD_FIELD_TO_ENTITY add_field_to_entity({ entity, field: {name, type, required?, enum_values?} })
REMOVE_FIELD_FROM_ENTITY remove_field_from_entity({ entity, field_name })

ADD_PAGE            add_page({ path, label, kind, entity?, config? })
                    kind is one of: dashboard | table | kanban | form | markdown | pipeline.
                    If kind is table/kanban/form, entity should reference an entity in data_model.
                    pipeline is a two-stack superview: config.lead_entity + config.opportunity_entity
                    name the two entities whose stage Kanbans render stacked (Salesforce-parity
                    Lead + Opportunity overview — see SunBiz /pipeline).

REMOVE_PAGE         remove_page({ path })

UPSERT_PROMPT       upsert_prompt({ agent_slug, label, prompt })   — adds or replaces a default prompt for the Reasoning tab.
REMOVE_PROMPT       remove_prompt({ agent_slug, label })

UPDATE_INDUSTRY     update_industry({ industry })   — one of: real_estate | business_funding | ecommerce | agency | custom.
`.trim();

const HARD_GUARDS = `
HARD GUARDS (do not propose, ever):
- Permissions changes (local_files, computer_control, web_access) — security-sensitive, human-only.
- Integration credential changes (credential_env_key) — rebinding secrets via chat is forbidden.
- agents[].model_override — billing-affecting, human-only.
If the user asks for any of these, explain in the "explanation" field that this needs the Settings page and return mutations: [].
`.trim();

const ENVELOPE_RULES = `
RESPONSE FORMAT — STRICT:

Reply with EXACTLY ONE JSON object on its own. No code fences, no leading prose, no trailing prose.
Schema:
  {
    "explanation": string,           // 1–4 sentences describing what you propose (or why no change is needed).
    "mutations": MutationCall[]      // array; empty when the user is just asking a question.
  }

MutationCall = { "name": "<mutation_name>", "args": { ... } }

Examples:

User: "Add a referral_source column to leads"
Response:
{"explanation":"Adding a string field 'referral_source' to the lead entity. It will become an editable column anywhere leads are rendered as a table.","mutations":[{"name":"add_field_to_entity","args":{"entity":"lead","field":{"name":"referral_source","type":"string"}}}]}

User: "What pages do I have?"
Response:
{"explanation":"You have 3 pages defined: leads (kanban), properties (table), deals (kanban). The catch-all renderer fills in any /t/<slug>/<path> the manifest defines.","mutations":[]}

User: "Change the brand color to navy and rename Bravo to 'Ops Lead'"
Response:
{"explanation":"Updating brand.primary_color to a navy (#0b1d3a) and renaming the Bravo agent's display name to 'Ops Lead' for this tenant.","mutations":[{"name":"update_brand","args":{"primary_color":"#0b1d3a"}},{"name":"update_agent","args":{"slug":"bravo","changes":{"display_name":"Ops Lead"}}}]}

If the user's intent is ambiguous, ask a clarifying question in the explanation and return mutations: []. Do NOT guess at destructive changes (entity removal, page removal) — confirm first.
`.trim();

export type ManifestEditorPromptInput = {
  tenantSlug: string;
  manifest: TenantManifest;
  /** Optional caller context to thread persona — e.g. "You are Bravo." */
  preamble?: string;
};

export function buildManifestEditorPrompt(input: ManifestEditorPromptInput): string {
  const preamble = input.preamble?.trim();
  const head = preamble
    ? `${preamble}\n\nYou are now operating in MANIFEST EDITOR MODE for tenant "${input.tenantSlug}".`
    : `You are the manifest editor for tenant "${input.tenantSlug}" — an OASIS AI Command Center.`;

  // Keep the manifest snapshot compact: drop verbose meta. The AI only needs
  // the editable shape, not timestamps or audit refs.
  const snapshot = {
    brand: input.manifest.brand,
    agents: input.manifest.agents,
    nav: input.manifest.nav,
    pages: input.manifest.pages || [],
    data_model: input.manifest.data_model || [],
    default_prompts: input.manifest.default_prompts || [],
    integrations: input.manifest.integrations || [],
    onboarding_industry: input.manifest.onboarding_industry,
  };

  return [
    head,
    "Your job: propose precise, valid mutations to this tenant's manifest, in response to natural-language requests from the operator. Be a thoughtful collaborator — explain trade-offs in 1–4 sentences, and don't guess at destructive changes.",
    "",
    "CURRENT MANIFEST:",
    JSON.stringify(snapshot, null, 2),
    "",
    TOOL_SURFACE,
    "",
    HARD_GUARDS,
    "",
    ENVELOPE_RULES,
  ].join("\n");
}
