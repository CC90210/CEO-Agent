import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-static";

const STAGES = [
  {
    num: "01",
    title: "Pattern Interrupt",
    duration: "~15 sec",
    purpose: "Disarm. Get permission.",
    line: "Hey [Name], it's Conaugh — we haven't spoken before, this is a cold call. You can hang up, or give me 30 seconds to tell you why I'm calling. Fair?",
    why:
      "Pattern interrupt. They expect a salesy opener; you give them honesty + control. ~80% say 'fair' out of curiosity. The 20% who hang up weren't going to buy anyway.",
  },
  {
    num: "02",
    title: "The Reason",
    duration: "~20 sec",
    purpose: "Plant the pain. Don't pitch yet.",
    line:
      "I work with [their niche] businesses around [region], and a lot of them are losing 8 to 15 hours a week to admin work — booking, follow-ups, lead chasing. I'm not sure if that's something you've thought about, but I figured you'd be the right person to ask.",
    why:
      '"I\'m not sure if..." is the NEPQ disarm — a question dressed as a statement. Forces the prospect to think. The second they\'re thinking, they\'re engaged.',
  },
  {
    num: "03",
    title: "Diagnose",
    duration: "~90 sec",
    purpose: "Five questions. Listen more than you talk.",
    questions: [
      "Walk me through how your team currently handles [process]. Just so I understand.",
      "How long does that take per week, ballpark?",
      "Have you looked at any tools or AI for it before? What stopped you?",
      "If that just… happened in the background and you got those hours back — what would you actually do with the time?",
      "And if nothing changes — same setup 12 months from now — what does that look like for the business?",
    ],
    why:
      "Q5 is the consequence question. It's where they sell themselves. Don't skip. Don't soften. Ask it. Wait. Let silence do the work.",
  },
  {
    num: "04",
    title: "The Pivot",
    duration: "~30 sec",
    purpose: "Drop the offer that makes saying no irrational.",
    line:
      "Here's what I do differently from anyone else you've probably talked to. I don't ask you to pay anything up front. We pick one process — the most painful one — we build the AI for it, and you run it for 14 days. If it saves you the time and money we projected, you pay implementation plus a small monthly to keep it running. If it doesn't, you owe me nothing and I walk. I'm that confident in the work. Worth a 15-minute walkthrough this week to see if it's a fit?",
    why:
      "Transfers risk onto OASIS. The 'no' gets very hard to say. There's literally no scenario where the prospect loses money.",
  },
  {
    num: "05",
    title: "The Close",
    duration: "~15 sec",
    purpose: "Two options. Never open-ended.",
    line: "I've got Tuesday at 2pm or Thursday at 10am open. Which works?",
    why:
      "Never 'let me know what works.' Always two specific slots. Binary choice processes 4× faster than open-ended ask.",
  },
];

export default function ColdCallScript() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Cold Call Script · V1"
        subtitle="Memorize. Drill. Run it without thinking. Total runtime: 2:50–3:10."
        action={<Tag tone="accent">NEPQ · AI services</Tag>}
      />

      <Card>
        <ul className="space-y-5">
          {STAGES.map((s) => (
            <li
              key={s.num}
              className="border-l-2 border-accent pl-5 py-1"
            >
              <div className="flex items-baseline gap-3 mb-2">
                <span className="text-accent text-[10px] font-bold tracking-[0.2em] uppercase">
                  Stage {s.num}
                </span>
                <span className="text-fg font-bold text-base">{s.title}</span>
                <span className="text-fg-dim text-xs ml-auto">{s.duration}</span>
              </div>
              <div className="text-fg-muted text-sm italic mb-3">{s.purpose}</div>
              {s.line && (
                <blockquote className="bg-accent-soft border-l-2 border-accent rounded-r-md px-4 py-3 text-fg leading-relaxed">
                  {s.line}
                </blockquote>
              )}
              {s.questions && (
                <ol className="space-y-2">
                  {s.questions.map((q, i) => (
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
                <span className="text-fg-muted font-semibold not-italic">Why →</span>{" "}
                {s.why}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Variants by deal type">
        <div className="space-y-3 text-sm">
          <div>
            <span className="text-accent font-bold">Custom-software prospects (Jonathan-style):</span>{" "}
            <span className="text-fg">
              swap Stage 4 to: "We run a free strategy session, scope a fixed-price build, and you only pay 50% deposit when you're 100% bought into the scope."
            </span>
          </div>
          <div>
            <span className="text-accent font-bold">C-suite consulting prospects:</span>{" "}
            <span className="text-fg">
              "We do a free 30-minute pitch call where I show you exactly what the AI strategy roadmap would look like for your business. You walk away with a deliverable either way."
            </span>
          </div>
        </div>
      </Card>
    </div>
  );
}
