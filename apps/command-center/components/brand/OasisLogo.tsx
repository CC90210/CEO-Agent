/**
 * OasisLogo — single canonical place to render the OASIS AI mark.
 *
 * Backed by /public/oasis-logo.jpg (the circuit-tree icon also used on
 * oasisai.work — brand consistency across the marketing site and the
 * dashboard).  Wraps next/image so it gets static optimization + lazy
 * loading where appropriate.
 *
 * Replaces three previous patterns scattered across the app:
 *   1. <Image src="/oasis-logo.svg" ...> — generic blue placeholder
 *      shipped before the real brand existed
 *   2. Gradient-O divs with `O` text — used on /configure and /onboarding
 *   3. Hand-rolled wrappers with bespoke ring / shadow / sizing
 *
 * Usage:
 *   <OasisLogo size={36} />
 *   <OasisLogo size={48} priority />
 */

import Image from "next/image";

export function OasisLogo({
  size = 40,
  priority = false,
  className = "",
}: {
  size?: number;
  priority?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-block rounded-lg overflow-hidden ring-1 ring-accent/40 shadow-[0_0_18px_-4px_rgba(0,212,255,0.55)] ${className}`}
      style={{ width: size, height: size }}
    >
      <Image
        src="/oasis-logo.jpg"
        alt="OASIS AI"
        width={size}
        height={size}
        priority={priority}
        className="w-full h-full object-cover"
      />
    </span>
  );
}
