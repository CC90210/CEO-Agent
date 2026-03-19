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

interface SobrietyLogProps {
  dayCount: number;
  reflection: string;
}

const DayCountDisplay: React.FC<{ count: number }> = ({ count }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Dramatic zoom: spring from small scale to large
  const progress = spring({
    frame,
    fps,
    config: { damping: 10, stiffness: 80, mass: 1.5 },
  });
  const scale = interpolate(progress, [0, 1], [0.1, 1]);
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        transform: `scale(${scale})`,
        opacity,
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: 220,
          fontWeight: 900,
          color: BRAND.text,
          lineHeight: 0.85,
          fontFamily: "sans-serif",
        }}
      >
        {count}
      </div>
    </div>
  );
};

const DaysSoberLabel: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  const translateY = interpolate(frame, [0, 20], [16, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: 28,
          letterSpacing: 10,
          color: BRAND.accent,
          fontFamily: "sans-serif",
          fontWeight: 700,
        }}
      >
        DAYS SOBER
      </div>
    </div>
  );
};

const ReflectionText: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 50], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        padding: "0 80px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          fontSize: 40,
          color: BRAND.text,
          lineHeight: 1.6,
          fontFamily: "Georgia, serif",
          fontWeight: 400,
          fontStyle: "italic",
        }}
      >
        &ldquo;{text}&rdquo;
      </div>
    </div>
  );
};

const WarmOverlay: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 60], [0, 0.35], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(ellipse at 50% 80%, #3D2B1F ${opacity * 0}%, transparent 70%)`,
        // Warm amber vignette softening the scene
        boxShadow: `inset 0 0 ${interpolate(frame, [0, 60], [0, 300], {
          extrapolateRight: "clamp",
        })}px #2A1A0E`,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

export const SobrietyLog: React.FC<SobrietyLogProps> = ({
  dayCount,
  reflection,
}) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ background: BRAND.bg }}>
      {/* Main content stack */}
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          gap: 20,
        }}
      >
        {/* Frame 0–45: Day count scales up dramatically */}
        <Sequence from={0} durationInFrames={210} premountFor={fps} layout="none">
          <DayCountDisplay count={dayCount} />
        </Sequence>

        {/* Frame 45–60: "DAYS SOBER" label appears */}
        <Sequence from={45} durationInFrames={165} premountFor={fps} layout="none">
          <DaysSoberLabel />
        </Sequence>

        {/* Frame 60–150: Reflection fades in */}
        <Sequence from={60} durationInFrames={150} premountFor={fps} layout="none">
          <ReflectionText text={reflection} />
        </Sequence>
      </AbsoluteFill>

      {/* Frame 150–210: Warm gradient overlay fades in on top */}
      <Sequence from={150} durationInFrames={60} premountFor={fps}>
        <WarmOverlay />
      </Sequence>
    </AbsoluteFill>
  );
};
