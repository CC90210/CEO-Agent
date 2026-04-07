import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

// Brand colors
const COLORS = {
  bg: "#141413",
  text: "#faf9f5",
  accent: "#D4A574",
  textMuted: "rgba(250, 249, 245, 0.55)",
};

// Font stack — no external font loads needed, universally available
const FONT_STACK =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif";

export interface QuoteCardProps {
  quote: string;
  author: string;
  pillar: string;
}

export const QuoteCard: React.FC<QuoteCardProps> = ({
  quote,
  author,
  pillar,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // --- Accent line: slides in from left over frames 0-20 ---
  const accentWidth = spring({
    frame,
    fps,
    from: 0,
    to: 80,
    config: { damping: 80, stiffness: 200, mass: 0.6 },
  });

  const accentOpacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  // --- Quote block: fades + rises in starting at frame 15 ---
  const quoteOpacity = interpolate(frame, [15, 45], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const quoteY = spring({
    frame: frame - 15,
    fps,
    from: 28,
    to: 0,
    config: { damping: 60, stiffness: 120, mass: 0.8 },
  });

  // --- Author line: fades in after quote settles (frame 60) ---
  const authorOpacity = interpolate(frame, [60, 90], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const authorY = spring({
    frame: frame - 60,
    fps,
    from: 16,
    to: 0,
    config: { damping: 70, stiffness: 140, mass: 0.6 },
  });

  // --- Pillar tag: appears last (frame 95) ---
  const pillarOpacity = interpolate(frame, [95, 115], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const formattedPillar = pillar.replace(/_/g, " ").toUpperCase();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        fontFamily: FONT_STACK,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "flex-start",
        padding: "0 88px",
      }}
    >
      {/* Accent line */}
      <div
        style={{
          width: accentWidth,
          height: 3,
          backgroundColor: COLORS.accent,
          opacity: accentOpacity,
          marginBottom: 48,
          borderRadius: 2,
        }}
      />

      {/* Quote text */}
      <div
        style={{
          opacity: quoteOpacity,
          transform: `translateY(${quoteY}px)`,
          marginBottom: 40,
        }}
      >
        {/* Opening quotation mark */}
        <div
          style={{
            fontSize: 96,
            lineHeight: 0.8,
            color: COLORS.accent,
            marginBottom: 16,
            fontWeight: 700,
            opacity: 0.7,
          }}
        >
          &ldquo;
        </div>
        <p
          style={{
            fontSize: 58,
            lineHeight: 1.35,
            color: COLORS.text,
            fontWeight: 600,
            margin: 0,
            letterSpacing: "-0.5px",
          }}
        >
          {quote}
        </p>
      </div>

      {/* Author */}
      <div
        style={{
          opacity: authorOpacity,
          transform: `translateY(${authorY}px)`,
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        {/* Small accent dash before author */}
        <div
          style={{
            width: 32,
            height: 2,
            backgroundColor: COLORS.accent,
            borderRadius: 1,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontSize: 34,
            color: COLORS.textMuted,
            fontWeight: 500,
            letterSpacing: "0.5px",
          }}
        >
          {author}
        </span>
      </div>

      {/* Pillar tag — bottom-left watermark */}
      <div
        style={{
          position: "absolute",
          bottom: 72,
          left: 88,
          opacity: pillarOpacity,
        }}
      >
        <span
          style={{
            fontSize: 22,
            color: COLORS.accent,
            fontWeight: 600,
            letterSpacing: "2.5px",
            textTransform: "uppercase",
            opacity: 0.65,
          }}
        >
          {formattedPillar}
        </span>
      </div>
    </AbsoluteFill>
  );
};
