/**
 * Shared helpers for Supabase Storage routes. Sanitization in particular
 * must be identical across uploaders — every storage path lives under
 * <tenant_id>/... so a sloppy filename could escape the tenant folder.
 */

/**
 * Strip directory-traversal, collapse whitespace, drop characters that
 * have no business in a storage object name. Returns a non-empty string
 * (falls back to a timestamped placeholder when the input sanitizes to
 * nothing).
 */
export function sanitizeStorageFilename(name: string): string {
  return (
    name
      .replace(/[/\\]/g, "_")
      .replace(/\.\.+/g, "_")
      .replace(/\s+/g, "_")
      .replace(/[^a-zA-Z0-9._-]/g, "")
      .slice(0, 120) || `file_${Date.now()}`
  );
}
