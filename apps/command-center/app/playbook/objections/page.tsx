import Link from "next/link";
import { Card, PageHeader, Tag } from "@/components/Card";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-static";

const OBJECTIONS = [
  {
    trigger: "Send me info.",
    response:
      "Yeah I can do that — but the info I send only makes sense after 5 minutes on the phone, otherwise it's just noise. What's the actual concern, that we're not legit, or that AI feels too early for you?",
  },
  {
    trigger: "Too expensive / no budget.",
    response:
      "I haven't quoted you anything yet. So is it that you're worried it won't be worth what we charge, or that you can't justify any new spend right now no matter what?",
  },
  {
    trigger: "We have someone.",
    response:
      "Smart, that's a sign you're growth-oriented. Out of curiosity — are they doing AI specifically, or running ads/marketing? Different categories. I just want to make sure I'm not stepping on toes.",
  },
  {
    trigger: "Not interested.",
    response:
      "Totally fair. Out of curiosity though — is it that AI feels too early for the business, or you've tried something before and it didn't deliver? I'm trying to figure out what people actually need.",
  },
  {
    trigger: "It's a bad time.",
    response:
      "Got it. When's a better time — a week, a month, never? Just being real with you — I'd rather know now than chase you for nothing.",
  },
  {
    trigger: "I'll think about it.",
    response:
      "Of course. What's the part you actually want to think about — the technology, the cost, the timing, or whether we're the right people?",
  },
  {
    trigger: "Sounds too good to be true.",
    response:
      "I get that a lot — that's exactly why I do it free for 14 days. There's literally no scenario where you lose money. If the work doesn't deliver, I eat the build cost. The risk is on me, not you.",
  },
  {
    trigger: "How does it actually work?",
    response:
      "Quick version: we pick one process, build the AI to run it, hand it over, you use it for 14 days. We measure the impact together on day 14. If it saved you what we promised, you pay implementation plus monthly. If not, walk. That simple.",
  },
];

export default function ObjectionsPage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <Link
        href="/playbook"
        className="inline-flex items-center gap-1.5 text-xs text-fg-muted hover:text-accent transition-colors"
      >
        <ArrowLeft size={14} /> Playbook
      </Link>

      <PageHeader
        title="Objection Handlers"
        subtitle="Universal rule: question, don't answer. The objection is rarely the real reason."
        action={<Tag tone="accent">8 patterns</Tag>}
      />

      <Card noPadding>
        <table className="w-full">
          <thead>
            <tr className="border-b border-bg-border">
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-accent font-bold px-5 py-3 w-1/3">
                What they say
              </th>
              <th className="text-left text-[10px] uppercase tracking-[0.14em] text-accent font-bold px-5 py-3">
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
                  <span className="text-status-hot font-medium text-sm">
                    "{o.trigger}"
                  </span>
                </td>
                <td className="px-5 py-4 text-fg text-sm leading-relaxed">
                  {o.response}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card title="The drill">
        <div className="text-sm text-fg leading-relaxed space-y-2">
          <p>
            Run this every day at midday for 10 minutes. Pull this page up. Say the trigger out loud, pause one second, then deliver the response. Speed up each round.
          </p>
          <p>
            <span className="text-accent font-bold">Goal:</span> by Day 14 you respond inside 1.5 seconds. No thinking. Pure muscle memory.
          </p>
        </div>
      </Card>
    </div>
  );
}
