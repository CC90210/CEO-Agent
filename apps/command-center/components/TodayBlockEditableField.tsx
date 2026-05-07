"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * Click-to-edit field for a Today schedule item. Wraps a span — single
 * click → contenteditable → blur or Enter saves via PATCH /api/daily-plan,
 * Esc cancels. Used for the slot title and body so the operator can
 * tweak the day without leaving /today.
 *
 * Optimistic: shows the new text immediately, reverts on error.
 */
export function TodayBlockEditableField({
  index,
  field,
  initial,
  schedule,
  className = "",
  multiline = false,
}: {
  index: number;
  field: "title" | "body";
  initial: string;
  schedule: Array<Record<string, unknown>>;
  className?: string;
  multiline?: boolean;
}) {
  const router = useRouter();
  const [value, setValue] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      if (inputRef.current instanceof HTMLInputElement) {
        inputRef.current.select();
      }
    }
  }, [editing]);

  async function save() {
    if (busy) return;
    const trimmed = value.trim();
    if (!trimmed || trimmed === initial) {
      setValue(initial);
      setEditing(false);
      return;
    }
    setBusy(true);
    try {
      const updated = schedule.map((b, i) => (i === index ? { ...b, [field]: trimmed } : b));
      const r = await fetch("/api/daily-plan", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schedule: updated }),
      });
      if (r.ok) {
        router.refresh();
      } else {
        setValue(initial);
      }
    } catch {
      setValue(initial);
    } finally {
      setBusy(false);
      setEditing(false);
    }
  }

  function cancel() {
    setValue(initial);
    setEditing(false);
  }

  if (!editing) {
    return (
      <span
        role="button"
        tabIndex={0}
        onClick={() => setEditing(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setEditing(true);
          }
        }}
        className={`${className} cursor-text hover:bg-bg-elev/50 rounded px-1 -mx-1 transition-colors`}
        title="Click to edit"
      >
        {value || initial}
      </span>
    );
  }

  if (multiline) {
    return (
      <textarea
        ref={inputRef as React.RefObject<HTMLTextAreaElement>}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            save();
          } else if (e.key === "Escape") {
            cancel();
          }
        }}
        disabled={busy}
        rows={2}
        className={`${className} bg-bg-elev border border-accent rounded px-2 py-1 outline-none w-full resize-none`}
      />
    );
  }
  return (
    <input
      ref={inputRef as React.RefObject<HTMLInputElement>}
      type="text"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          save();
        } else if (e.key === "Escape") {
          cancel();
        }
      }}
      disabled={busy}
      className={`${className} bg-bg-elev border border-accent rounded px-2 py-0.5 outline-none w-full`}
    />
  );
}
