/** Time + text formatting helpers shared across pages. */

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
