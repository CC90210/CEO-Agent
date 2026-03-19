import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";

const BRAND = {
  bg: "#0A0A0A",
  text: "#FAF9F5",
  accent: "#00D4AA",
};

interface QuoteDropProps {
  quote: string;
  author: string;
}

const QuoteMark: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        fontSize: 200,
        lineHeight: 1,
        color: BRAND.accent,
        fontFamily: "Georgia, serif",
        opacity,
        // Offset so it sits as a decorative element above the quote
        marginBottom: -60,
        alignSelf: "flex-start",
        paddingLeft: 60,
      }}
    >
      &ldquo;
    </div>
  );
};

const TypewriterQuote: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  // 60-frame window to type the full string (frames 0–60 inside this Sequence)
  const charsToShow = Math.floor(
    interpolate(frame, [0, 60], [0, text.length], {
      extrapolateRight: "clamp",
    })
  );

  return (
    <div
      style={{
        fontSize: 52,
        fontWeight: 600,
        color: BRAND.text,
        fontFamily: "Georgia, serif",
        lineHeight: 1.4,
        padding: "0 64px",
        textAlign: "center",
      }}
    >
      {text.slice(0, charsToShow)}
    </div>
  );
};

const AuthorLine: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 25], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
      }}
    >
      <div
        style={{
          width: 48,
          height: 2,
          background: BRAND.accent,
        }}
      />
      <div
        style={{
          fontSize: 28,
          color: BRAND.text,
          opacity: 0.7,
          fontFamily: "sans-serif",
          fontWeight: 400,
          letterSpacing: 2,
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const QuoteDrop: React.FC<QuoteDropProps> = ({ quote, author }) => {
  const { fps } = useVideoConfig();

  // Frame 120–150: scale pulse on the whole card
  const frame = useCurrentFrame();
  const pulse = spring({
    frame: frame - 120,
    fps,
    config: { damping: 8, stiffness: 180 },
  });
  // pulse goes 0→1 with bounce; map to a subtle scale around 1.0
  const scale = interpolate(pulse, [0, 1], [1, 1.015]);

  return (
    <AbsoluteFill
      style={{
        background: BRAND.bg,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          transform: `scale(${scale})`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 32,
          width: "100%",
        }}
      >
        {/* Frame 0–30: quotation mark fades in */}
        <Sequence from={0} durationInFrames={150} premountFor={fps} layout="none">
          <QuoteMark />
        </Sequence>

        {/* Frame 30–90: quote types in letter by letter */}
        <Sequence from={30} durationInFrames={120} premountFor={fps} layout="none">
          <TypewriterQuote text={quote} />
        </Sequence>

        {/* Frame 90–120: author fades in */}
        <Sequence from={90} durationInFrames={60} premountFor={fps} layout="none">
          <AuthorLine text={author} />
        </Sequence>
      </div>
    </AbsoluteFill>
  );
};
