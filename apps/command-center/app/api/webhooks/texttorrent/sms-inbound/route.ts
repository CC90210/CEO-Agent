import { NextRequest, NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "node:crypto";
import { isStopCommand, suppressPhoneViaCasl } from "@/lib/sms-opt-out";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type TextTorrentInbound = {
  from?: unknown;
  body?: unknown;
};

function timingSafeStringEqual(provided: string, expected: string): boolean {
  const providedBuffer = Buffer.from(provided);
  const expectedBuffer = Buffer.from(expected);
  if (providedBuffer.length !== expectedBuffer.length) return false;
  return timingSafeEqual(providedBuffer, expectedBuffer);
}

function verifyTextTorrentSignature(rawBody: string, headerSig: string | null): boolean {
  if (!headerSig) return false;
  const secret = (process.env.TEXTTORRENT_WEBHOOK_SECRET || "").trim();
  if (!secret) return false;

  const expected = createHmac("sha256", secret).update(rawBody, "utf8").digest("base64");
  return timingSafeStringEqual(headerSig.trim(), expected);
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();

  if (!verifyTextTorrentSignature(rawBody, req.headers.get("x-tt-signature"))) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  let payload: TextTorrentInbound;
  try {
    payload = JSON.parse(rawBody) as TextTorrentInbound;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const from = typeof payload.from === "string" ? payload.from : "";
  const body = typeof payload.body === "string" ? payload.body : "";

  if (from && isStopCommand(body)) {
    const result = await suppressPhoneViaCasl(from, "texttorrent_inbound");
    if (!result.ok) {
      console.error("[webhooks.texttorrent.sms-inbound] suppress-phone failed", result.error);
    }
  }

  return NextResponse.json({ ok: true });
}
