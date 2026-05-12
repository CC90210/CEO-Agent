import { notFound } from "next/navigation";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card, PageHeader, Tag } from "@/components/Card";
import { loadPlaybook } from "@/lib/playbooks";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const AUDIENCE_TONE: Record<string, "accent" | "engaged" | "warm"> = {
  operator: "accent",
  client: "engaged",
  internal: "warm",
};

export default async function PlaybookSlugPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const file = await loadPlaybook(slug);
  if (!file) notFound();

  return (
    <div className="space-y-6 max-w-4xl">
      <PageHeader
        title={file.title}
        subtitle={
          <span>
            <Link href="/playbook" className="text-fg-muted hover:text-accent underline-offset-2 hover:underline">
              ← Playbook index
            </Link>
          </span>
        }
        action={<Tag tone={AUDIENCE_TONE[file.audience] ?? "accent"}>{file.audience}</Tag>}
      />
      <Card title="" subtitle="">
        <article className="prose prose-invert prose-headings:text-fg prose-p:text-fg-muted prose-strong:text-fg prose-a:text-accent max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{file.body}</ReactMarkdown>
        </article>
      </Card>
    </div>
  );
}
