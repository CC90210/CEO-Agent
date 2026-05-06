"use client";

/**
 * Global error boundary — catches errors thrown in the ROOT layout itself
 * (where error.tsx can't help because the layout is the boundary).
 *
 * This must include its own <html><body> shell since the parent layout
 * has already failed.
 */

import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error.tsx]", error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          backgroundColor: "#020409",
          color: "#f5f7fa",
          fontFamily:
            '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", Roboto, sans-serif',
          minHeight: "100vh",
          margin: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "2rem",
        }}
      >
        <div
          style={{
            maxWidth: 480,
            padding: "1.75rem",
            borderRadius: 16,
            border: "1px solid #1e2532",
            background: "#0b0f17",
          }}
        >
          <h1 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>
            The dashboard couldn&apos;t load
          </h1>
          <p
            style={{
              fontSize: "0.875rem",
              color: "#9ba3b1",
              marginTop: "0.5rem",
              lineHeight: 1.55,
            }}
          >
            A fatal error stopped the root layout from rendering. Try a refresh.
            If this keeps happening, capture the digest and check Vercel
            function logs.
          </p>
          {error.digest && (
            <div
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                fontSize: 11,
                color: "#6c7180",
                background: "#020409",
                border: "1px solid #1e2532",
                borderRadius: 6,
                padding: "0.5rem 0.75rem",
                marginTop: "0.875rem",
                wordBreak: "break-all",
              }}
            >
              digest: {error.digest}
            </div>
          )}
          <button
            onClick={() => reset()}
            style={{
              marginTop: "1rem",
              padding: "0.55rem 1rem",
              borderRadius: 6,
              border: "1px solid rgba(59,130,246,0.3)",
              background: "#3b82f6",
              color: "#020409",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
