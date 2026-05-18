/**
 * Role-based action allow/deny lists.
 *
 * Centralizes the "what can read_only users NOT do" list used by both
 * the cloud-tool palette filter (strips write tools before the model
 * even sees them) and the marker-action dispatcher (hard-rejects any
 * write that slipped through via a jailbreak / prompt-leak).
 *
 * Without this constant the two surfaces carry parallel hand-typed
 * sets that can silently drift — exactly the kind of split that breaks
 * security boundaries during refactors.
 */

/**
 * Cloud-tool names a read_only operator MUST NOT call. Filtered out
 * of `toolPalette` in /api/chat/route.ts before stream start so the
 * model doesn't even see them.
 */
export const READ_ONLY_DENIED_TOOLS = new Set<string>([
  "create_record",
  "update_record",
  "delete_record",
  "send_email",
  "send_sms",
  "write_file",
  "bash",
  "run_script",
]);

/**
 * Marker action types a read_only operator MUST NOT execute. Caught
 * by the dispatcher in /api/chat/route.ts — superset of the tool list
 * above because some operator actions (update_profile,
 * toggle_agent_enabled) aren't in the cloud-tool palette but still
 * mutate state.
 */
export const READ_ONLY_DENIED_MARKERS = new Set<string>([
  "create_record",
  "update_record",
  "delete_record",
  "update_profile",
  "toggle_agent_enabled",
]);

/** Marker action types that the cloud-tool native loop ALSO emits — used
 *  to dedupe so we don't double-execute when the model both tool_calls AND
 *  text-markers the same write. */
export const TOOL_NATIVE_MARKER_TYPES = new Set<string>([
  "create_record",
  "update_record",
  "delete_record",
]);

export function isReadOnlyRole(teamRole: string | null | undefined): boolean {
  return (teamRole || "").trim().toLowerCase() === "read_only";
}
