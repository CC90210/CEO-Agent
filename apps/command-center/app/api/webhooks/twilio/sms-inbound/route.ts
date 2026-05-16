import { NextRequest, NextResponse } from "next/server";
import { createHmac, timingSafeEqual } from "node:crypto";
import { isStopCommand, suppressPhoneViaCasl } from "@/lib/sms-opt-out";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function timingSafeStringEqual(provided: string, expected: string): boolean {
  const providedBuffer = Buffer.from(provided);
  const expectedBuffer = Buffer.from(expected);
  if (providedBuffer.length !== expectedBuffer.length) return false;
  return timingSafeEqual(providedBuffer, expectedBuffer);
}

function verifyTwilioSignature(
  url: string,
  params: URLSearchParams,
  headerSig: string | null,
): boolean {
  if (!headerSig) return false;
  const token = (process.env.TWILIO_AUTH_TOKEN || "").trim();
  if (!token) return false;

  const sortedParams = Array.from(params.entries()).sort(([aKey, aVal], [bKey, bVal]) => {
    const keyCompare = aKey.localeCompare(bKey);
    return keyCompare || aVal.localeCompare(bVal);
  });
  const signatureBase = sortedParams.reduce(
    (acc, [key, value]) => `${acc}${key}${value}`,
    url,
  );
  const expected = createHmac("sha1", token).update(signatureBase, "utf8").digest("base64");
  return timingSafeStringEqual(headerSig.trim(), expected);
}

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const params = new URLSearchParams(rawBody);

  if (!verifyTwilioSignature(req.url, params, req.headers.get("x-twilio-signature"))) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  const from = params.get("From") || "";
  const body = params.get("Body") || "";

  if (from && isStopCommand(body)) {
    const result = await suppressPhoneViaCasl(from, "twilio_inbound");
    if (!result.ok) {
      console.error("[webhooks.twilio.sms-inbound] suppress-phone failed", result.error);
    }
  }

  return new NextResponse("<Response/>", {
    status: 200,
    headers: { "content-type": "text/xml; charset=utf-8" },
  });
}
