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
  navy: "#1A1A2E",
};

const BULLETS = [
  "Automated Lead Nurturing",
  "AI Content Engine",
  "Revenue Dashboard",
];

interface OasisPromoProps {
  headline: string;
  subheadline: string;
  ctaText: string;
}

const Logo: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  const scale = spring({ frame, fps, config: { damping: 200 } });

  return (
    <div
      style={{
        opacity,
        transform: `scale(${scale})`,
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: 56,
          fontWeight: 800,
          letterSpacing: 10,
          color: BRAND.accent,
          fontFamily: "sans-serif",
        }}
      >
        OASIS
      </div>
      <div
        style={{
          fontSize: 18,
          letterSpacing: 4,
          color: BRAND.text,
          opacity: 0.6,
          fontFamily: "sans-serif",
        }}
      >
        AI SOLUTIONS
      </div>
    </div>
  );
};

const Headline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps, config: { damping: 18, stiffness: 120 } });
  const translateY = interpolate(progress, [0, 1], [60, 0]);
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        transform: `translateY(${translateY}px)`,
        opacity,
        textAlign: "center",
        padding: "0 60px",
      }}
    >
      <div
        style={{
          fontSize: 64,
          fontWeight: 900,
          color: BRAND.text,
          lineHeight: 1.1,
          fontFamily: "sans-serif",
        }}
      >
        {text}
      </div>
    </div>
  );
};

const Subheadline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const translateY = interpolate(frame, [0, 30], [40, 0], {
    extrapolateRight: "clamp",
    easing: (t) => 1 - Math.pow(1 - t, 3),
  });
  const opacity = interpolate(frame, [0, 25], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        transform: `translateY(${translateY}px)`,
        opacity,
        textAlign: "center",
        padding: "0 80px",
      }}
    >
      <div
        style={{
          fontSize: 32,
          color: BRAND.text,
          opacity: 0.75,
          fontFamily: "sans-serif",
          fontWeight: 400,
        }}
      >
        {text}
      </div>
    </div>
  );
};

const BulletList: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24, padding: "0 80px" }}>
      {BULLETS.map((bullet, i) => {
        const delay = i * 20;
        const opacity = interpolate(frame, [delay, delay + 20], [0, 1], {
          extrapolateRight: "clamp",
          extrapolateLeft: "clamp",
        });
        const translateX = interpolate(frame, [delay, delay + 25], [-40, 0], {
          extrapolateRight: "clamp",
          extrapolateLeft: "clamp",
        });

        return (
          <div
            key={bullet}
            style={{
              opacity,
              transform: `translateX(${translateX}px)`,
              display: "flex",
              alignItems: "center",
              gap: 20,
            }}
          >
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: BRAND.accent,
                flexShrink: 0,
              }}
            />
            <div
              style={{
                fontSize: 34,
                color: BRAND.text,
                fontFamily: "sans-serif",
                fontWeight: 500,
              }}
            >
              {bullet}
            </div>
          </div>
        );
      })}
    </div>
  );
};

const CTA: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Pulse: sine wave on scale
  const pulse = interpolate(
    Math.sin((frame / fps) * Math.PI * 2),
    [-1, 1],
    [0.97, 1.03]
  );

  return (
    <div
      style={{
        opacity,
        transform: `scale(${pulse})`,
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          background: BRAND.accent,
          borderRadius: 12,
          padding: "24px 60px",
          fontSize: 32,
          fontWeight: 700,
          color: BRAND.bg,
          fontFamily: "sans-serif",
          letterSpacing: 1,
        }}
      >
        {text}
      </div>
    </div>
  );
};

export const OasisPromo: React.FC<OasisPromoProps> = ({
  headline,
  subheadline,
  ctaText,
}) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        background: BRAND.bg,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 48,
      }}
    >
      {/* Frame 0–30: Logo fade + scale */}
      <Sequence from={0} durationInFrames={30} premountFor={fps} layout="none">
        <Logo />
      </Sequence>

      {/* Frame 30–90: Headline spring up */}
      <Sequence from={30} durationInFrames={270} premountFor={fps} layout="none">
        <Headline text={headline} />
      </Sequence>

      {/* Frame 90–150: Subheadline slides up */}
      <Sequence from={90} durationInFrames={210} premountFor={fps} layout="none">
        <Subheadline text={subheadline} />
      </Sequence>

      {/* Frame 150–240: Bullets appear one by one */}
      <Sequence from={150} durationInFrames={150} premountFor={fps} layout="none">
        <BulletList />
      </Sequence>

      {/* Frame 240–300: CTA pulses in */}
      <Sequence from={240} durationInFrames={60} premountFor={fps} layout="none">
        <CTA text={ctaText} />
      </Sequence>
    </AbsoluteFill>
  );
};
