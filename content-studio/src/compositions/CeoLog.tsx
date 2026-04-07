import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
  Sequence,
} from "remotion";
import { loadFont, fontFamily } from "@remotion/google-fonts/SpaceGrotesk";

loadFont("normal", { weights: ["400", "500", "700"], subsets: ["latin"] });

// ─── Design tokens ────────────────────────────────────────────────────────────
const C = {
  navyDeep: "#0a0f1e",
  emeraldDeep: "#0a2620",
  charcoal: "#1a1a2e",
  cyan: "#00D4AA",
  green: "#00FF88",
  white: "#FAF9F5",
  circuitLine: "rgba(0, 212, 170, 0.10)",
  circuitLineBright: "rgba(0, 212, 170, 0.22)",
  darkPanel: "rgba(255,255,255,0.03)",
  panelBorder: "rgba(0, 212, 170, 0.14)",
};

// ─── Circuit board SVG background ────────────────────────────────────────────
const CircuitPattern: React.FC<{ pulse: number }> = ({ pulse }) => {
  const bright = interpolate(pulse, [0, 1], [0.08, 0.18]);

  const paths = [
    // Horizontal trunk lines
    "M 0 320 H 260 V 480 H 380",
    "M 1080 680 H 820 V 560 H 700",
    "M 0 900 H 140 V 780 H 340 V 720",
    "M 1080 1100 H 940 V 1240 H 760 V 1340",
    "M 0 1500 H 180 V 1420 H 420",
    "M 1080 1680 H 880 V 1600 H 640 V 1520",
    // Vertical trunk lines
    "M 120 0 V 200 H 220 V 460",
    "M 960 0 V 340 H 820 V 520",
    "M 200 1920 V 1700 H 340 V 1540",
    "M 880 1920 V 1760 H 740 V 1600",
    // Node dots (rendered as tiny rects in SVG)
  ];

  const nodes = [
    { cx: 260, cy: 320 }, { cx: 380, cy: 480 },
    { cx: 820, cy: 680 }, { cx: 700, cy: 560 },
    { cx: 140, cy: 900 }, { cx: 340, cy: 780 },
    { cx: 940, cy: 1100 }, { cx: 760, cy: 1240 },
    { cx: 180, cy: 1500 }, { cx: 420, cy: 1420 },
    { cx: 880, cy: 1680 }, { cx: 640, cy: 1600 },
    { cx: 120, cy: 200 }, { cx: 220, cy: 460 },
    { cx: 960, cy: 340 }, { cx: 820, cy: 520 },
  ];

  return (
    <svg
      viewBox="0 0 1080 1920"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        opacity: bright,
      }}
    >
      {paths.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke={C.cyan}
          strokeWidth={1.5}
          strokeLinecap="round"
        />
      ))}
      {nodes.map((n, i) => (
        <circle
          key={i}
          cx={n.cx}
          cy={n.cy}
          r={4}
          fill={C.cyan}
          opacity={0.7}
        />
      ))}
    </svg>
  );
};

// ─── Animated gradient background ────────────────────────────────────────────
const AnimatedBackground: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Slow gradient shift: cycles over ~8s
  const gradientShift = interpolate(frame, [0, 240], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Pulse for circuit glow, peaking at frame 60 then settling
  const pulse = spring({
    frame,
    fps,
    from: 0,
    to: 1,
    config: { damping: 40, stiffness: 8 },
  });

  // Interpolate gradient stop positions
  const midStop = interpolate(gradientShift, [0, 0.5, 1], [40, 55, 40]);

  return (
    <AbsoluteFill style={{ opacity: fadeIn }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `
            radial-gradient(
              ellipse 120% 60% at 20% ${midStop}%,
              ${C.emeraldDeep} 0%,
              transparent 60%
            ),
            radial-gradient(
              ellipse 80% 40% at 80% 70%,
              rgba(26,26,46,0.9) 0%,
              transparent 70%
            ),
            linear-gradient(
              175deg,
              ${C.navyDeep} 0%,
              ${C.charcoal} 50%,
              ${C.navyDeep} 100%
            )
          `,
        }}
      />
      <CircuitPattern pulse={pulse} />
    </AbsoluteFill>
  );
};

// ─── Data stream particles ────────────────────────────────────────────────────
const STREAM_COLUMNS = [80, 200, 360, 520, 640, 800, 960, 1020];

const DataStream: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {STREAM_COLUMNS.map((x, col) => {
        // Each column has a staggered speed and offset so they don't move in unison
        const speed = 1.8 + (col % 3) * 0.5;
        const offset = (col * 137) % 1920; // golden-angle spacing
        const y = ((frame * speed + offset) % 1920) - 20;

        const opacity = interpolate(
          (frame + col * 20) % 90,
          [0, 20, 70, 90],
          [0, 0.18, 0.18, 0],
          { extrapolateRight: "clamp" }
        );

        return (
          <div
            key={col}
            style={{
              position: "absolute",
              left: x,
              top: y,
              width: 2,
              height: 18,
              borderRadius: 2,
              background: C.cyan,
              opacity,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// ─── Corner bracket accents ───────────────────────────────────────────────────
const AnimatedCornerBrackets: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });
  return <CornerBrackets opacity={opacity} />;
};

const CornerBrackets: React.FC<{ opacity: number }> = ({ opacity }) => {
  const size = 60;
  const weight = 2;
  const glow = `0 0 12px ${C.cyan}, 0 0 24px rgba(0,212,170,0.3)`;

  const bracketStyle = (
    top: number | "auto",
    right: number | "auto",
    bottom: number | "auto",
    left: number | "auto",
    rotation: number
  ): React.CSSProperties => ({
    position: "absolute",
    top: top !== "auto" ? top : undefined,
    right: right !== "auto" ? right : undefined,
    bottom: bottom !== "auto" ? bottom : undefined,
    left: left !== "auto" ? left : undefined,
    width: size,
    height: size,
    borderTop: `${weight}px solid ${C.cyan}`,
    borderLeft: `${weight}px solid ${C.cyan}`,
    transform: `rotate(${rotation}deg)`,
    boxShadow: glow,
    opacity,
  });

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Top-left */}
      <div style={bracketStyle(48, "auto", "auto", 48, 0)} />
      {/* Top-right */}
      <div style={bracketStyle(48, 48, "auto", "auto", 90)} />
      {/* Bottom-right */}
      <div style={bracketStyle("auto", 48, 48, "auto", 180)} />
      {/* Bottom-left */}
      <div style={bracketStyle("auto", "auto", 48, 48, 270)} />
    </AbsoluteFill>
  );
};

// ─── "CEO LOG" label ──────────────────────────────────────────────────────────
const CeoLabel: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame,
    fps,
    config: { damping: 18, stiffness: 160 },
  });

  const translateY = interpolate(progress, [0, 1], [-40, 0]);
  const opacity = interpolate(progress, [0, 0.3], [0, 1]);

  return (
    <div
      style={{
        transform: `translateY(${translateY}px)`,
        opacity,
        textAlign: "center",
      }}
    >
      <span
        style={{
          fontFamily,
          fontSize: 24,
          fontWeight: 500,
          letterSpacing: 8,
          textTransform: "uppercase",
          color: C.cyan,
          textShadow: `0 0 20px rgba(0,212,170,0.6), 0 0 40px rgba(0,212,170,0.2)`,
        }}
      >
        CEO LOG
      </span>
      {/* Thin underline accent */}
      <div
        style={{
          height: 1,
          width: interpolate(progress, [0.4, 1], [0, 180]),
          background: `linear-gradient(90deg, transparent, ${C.cyan}, transparent)`,
          margin: "8px auto 0",
          opacity: interpolate(progress, [0.4, 1], [0, 1]),
        }}
      />
    </div>
  );
};

// ─── Day counter ──────────────────────────────────────────────────────────────
const DayCounter: React.FC<{ dayNumber: number }> = ({ dayNumber }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame,
    fps,
    config: { damping: 12, stiffness: 140 },
  });

  const scale = interpolate(progress, [0, 1], [0.4, 1]);
  const opacity = interpolate(progress, [0, 0.25], [0, 1]);

  // Count up from 0 to dayNumber
  const displayNumber = Math.round(interpolate(progress, [0, 0.8], [0, dayNumber], {
    extrapolateRight: "clamp",
  }));

  const glowIntensity = interpolate(progress, [0.8, 1], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        transform: `scale(${scale})`,
        opacity,
        textAlign: "center",
        position: "relative",
      }}
    >
      <div
        style={{
          fontFamily,
          fontSize: 20,
          fontWeight: 500,
          letterSpacing: 6,
          textTransform: "uppercase",
          color: `rgba(250,249,245,0.5)`,
          marginBottom: 4,
        }}
      >
        DAY
      </div>
      <div
        style={{
          fontFamily,
          fontSize: 140,
          fontWeight: 700,
          color: C.white,
          lineHeight: 0.85,
          textShadow: `
            0 0 ${interpolate(glowIntensity, [0, 1], [0, 40])}px rgba(0,212,170,0.4),
            0 0 ${interpolate(glowIntensity, [0, 1], [0, 80])}px rgba(0,212,170,0.15)
          `,
        }}
      >
        {displayNumber}
      </div>
    </div>
  );
};

// ─── Headline ─────────────────────────────────────────────────────────────────
const Headline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame,
    fps,
    config: { damping: 22, stiffness: 180 },
  });

  const translateX = interpolate(progress, [0, 1], [120, 0]);
  const opacity = interpolate(progress, [0, 0.2], [0, 1]);

  return (
    <div
      style={{
        transform: `translateX(${translateX}px)`,
        opacity,
        padding: "0 64px",
      }}
    >
      {/* Cyan left-border accent */}
      <div
        style={{
          borderLeft: `3px solid ${C.cyan}`,
          paddingLeft: 24,
          boxShadow: `-4px 0 20px rgba(0,212,170,0.25)`,
        }}
      >
        <div
          style={{
            fontFamily,
            fontSize: 48,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1.2,
          }}
        >
          {text}
        </div>
      </div>
    </div>
  );
};

// ─── Body text ────────────────────────────────────────────────────────────────
const BodyText: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 50], [0, 1], {
    extrapolateRight: "clamp",
  });

  const translateY = interpolate(frame, [0, 50], [20, 0], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        padding: "0 64px",
      }}
    >
      <div
        style={{
          fontFamily,
          fontSize: 28,
          fontWeight: 400,
          color: `rgba(250,249,245,0.82)`,
          lineHeight: 1.55,
        }}
      >
        {text}
      </div>
    </div>
  );
};

// ─── Metric bar ───────────────────────────────────────────────────────────────
const MetricBar: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const containerProgress = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  const fillProgress = spring({
    frame: Math.max(0, frame - 15),
    fps,
    config: { damping: 28, stiffness: 80 },
  });

  const fillWidth = interpolate(fillProgress, [0, 1], [0, 100]);

  const labelOpacity = interpolate(frame, [10, 35], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: containerProgress,
        padding: "0 64px",
      }}
    >
      {/* Metric label */}
      <div
        style={{
          opacity: labelOpacity,
          fontFamily,
          fontSize: 32,
          fontWeight: 700,
          color: C.white,
          marginBottom: 16,
          textShadow: `0 0 20px rgba(0,212,170,0.3)`,
        }}
      >
        {text}
      </div>

      {/* Progress bar track */}
      <div
        style={{
          height: 8,
          borderRadius: 4,
          background: "rgba(255,255,255,0.08)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        {/* Animated fill */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            width: `${fillWidth}%`,
            borderRadius: 4,
            background: `linear-gradient(90deg, ${C.cyan}, ${C.green})`,
            boxShadow: `0 0 12px rgba(0,212,170,0.6), 0 0 24px rgba(0,255,136,0.3)`,
          }}
        />
      </div>

      {/* Percentage label right-aligned */}
      <div
        style={{
          opacity: labelOpacity,
          fontFamily,
          fontSize: 18,
          fontWeight: 500,
          color: C.cyan,
          textAlign: "right",
          marginTop: 8,
          letterSpacing: 1,
        }}
      >
        {Math.round(fillWidth)}%
      </div>
    </div>
  );
};

// ─── Sign-off ─────────────────────────────────────────────────────────────────
const SignOff: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        textAlign: "center",
        padding: "0 80px",
      }}
    >
      <div
        style={{
          fontFamily: "Georgia, 'Times New Roman', serif",
          fontSize: 26,
          fontStyle: "italic",
          fontWeight: 400,
          color: `rgba(250,249,245,0.5)`,
          letterSpacing: 0.5,
        }}
      >
        Only good things from now on.
      </div>
    </div>
  );
};

// ─── Fade-out overlay ─────────────────────────────────────────────────────────
const FadeOut: React.FC = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: C.navyDeep,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

// ─── Root composition ─────────────────────────────────────────────────────────
export const CeoLog: React.FC<{
  dayNumber: number;
  headline: string;
  body: string;
  metric: string;
}> = ({ dayNumber, headline, body, metric }) => {
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Layer 0: Background (always visible) */}
      <AnimatedBackground />

      {/* Layer 1: Data stream particles */}
      <DataStream />

      {/* Layer 2: Corner brackets — fade in with background */}
      <Sequence from={5} durationInFrames={265} layout="none">
        <AnimatedCornerBrackets />
      </Sequence>

      {/* Content column */}
      <AbsoluteFill
        style={{
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "stretch",
          gap: 44,
          padding: "100px 0",
        }}
      >
        {/* Frames 10-40: CEO LOG label slides in from top */}
        <Sequence from={10} durationInFrames={260} layout="none">
          <CeoLabel />
        </Sequence>

        {/* Frames 25-55: Day counter scales up with count animation */}
        <Sequence from={25} durationInFrames={275} layout="none">
          <DayCounter dayNumber={dayNumber} />
        </Sequence>

        {/* Frames 50-80: Headline slides in from right */}
        <Sequence from={50} durationInFrames={250} layout="none">
          <Headline text={headline} />
        </Sequence>

        {/* Frames 75-150: Body fades in */}
        <Sequence from={75} durationInFrames={225} layout="none">
          <BodyText text={body} />
        </Sequence>

        {/* Frames 140-200: Metric bar fills */}
        <Sequence from={140} durationInFrames={160} layout="none">
          <MetricBar text={metric} />
        </Sequence>

        {/* Frames 210-270: Sign-off fades in */}
        <Sequence from={210} durationInFrames={90} layout="none">
          <SignOff />
        </Sequence>
      </AbsoluteFill>

      {/* Fade out: frames 270-300 */}
      <Sequence from={270} durationInFrames={30} layout="none">
        <FadeOut />
      </Sequence>
    </AbsoluteFill>
  );
};
