"use client";

import { useFormStatus } from "react-dom";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";

/**
 * Approve/Deny submit pair for one exec_overrides row. Wraps the server
 * action in a client form so useFormStatus disables both buttons during
 * the round trip — without this, a slow network lets the operator click
 * twice and the second click hits a 'already_decided' (409) RPC error.
 * The consumer daemon is idempotent, so the data was always safe; this
 * just kills the bad UX.
 */
export function OverrideDecisionForms({
  requestId,
  action,
}: {
  requestId: string;
  action: (formData: FormData) => Promise<void>;
}) {
  return (
    <div className="flex items-center gap-3 pt-1">
      <form action={action} className="contents">
        <input type="hidden" name="request_id" value={requestId} />
        <input type="hidden" name="decision" value="approve" />
        <input
          type="text"
          name="reason"
          placeholder="optional reason"
          maxLength={500}
          className="flex-1 text-xs px-3 py-1.5 rounded border border-bg-border bg-bg-elev text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent"
        />
        <DecisionButton
          tone="engaged"
          label="Approve"
          submittingLabel="Approving…"
          Icon={CheckCircle2}
        />
      </form>
      <form action={action}>
        <input type="hidden" name="request_id" value={requestId} />
        <input type="hidden" name="decision" value="deny" />
        <DecisionButton
          tone="hot"
          label="Deny"
          submittingLabel="Denying…"
          Icon={XCircle}
        />
      </form>
    </div>
  );
}

function DecisionButton({
  tone,
  label,
  submittingLabel,
  Icon,
}: {
  tone: "engaged" | "hot";
  label: string;
  submittingLabel: string;
  Icon: typeof CheckCircle2;
}) {
  const { pending } = useFormStatus();
  const toneClass =
    tone === "engaged"
      ? "border-status-engaged/40 bg-status-engaged/10 text-status-engaged hover:bg-status-engaged/20"
      : "border-status-hot/40 bg-status-hot/10 text-status-hot hover:bg-status-hot/20";
  return (
    <button
      type="submit"
      disabled={pending}
      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded border ${toneClass} text-xs font-bold uppercase tracking-wider disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {pending ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        <Icon size={14} />
      )}
      {pending ? submittingLabel : label}
    </button>
  );
}
