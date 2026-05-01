/** Time + text formatting helpers shared across pages. */

/**
 * Convert a 24h time range like "08:00 — 09:00" or "17:00 onwards" into
 * 12h with AM/PM, preserving the rest of the label.
 *
 *   "08:00 — 09:00"   -> "8:00 AM – 9:00 AM"
 *   "12:30 — 13:00"   -> "12:30 PM – 1:00 PM"
 *   "17:00 onwards"   -> "5:00 PM onwards"
 *   "00:30"           -> "12:30 AM"
 */
export function formatTimeRange(label: string | null | undefined): string {
  if (!label) return "";
  // Normalize em-dash variants to en-dash for visual consistency.
  const normalized = label.replace(/\s+[—–-]\s+/g, " – ");
  return normalized.replace(/(\d{1,2}):(\d{2})/g, (match, h: string, m: string) => {
    const hh = parseInt(h, 10);
    if (Number.isNaN(hh) || hh < 0 || hh > 23) return match;
    const mm = m;
    const period = hh >= 12 ? "PM" : "AM";
    const displayH = hh === 0 ? 12 : hh > 12 ? hh - 12 : hh;
    return `${displayH}:${mm} ${period}`;
  });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  const sec = Math.round((now - then) / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hrs = Math.round(min / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function truncate(text: string | null | undefined, max = 80): string {
  if (!text) return "";
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}

/** Map a status string to a Tailwind text-color utility. */
export function statusColor(status: string | null | undefined): string {
  switch ((status || "").toLowerCase()) {
    case "hot":
    case "failed":
    case "escalated":
    case "escalated_by_critic":
      return "text-status-hot";
    case "warm":
    case "deferred":
    case "shadow":
      return "text-status-warm";
    case "sent":
    case "engaged":
    case "won":
      return "text-status-engaged";
    case "cold":
    case "queued":
      return "text-status-cold";
    case "dormant":
      return "text-status-dormant";
    case "lost":
      return "text-status-lost";
    default:
      return "text-fg-muted";
  }
}

/** Color the intent label coming from the inbound classifier. */
export function intentColor(intent: string | null | undefined): string {
  switch ((intent || "").toLowerCase()) {
    case "booking":
    case "reply_positive":
    case "referral":
      return "text-status-engaged";
    case "pricing":
    case "info_request":
      return "text-status-warm";
    case "objection":
    case "reply_negative":
      return "text-status-hot";
    case "unsubscribe":
    case "spam_bounce":
      return "text-status-dormant";
    case "out_of_office":
    case "noise":
    case "other":
    default:
      return "text-fg-muted";
  }
}
