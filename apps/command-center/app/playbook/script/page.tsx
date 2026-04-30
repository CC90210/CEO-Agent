"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import {
  STAGE_1_PATTERN_INTERRUPT,
  STAGE_4_PIVOT,
  STAGE_5_CLOSE,
  TRACK_STAGES,
  TRACK_LABELS,
  TRACK_DESCRIPTIONS,
  OBJECTIONS,
  TRACKS,
  type ProspectTrack,
} from "@/lib/playbook";

export default function ScriptPage() {
  const [track, setTrack] = useState<ProspectTrack>("service_trades");
  const trackStages = TRACK_STAGES[track];

  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-fg">
            Cold Call Script + Objections
          </h1>
          <p className="text-sm text-fg-muted mt-1.5">
            One page. Memorize. Drill. Run it without thinking. Total runtime: 2:50–3:10.
          </p>
        </div>
      </header>

      {/* Track selector */}
      <div className="bg-bg-panel border border-bg-border rounded-xl p-4">
        <div className="text-[10px] uppercase tracking-[0.14em] font-bold text-fg-muted mb-2">
          Prospect track
        </div>
        <div className="flex flex-wrap gap-2">
          {TRACKS.map((t) => (
            <button
              key={t}
              onClick={() => setTrack(t)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-all ${
                track === t
                  ? "bg-accent text-bg shadow-glow"
                  : "bg-bg-elev text-fg-muted border border-bg-border hover:bg-bg-hover hover:text-fg"
              }`}
            >
              {TRACK_LABELS[t]}
            </button>
          ))}
        </div>
        <div className="text-xs text-fg-dim mt-3 italic">
          {TRACK_DESCRIPTIONS[track]}
        </div>
      </div>

      {/* The 5 stages */}
      <div className="bg-bg-panel border border-bg-border rounded-xl p-5 space-y-5">
        <Stage
          num={STAGE_1_PATTERN_INTERRUPT.num}
          title={STAGE_1_PATTERN_INTERRUPT.title}
          duration={STAGE_1_PATTERN_INTERRUPT.duration}
          purpose={STAGE_1_PATTERN_INTERRUPT.purpose}
          line={STAGE_1_PATTERN_INTERRUPT.line}
          why={STAGE_1_PATTERN_INTERRUPT.why}
        />
        <Stage
          num="02"
          title="The Reason"
          duration="~20 sec"
          purpose="Plant the pain. Don't pitch yet."
          line={trackStages.stage2_line}
          why='"I&apos;m not sure if..." is the NEPQ disarm — a question dressed as a statement. Forces the prospect to think. The second they&apos;re thinking, they&apos;re engaged.'
        />
        <Stage
          num="03"
          title="Diagnose"
          duration="~90 sec"
          purpose="Five questions. Listen more than you talk."
          questions={trackStages.stage3_questions}
          why="Q5 is the consequence question. It's where they sell themselves. Don't skip. Don't soften. Ask it. Wait. Let silence do the work."
        />
        <Stage
          num={STAGE_4_PIVOT.num}
          title={STAGE_4_PIVOT.title}
          duration={STAGE_4_PIVOT.duration}
          purpose={STAGE_4_PIVOT.purpose}
          line={STAGE_4_PIVOT.line}
          why={STAGE_4_PIVOT.why}
        />
        <Stage
          num={STAGE_5_CLOSE.num}
          title={STAGE_5_CLOSE.title}
          duration={STAGE_5_CLOSE.duration}
          purpose={STAGE_5_CLOSE.purpose}
          line={STAGE_5_CLOSE.line}
          why={STAGE_5_CLOSE.why}
        />
      </div>

      {/* Objection table */}
      <div className="bg-bg-panel border border-bg-border rounded-xl">
        <header className="border-b border-bg-border px-5 py-3.5">
          <h2 className="text-xs font-bold uppercase tracking-[0.14em] text-accent">
            Objection Handlers
          </h2>
          <p className="text-xs text-fg-muted mt-1">
            Universal rule: question, don't answer. The objection is rarely the real reason.
          </p>
        </header>
        <table className="w-full">
          <thead>
            <tr className="border-b border-bg-border">
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold px-5 py-3 w-1/3">
                What they say
              </th>
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-fg-muted font-bold px-5 py-3">
                What you say
              </th>
            </tr>
          </thead>
          <tbody>
            {OBJECTIONS.map((o, i) => (
              <tr
                key={i}
                className="border-b border-bg-border last:border-0 hover:bg-bg-hover/30 transition-colors"
              >
                <td className="px-5 py-4 align-top">
                  <span className="text-status-hot font-medium text-sm">"{o.trigger}"</span>
                </td>
                <td className="px-5 py-4 text-fg text-sm leading-relaxed">{o.response}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-bg-panel border border-bg-border rounded-xl p-5">
        <h3 className="text-xs uppercase tracking-[0.14em] font-bold text-accent mb-2">
          The drill
        </h3>
        <p className="text-fg text-sm leading-relaxed">
          Pull this page up at midday for 10 minutes. Say the trigger out loud, pause one second, then deliver the response. Speed up each round.{" "}
          <strong>Goal:</strong> by Day 14 you respond inside 1.5 seconds. No thinking. Pure muscle memory.
        </p>
      </div>
    </div>
  );
}

function Stage({
  num,
  title,
  duration,
  purpose,
  line,
  questions,
  why,
}: {
  num: string;
  title: string;
  duration: string;
  purpose: string;
  line?: string;
  questions?: string[];
  why: string;
}) {
  return (
    <div className="border-l-2 border-accent pl-5">
      <div className="flex items-baseline gap-3 mb-2">
        <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
          Stage {num}
        </span>
        <span className="text-fg font-bold text-base">{title}</span>
        <span className="text-fg-dim text-xs ml-auto">{duration}</span>
      </div>
      <div className="text-fg-muted text-sm italic mb-3">{purpose}</div>
      {line && (
        <blockquote className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-3 text-fg leading-relaxed">
          {line}
        </blockquote>
      )}
      {questions && (
        <ol className="space-y-2">
          {questions.map((q, i) => (
            <li
              key={i}
              className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-2.5 text-fg text-sm leading-relaxed"
            >
              <span className="text-accent font-bold mr-2">{i + 1}.</span>
              {q}
            </li>
          ))}
        </ol>
      )}
      <div className="mt-3 text-xs text-fg-dim italic">
        <span className="text-fg-muted font-semibold not-italic">Why →</span> {why}
      </div>
    </div>
  );
}
