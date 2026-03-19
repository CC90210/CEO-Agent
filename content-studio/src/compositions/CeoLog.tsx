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

interface CeoLogProps {
  dayNumber: number;
  headline: string;
  body: string;
  metric: string;
}

const DayCounter: React.FC<{ dayNumber: number }> = ({ dayNumber }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps, config: { damping: 14, stiffness: 150 } });
  const scale = interpolate(progress, [0, 1], [0.3, 1]);
  const opacity = interpolate(progress, [0, 0.2], [0, 1]);

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
          fontSize: 28,
          letterSpacing: 8,
          color: BRAND.accent,
          fontFamily: "sans-serif",
          fontWeight: 700,
        }}
      >
        DAY
      </div>
      <div
        style={{
          fontSize: 160,
          fontWeight: 900,
          color: BRAND.text,
          lineHeight: 0.9,
          fontFamily: "sans-serif",
        }}
      >
        {dayNumber}
      </div>
    </div>
  );
};

const SlideInHeadline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps, config: { damping: 200 } });
  const translateX = interpolate(progress, [0, 1], [-80, 0]);
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        transform: `translateX(${translateX}px)`,
        opacity,
        padding: "0 64px",
      }}
    >
      <div
        style={{
          fontSize: 52,
          fontWeight: 800,
          color: BRAND.text,
          lineHeight: 1.2,
          fontFamily: "sans-serif",
        }}
      >
        {text}
      </div>
    </div>
  );
};

const BodyText: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 40], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        padding: "0 64px",
      }}
    >
      <div
        style={{
          fontSize: 36,
          color: BRAND.text,
          opacity: 0.8,
          lineHeight: 1.6,
          fontFamily: "sans-serif",
          fontWeight: 400,
        }}
      >
        {text}
      </div>
    </div>
  );
};

const MetricBar: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({ frame, fps, config: { damping: 200 } });
  const width = interpolate(progress, [0, 1], [0, 100]);
  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ opacity, padding: "0 64px" }}>
      <div
        style={{
          background: BRAND.navy,
          borderRadius: 12,
          overflow: "hidden",
          padding: "28px 36px",
          position: "relative",
        }}
      >
        {/* Accent fill bar animating width */}
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            height: "100%",
            width: `${width}%`,
            background: `linear-gradient(90deg, ${BRAND.accent}33, ${BRAND.accent}11)`,
          }}
        />
        <div
          style={{
            position: "relative",
            fontSize: 44,
            fontWeight: 800,
            color: BRAND.accent,
            fontFamily: "sans-serif",
            textAlign: "center",
          }}
        >
          {text}
        </div>
      </div>
    </div>
  );
};

const SignOff: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 30, 50, 60], [0, 1, 1, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        textAlign: "center",
        padding: "0 64px",
      }}
    >
      <div
        style={{
          fontSize: 30,
          color: BRAND.text,
          opacity: 0.5,
          fontFamily: "Georgia, serif",
          fontStyle: "italic",
          letterSpacing: 1,
        }}
      >
        Only good things from now on.
      </div>
    </div>
  );
};

export const CeoLog: React.FC<CeoLogProps> = ({
  dayNumber,
  headline,
  body,
  metric,
}) => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        background: BRAND.bg,
        justifyContent: "center",
        alignItems: "stretch",
        flexDirection: "column",
        gap: 40,
        padding: "80px 0",
      }}
    >
      {/* Frame 0–30: DAY counter zooms in */}
      <Sequence from={0} durationInFrames={300} premountFor={fps} layout="none">
        <DayCounter dayNumber={dayNumber} />
      </Sequence>

      {/* Frame 30–60: Headline slides in from left */}
      <Sequence from={30} durationInFrames={270} premountFor={fps} layout="none">
        <SlideInHeadline text={headline} />
      </Sequence>

      {/* Frame 60–180: Body fades in */}
      <Sequence from={60} durationInFrames={240} premountFor={fps} layout="none">
        <BodyText text={body} />
      </Sequence>

      {/* Frame 180–240: Metric highlight bar */}
      <Sequence from={180} durationInFrames={120} premountFor={fps} layout="none">
        <MetricBar text={metric} />
      </Sequence>

      {/* Frame 240–300: Sign-off fades in then out */}
      <Sequence from={240} durationInFrames={60} premountFor={fps} layout="none">
        <SignOff />
      </Sequence>
    </AbsoluteFill>
  );
};
