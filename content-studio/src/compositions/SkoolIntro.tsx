import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont, fontFamily as spaceGroteskFamily } from "@remotion/google-fonts/SpaceGrotesk";

// Load Space Grotesk at module scope — required by Remotion font system
loadFont("normal", { weights: ["300", "400", "500", "700"], subsets: ["latin"] });

const FONT = spaceGroteskFamily;

const C = {
  cyan: "#00D4AA",
  magenta: "#FF006E",
  white: "#FFFFFF",
  bgPurple: "#1a0533",
  bgTeal: "#0a2e3d",
  bgMidnight: "#0d1b3e",
  electric: "#00BFFF",
  gold: "#FFD700",
};

// ---------------------------------------------------------------------------
// Scene 1 helpers
// ---------------------------------------------------------------------------

const AnimatedBackground: React.FC = () => {
  const frame = useCurrentFrame();

  // Rotate gradient angle over full video duration
  const angle = interpolate(frame, [0, 600], [135, 270], {
    extrapolateRight: "clamp",
  });

  const opacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity,
        background: `linear-gradient(${angle}deg, ${C.bgPurple} 0%, ${C.bgMidnight} 50%, ${C.bgTeal} 100%)`,
      }}
    />
  );
};

// Five orbs: cyan top-right, magenta bottom-left, electric center, cyan lower-right, magenta top-left
const GlowOrbs: React.FC = () => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  const p1 = Math.sin((frame / 30) * Math.PI * 0.7);
  const p2 = Math.sin((frame / 30) * Math.PI * 0.55 + 1.4);
  const p3 = Math.sin((frame / 30) * Math.PI * 0.45 + 2.8);
  const p4 = Math.sin((frame / 30) * Math.PI * 0.62 + 0.6);
  const p5 = Math.sin((frame / 30) * Math.PI * 0.38 + 3.5);

  const scale1 = interpolate(p1, [-1, 1], [0.88, 1.12]);
  const scale2 = interpolate(p2, [-1, 1], [0.85, 1.15]);
  const scale3 = interpolate(p3, [-1, 1], [0.9, 1.1]);
  const scale4 = interpolate(p4, [-1, 1], [0.87, 1.13]);
  const scale5 = interpolate(p5, [-1, 1], [0.92, 1.08]);

  return (
    <div style={{ position: "absolute", inset: 0, opacity: fadeIn }}>
      {/* Top-right cyan */}
      <div
        style={{
          position: "absolute",
          top: 100,
          right: -150,
          width: 500,
          height: 500,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${C.cyan}55 0%, transparent 70%)`,
          filter: "blur(70px)",
          transform: `scale(${scale1})`,
        }}
      />
      {/* Bottom-left magenta */}
      <div
        style={{
          position: "absolute",
          bottom: 200,
          left: -160,
          width: 520,
          height: 520,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${C.magenta}44 0%, transparent 70%)`,
          filter: "blur(80px)",
          transform: `scale(${scale2})`,
        }}
      />
      {/* Center electric blue */}
      <div
        style={{
          position: "absolute",
          top: "42%",
          left: "50%",
          width: 600,
          height: 600,
          marginLeft: -300,
          marginTop: -300,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${C.electric}28 0%, transparent 65%)`,
          filter: "blur(90px)",
          transform: `scale(${scale3})`,
        }}
      />
      {/* Lower-right cyan accent */}
      <div
        style={{
          position: "absolute",
          bottom: -80,
          right: -80,
          width: 420,
          height: 420,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${C.cyan}33 0%, transparent 70%)`,
          filter: "blur(60px)",
          transform: `scale(${scale4})`,
        }}
      />
      {/* Top-left magenta accent */}
      <div
        style={{
          position: "absolute",
          top: 600,
          left: -80,
          width: 360,
          height: 360,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${C.magenta}30 0%, transparent 70%)`,
          filter: "blur(55px)",
          transform: `scale(${scale5})`,
        }}
      />
    </div>
  );
};

// 10 geometric particles drifting upward with horizontal wobble
const FloatingParticles: React.FC = () => {
  const frame = useCurrentFrame();

  const particles: {
    x: number;
    startY: number;
    size: number;
    speed: number;
    color: string;
    shape: "circle" | "diamond" | "hex";
    phaseOffset: number;
    wobbleAmp: number;
    opacity: number;
  }[] = [
    { x: 80, startY: 1900, size: 10, speed: 2.4, color: C.cyan, shape: "circle", phaseOffset: 0, wobbleAmp: 24, opacity: 0.5 },
    { x: 200, startY: 1950, size: 14, speed: 1.8, color: C.magenta, shape: "diamond", phaseOffset: 1.2, wobbleAmp: 18, opacity: 0.45 },
    { x: 370, startY: 2000, size: 8, speed: 2.1, color: C.electric, shape: "circle", phaseOffset: 2.4, wobbleAmp: 30, opacity: 0.5 },
    { x: 520, startY: 1880, size: 12, speed: 1.6, color: C.cyan, shape: "hex", phaseOffset: 0.6, wobbleAmp: 16, opacity: 0.4 },
    { x: 660, startY: 1970, size: 16, speed: 2.7, color: C.gold, shape: "diamond", phaseOffset: 3.0, wobbleAmp: 22, opacity: 0.38 },
    { x: 780, startY: 1920, size: 9, speed: 1.9, color: C.magenta, shape: "circle", phaseOffset: 1.8, wobbleAmp: 28, opacity: 0.48 },
    { x: 900, startY: 2020, size: 11, speed: 2.2, color: C.electric, shape: "hex", phaseOffset: 4.2, wobbleAmp: 20, opacity: 0.42 },
    { x: 140, startY: 1860, size: 7, speed: 3.0, color: C.gold, shape: "circle", phaseOffset: 2.0, wobbleAmp: 14, opacity: 0.35 },
    { x: 440, startY: 1990, size: 13, speed: 1.5, color: C.cyan, shape: "diamond", phaseOffset: 0.3, wobbleAmp: 26, opacity: 0.44 },
    { x: 830, startY: 1840, size: 6, speed: 2.6, color: C.magenta, shape: "circle", phaseOffset: 3.7, wobbleAmp: 12, opacity: 0.4 },
  ];

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {particles.map((p, i) => {
        const totalTravel = 1920 + 200;
        const yOffset = ((frame * p.speed) % totalTravel);
        const xWobble = Math.sin(frame * 0.04 + p.phaseOffset) * p.wobbleAmp;
        const currentY = p.startY - yOffset;
        const alphaWobble = p.opacity + Math.sin(frame * 0.07 + p.phaseOffset) * 0.15;

        const borderRadius =
          p.shape === "circle" ? "50%" : p.shape === "hex" ? "18%" : "2px";
        const rotate = p.shape === "diamond" ? 45 : p.shape === "hex" ? (frame * 0.3 + i * 30) % 360 : 0;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p.x + xWobble,
              top: currentY,
              width: p.size,
              height: p.size,
              borderRadius,
              background: p.color,
              opacity: Math.max(0, Math.min(1, alphaWobble)),
              transform: `rotate(${rotate}deg)`,
              boxShadow: `0 0 ${p.size * 1.5}px ${p.color}88`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

// Holographic hexagon wireframe with slow rotation and opacity pulse
const HolographicHexagon: React.FC<{ startFrame: number; endFrame: number }> = ({
  startFrame,
  endFrame,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entryProgress = spring({
    frame: frame - startFrame,
    fps,
    config: { damping: 20, stiffness: 60, mass: 1.2 },
  });

  const fadeOut = interpolate(frame, [endFrame - 20, endFrame], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const opacity = interpolate(entryProgress, [0, 1], [0, 1]) * fadeOut;
  const scale = interpolate(entryProgress, [0, 1], [0.5, 1]);
  const rotation = frame * 0.3;

  // Pulsing glow intensity on the hex strokes
  const glowStrength = interpolate(
    Math.sin((frame / 30) * Math.PI * 0.8),
    [-1, 1],
    [2, 5]
  );

  // Hexagon points for a 200px radius hexagon
  const r = 200;
  const cx = 540;
  const cy = 540;
  const points = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
  }).join(" ");

  // Inner hexagon at 60% scale
  const r2 = 120;
  const points2 = Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 2 + Math.PI / 6;
    return `${cx + r2 * Math.cos(angle)},${cy + r2 * Math.sin(angle)}`;
  }).join(" ");

  return (
    <div
      style={{
        position: "absolute",
        top: 240,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        opacity,
        transform: `scale(${scale}) rotate(${rotation}deg)`,
      }}
    >
      <svg width="1080" height="1080" viewBox="0 0 1080 1080">
        <defs>
          <filter id="hexGlow">
            <feGaussianBlur stdDeviation={glowStrength} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* Outer hexagon */}
        <polygon
          points={points}
          fill="none"
          stroke={C.cyan}
          strokeWidth="1.5"
          strokeOpacity="0.7"
          filter="url(#hexGlow)"
        />
        {/* Inner hexagon, counter-rotating visual */}
        <polygon
          points={points2}
          fill="none"
          stroke={C.electric}
          strokeWidth="1"
          strokeOpacity="0.5"
          filter="url(#hexGlow)"
        />
        {/* Spoke lines from center to outer vertices */}
        {Array.from({ length: 6 }, (_, i) => {
          const angle = (Math.PI / 3) * i - Math.PI / 2;
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + r * Math.cos(angle)}
              y2={cy + r * Math.sin(angle)}
              stroke={C.cyan}
              strokeWidth="0.6"
              strokeOpacity="0.3"
            />
          );
        })}
        {/* Center crosshair dot */}
        <circle cx={cx} cy={cy} r={4} fill={C.cyan} opacity={0.6} filter="url(#hexGlow)" />
      </svg>
    </div>
  );
};

// ---------------------------------------------------------------------------
// DataStream — vertical columns of falling data characters (subtle Matrix-style)
// ---------------------------------------------------------------------------
const DataStream: React.FC = () => {
  const frame = useCurrentFrame();

  const columns = [
    { x: 40, speed: 1.4, chars: 18, phaseOffset: 0 },
    { x: 160, speed: 1.1, chars: 14, phaseOffset: 3.2 },
    { x: 300, speed: 1.7, chars: 20, phaseOffset: 1.1 },
    { x: 490, speed: 1.3, chars: 16, phaseOffset: 2.5 },
    { x: 640, speed: 1.5, chars: 12, phaseOffset: 0.7 },
    { x: 780, speed: 1.2, chars: 17, phaseOffset: 4.1 },
    { x: 960, speed: 1.6, chars: 15, phaseOffset: 1.8 },
    { x: 1040, speed: 1.0, chars: 13, phaseOffset: 3.8 },
  ];

  const CHARS = "01アイウエオABCDEF<>{}[]";
  const globalOpacity = interpolate(frame, [0, 40], [0, 0.22], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: globalOpacity }}>
      {columns.map((col, ci) => {
        return Array.from({ length: col.chars }, (_, ri) => {
          const totalHeight = 1920 + col.chars * 36;
          const yBase = ((frame * col.speed * 1.5 + ri * 36 + col.phaseOffset * 120) % totalHeight) - 60;
          const charIndex = Math.floor((frame * 0.3 + ri * 7 + ci * 13) % CHARS.length);
          const headOpacity = ri === 0 ? 1 : interpolate(ri, [0, col.chars], [0.9, 0.05]);
          const color = ri === 0 ? C.white : ri < 3 ? C.cyan : C.electric;

          return (
            <div
              key={`${ci}-${ri}`}
              style={{
                position: "absolute",
                left: col.x,
                top: yBase,
                fontFamily: "monospace",
                fontSize: 14,
                color,
                opacity: headOpacity,
                lineHeight: 1,
                textShadow: ri < 2 ? `0 0 8px ${C.cyan}` : "none",
                userSelect: "none",
              }}
            >
              {CHARS[charIndex]}
            </div>
          );
        });
      })}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// EnergyWave — expanding concentric rings that pulse outward from center
// ---------------------------------------------------------------------------
const EnergyWave: React.FC<{ triggerFrame: number }> = ({ triggerFrame }) => {
  const frame = useCurrentFrame();
  const WAVE_INTERVAL = 60;
  const NUM_WAVES = 4;

  return (
    <div
      style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        width: 0,
        height: 0,
        pointerEvents: "none",
      }}
    >
      {Array.from({ length: NUM_WAVES }, (_, i) => {
        const waveFrame = frame - triggerFrame - i * WAVE_INTERVAL;
        if (waveFrame < 0) return null;

        const radius = interpolate(waveFrame, [0, 120], [0, 900], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const waveOpacity = interpolate(waveFrame, [0, 20, 120], [0, 0.4, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const color = i % 2 === 0 ? C.cyan : C.magenta;
        const thickness = interpolate(waveFrame, [0, 120], [3, 0.5], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: -radius,
              left: -radius,
              width: radius * 2,
              height: radius * 2,
              borderRadius: "50%",
              border: `${thickness}px solid ${color}`,
              opacity: waveOpacity,
              boxShadow: `0 0 16px ${color}44, inset 0 0 16px ${color}22`,
            }}
          />
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// HolographicGrid — perspective grid floor with vanishing point
// ---------------------------------------------------------------------------
const HolographicGrid: React.FC<{ startFrame: number; endFrame: number }> = ({
  startFrame,
  endFrame,
}) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [startFrame, startFrame + 30, endFrame - 20, endFrame],
    [0, 0.35, 0.35, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Scroll the grid lines to create movement illusion
  const scroll = (frame * 2) % 100;

  const HORIZON_Y = 700;
  const VP_X = 540;
  const GRID_COLOR = C.electric;
  const NUM_V_LINES = 11;
  const NUM_H_LINES = 8;

  const vLines = Array.from({ length: NUM_V_LINES }, (_, i) => {
    const t = i / (NUM_V_LINES - 1);
    const bottomX = t * 1080;
    return { x1: VP_X, y1: HORIZON_Y, x2: bottomX, y2: 1920 };
  });

  const hLines = Array.from({ length: NUM_H_LINES }, (_, i) => {
    const t = ((i / NUM_H_LINES) + scroll / 100) % 1;
    const perspT = Math.pow(t, 2);
    const y = HORIZON_Y + perspT * (1920 - HORIZON_Y);
    const spreadX = perspT * VP_X;
    return { x1: VP_X - spreadX, y1: y, x2: VP_X + spreadX, y2: y, alpha: t };
  });

  return (
    <div style={{ position: "absolute", inset: 0, opacity }}>
      <svg width="1080" height="1920" viewBox="0 0 1080 1920" style={{ display: "block" }}>
        <defs>
          <linearGradient id="gridFade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={GRID_COLOR} stopOpacity="0" />
            <stop offset="60%" stopColor={GRID_COLOR} stopOpacity="0.5" />
            <stop offset="100%" stopColor={GRID_COLOR} stopOpacity="0.8" />
          </linearGradient>
        </defs>
        {vLines.map((l, i) => (
          <line
            key={`v${i}`}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke="url(#gridFade)"
            strokeWidth="0.6"
            strokeOpacity="0.6"
          />
        ))}
        {hLines.map((l, i) => (
          <line
            key={`h${i}`}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke={GRID_COLOR}
            strokeWidth="0.5"
            strokeOpacity={l.alpha * 0.7}
          />
        ))}
      </svg>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Scene 1: Opening — Agency Accelerants hero text
// ---------------------------------------------------------------------------
const Scene1: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Main title springs up from frame 20
  const titleSpring = spring({
    frame: frame - 20,
    fps,
    config: { damping: 14, stiffness: 90, mass: 0.8 },
  });
  const titleY = interpolate(titleSpring, [0, 1], [80, 0]);
  const titleOpacity = interpolate(frame, [20, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Title glow pulse
  const titleGlow = interpolate(
    Math.sin((frame / 30) * Math.PI * 1.1),
    [-1, 1],
    [12, 30]
  );

  // Subtitle fades in from frame 48
  const subtitleSpring = spring({
    frame: frame - 48,
    fps,
    config: { damping: 18, stiffness: 80 },
  });
  const subtitleY = interpolate(subtitleSpring, [0, 1], [40, 0]);
  const subtitleOpacity = interpolate(frame, [48, 70], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Separator line expands from center
  const lineScale = interpolate(frame, [30, 60], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Scene 1 exit: fade out from frame 96
  const sceneOpacity = interpolate(frame, [96, 120], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 0,
        paddingBottom: 120,
      }}
    >
      {/* "AGENCY ACCELERANTS" */}
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
          padding: "0 48px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 72,
            fontWeight: 700,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: C.white,
            lineHeight: 1.1,
            textShadow: `0 0 ${titleGlow}px ${C.cyan}cc, 0 0 ${titleGlow * 2}px ${C.cyan}55, 0 4px 32px rgba(0,0,0,0.6)`,
          }}
        >
          AGENCY
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 72,
            fontWeight: 700,
            letterSpacing: 6,
            textTransform: "uppercase",
            background: `linear-gradient(90deg, ${C.cyan}, ${C.electric}, ${C.magenta})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            lineHeight: 1.1,
            textShadow: "none",
          }}
        >
          ACCELERANTS
        </div>
      </div>

      {/* Separator */}
      <div
        style={{
          marginTop: 20,
          width: `${lineScale * 560}px`,
          height: 1,
          background: `linear-gradient(90deg, transparent, ${C.cyan}cc, ${C.electric}cc, transparent)`,
          boxShadow: `0 0 12px ${C.cyan}88`,
        }}
      />

      {/* "by OASIS AI Solutions" */}
      <div
        style={{
          marginTop: 20,
          opacity: subtitleOpacity,
          transform: `translateY(${subtitleY}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 32,
            fontWeight: 400,
            letterSpacing: 4,
            color: C.cyan,
            textTransform: "uppercase",
            textAlign: "center",
            textShadow: `0 0 14px ${C.cyan}99`,
          }}
        >
          by Bennet Spooner
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scan line sweeping down the screen
// ---------------------------------------------------------------------------
const ScanLine: React.FC<{ startFrame: number; endFrame: number }> = ({
  startFrame,
  endFrame,
}) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [startFrame, startFrame + 10, endFrame - 10, endFrame], [0, 0.45, 0.45, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const top = progress * 1920;

  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 0,
        right: 0,
        height: 2,
        background: `linear-gradient(90deg, transparent, ${C.electric}cc, ${C.cyan}cc, transparent)`,
        opacity,
        boxShadow: `0 0 8px ${C.electric}88`,
        pointerEvents: "none",
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Scene 2: The Problem
// ---------------------------------------------------------------------------
const PROBLEM_BULLETS = [
  "Cold outreach by hand",
  "No systems, no leverage",
  "Trading time for money",
];

const Scene2: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene 2 active: frames 120-228
  const sceneIn = interpolate(frame, [120, 144], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [204, 228], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // Headline typewriter: frames 132-178
  const headline = "Still doing everything manually?";
  const charsShown = Math.floor(
    interpolate(frame, [132, 178], [0, headline.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const visibleHeadline = headline.slice(0, charsShown);
  const cursorVisible =
    charsShown < headline.length || Math.sin((frame / 30) * Math.PI * 4) > 0;

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "0 72px",
        gap: 48,
      }}
    >
      {/* Headline */}
      <div>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 58,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1.2,
            textShadow: "0 4px 24px rgba(0,0,0,0.6)",
          }}
        >
          {visibleHeadline}
          {cursorVisible && (
            <span
              style={{
                display: "inline-block",
                width: 3,
                height: "0.8em",
                background: C.magenta,
                marginLeft: 5,
                verticalAlign: "middle",
                boxShadow: `0 0 10px ${C.magenta}`,
              }}
            />
          )}
        </div>
      </div>

      {/* Staggered bullets from left */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 32,
          width: "100%",
        }}
      >
        {PROBLEM_BULLETS.map((bullet, i) => {
          const bulletStart = 152 + i * 24;
          const bulletProgress = spring({
            frame: frame - bulletStart,
            fps,
            config: { damping: 18, stiffness: 160, mass: 0.7 },
          });
          const bulletX = interpolate(bulletProgress, [0, 1], [-120, 0]);
          const bulletOpacity = interpolate(
            frame,
            [bulletStart, bulletStart + 14],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );

          return (
            <div
              key={i}
              style={{
                opacity: bulletOpacity,
                transform: `translateX(${bulletX}px)`,
                display: "flex",
                alignItems: "center",
                gap: 20,
                position: "relative",
              }}
            >
              {/* Red glow behind each bullet */}
              <div
                style={{
                  position: "absolute",
                  left: -16,
                  top: "50%",
                  width: 500,
                  height: 60,
                  marginTop: -30,
                  background: `linear-gradient(90deg, ${C.magenta}22, transparent)`,
                  borderRadius: 8,
                }}
              />
              <div
                style={{
                  fontFamily: FONT,
                  fontSize: 26,
                  fontWeight: 400,
                  color: C.magenta,
                  flexShrink: 0,
                  zIndex: 1,
                }}
              >
                ✕
              </div>
              <div
                style={{
                  fontFamily: FONT,
                  fontSize: 36,
                  fontWeight: 500,
                  color: C.white,
                  zIndex: 1,
                  lineHeight: 1.25,
                }}
              >
                {bullet}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Flash/pulse effect at scene transition
// ---------------------------------------------------------------------------
const TransitionFlash: React.FC<{ peakFrame: number }> = ({ peakFrame }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [peakFrame - 8, peakFrame, peakFrame + 12],
    [0, 0.35, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: C.white,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Circuit board SVG pattern fading in for Scene 3
// ---------------------------------------------------------------------------
const CircuitPattern: React.FC<{ fadeInStart: number; opacity: number }> = ({
  fadeInStart,
  opacity: maxOpacity,
}) => {
  const frame = useCurrentFrame();

  const op = interpolate(frame, [fadeInStart, fadeInStart + 30], [0, maxOpacity], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Build a circuit-board-style SVG with lines and nodes
  const lines = [
    { x1: 0, y1: 300, x2: 200, y2: 300 },
    { x1: 200, y1: 300, x2: 200, y2: 100 },
    { x1: 200, y1: 100, x2: 500, y2: 100 },
    { x1: 500, y1: 100, x2: 500, y2: 400 },
    { x1: 500, y1: 400, x2: 900, y2: 400 },
    { x1: 900, y1: 400, x2: 900, y2: 200 },
    { x1: 900, y1: 200, x2: 1080, y2: 200 },
    { x1: 0, y1: 600, x2: 350, y2: 600 },
    { x1: 350, y1: 600, x2: 350, y2: 750 },
    { x1: 350, y1: 750, x2: 700, y2: 750 },
    { x1: 700, y1: 750, x2: 700, y2: 500 },
    { x1: 700, y1: 500, x2: 1080, y2: 500 },
    { x1: 100, y1: 0, x2: 100, y2: 200 },
    { x1: 800, y1: 0, x2: 800, y2: 180 },
    { x1: 800, y1: 180, x2: 1080, y2: 180 },
    { x1: 0, y1: 900, x2: 450, y2: 900 },
    { x1: 450, y1: 900, x2: 450, y2: 1080 },
    { x1: 600, y1: 1080, x2: 600, y2: 850 },
    { x1: 600, y1: 850, x2: 1080, y2: 850 },
  ];

  const nodes = [
    { x: 200, y: 300 }, { x: 500, y: 100 }, { x: 500, y: 400 }, { x: 900, y: 400 },
    { x: 350, y: 600 }, { x: 350, y: 750 }, { x: 700, y: 750 }, { x: 700, y: 500 },
    { x: 100, y: 200 }, { x: 800, y: 180 }, { x: 450, y: 900 }, { x: 600, y: 850 },
  ];

  return (
    <div style={{ position: "absolute", inset: 0, opacity: op }}>
      <svg width="1080" height="1920" viewBox="0 0 1080 1080" style={{ display: "block" }}>
        {lines.map((l, i) => (
          <line
            key={i}
            x1={l.x1}
            y1={l.y1}
            x2={l.x2}
            y2={l.y2}
            stroke={C.cyan}
            strokeWidth="0.7"
            strokeOpacity="0.5"
          />
        ))}
        {nodes.map((n, i) => (
          <circle
            key={i}
            cx={n.x}
            cy={n.y}
            r={3}
            fill={C.cyan}
            opacity={0.6}
          />
        ))}
      </svg>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Scene 3: The Transformation
// ---------------------------------------------------------------------------
const FEATURE_CARDS = [
  { icon: "🤖", text: "AI Agents That Close Deals" },
  { icon: "⚡", text: "Automated Client Pipelines" },
  { icon: "📈", text: "Systems That Scale While You Sleep" },
];

const Scene3: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene 3: frames 228-370
  const sceneIn = interpolate(frame, [228, 254], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [348, 370], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // "What if AI did 90% of it?" spring scale-in from frame 232
  const questionSpring = spring({
    frame: frame - 232,
    fps,
    config: { damping: 14, stiffness: 100, mass: 0.9 },
  });
  const questionScale = interpolate(questionSpring, [0, 1], [0.7, 1]);
  const questionOpacity = interpolate(frame, [232, 258], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "0 60px",
        gap: 52,
      }}
    >
      {/* "What if AI did 90% of it?" */}
      <div
        style={{
          opacity: questionOpacity,
          transform: `scale(${questionScale})`,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 60,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1.2,
            textShadow: `0 0 24px ${C.electric}55, 0 4px 32px rgba(0,0,0,0.7)`,
          }}
        >
          What if AI did{" "}
          <span
            style={{
              background: `linear-gradient(90deg, ${C.cyan}, ${C.electric})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}
          >
            90%
          </span>{" "}
          of it?
        </div>
      </div>

      {/* Feature cards staggered from bottom */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 24,
          width: "100%",
        }}
      >
        {FEATURE_CARDS.map((card, i) => {
          const cardStart = 254 + i * 30;
          const cardSpring = spring({
            frame: frame - cardStart,
            fps,
            config: { damping: 16, stiffness: 140, mass: 0.8 },
          });
          const cardY = interpolate(cardSpring, [0, 1], [80, 0]);
          const cardOpacity = interpolate(
            frame,
            [cardStart, cardStart + 16],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );

          // Card glow pulse per card, offset phase
          const cardGlow = interpolate(
            Math.sin((frame / 30) * Math.PI * 0.9 + i * 1.5),
            [-1, 1],
            [6, 18]
          );

          // Subtle tilt oscillation
          const tilt = Math.sin((frame / 30) * Math.PI * 0.5 + i * 0.8) * 0.5;

          return (
            <div
              key={i}
              style={{
                opacity: cardOpacity,
                transform: `translateY(${cardY}px) rotate(${tilt}deg)`,
              }}
            >
              {/* Card outer glow border */}
              <div
                style={{
                  borderRadius: 18,
                  padding: 1.5,
                  background: `linear-gradient(135deg, ${C.cyan}66, ${C.electric}44, ${C.magenta}22)`,
                  boxShadow: `0 0 ${cardGlow}px ${C.cyan}44, 0 4px 20px rgba(0,0,0,0.4)`,
                }}
              >
                <div
                  style={{
                    background: "rgba(13, 27, 62, 0.88)",
                    borderRadius: 17,
                    padding: "26px 32px",
                    display: "flex",
                    alignItems: "center",
                    gap: 22,
                    backdropFilter: "blur(12px)",
                  }}
                >
                  <div style={{ fontSize: 36, flexShrink: 0 }}>{card.icon}</div>
                  <div
                    style={{
                      fontFamily: FONT,
                      fontSize: 30,
                      fontWeight: 600,
                      color: C.white,
                      lineHeight: 1.3,
                    }}
                  >
                    {card.text}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene 4: Social Proof — animated counter + authority signals
// ---------------------------------------------------------------------------
const PulsingRings: React.FC<{ peakFrame: number }> = ({ peakFrame }) => {
  const frame = useCurrentFrame();

  const rings = [0, 18, 36];

  return (
    <div
      style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        width: 0,
        height: 0,
        pointerEvents: "none",
      }}
    >
      {rings.map((delay, i) => {
        const ringFrame = frame - (peakFrame + delay);
        const radius = interpolate(ringFrame, [0, 90], [0, 600], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const ringOpacity = interpolate(ringFrame, [0, 30, 90], [0, 0.5, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const color = i === 0 ? C.cyan : i === 1 ? C.electric : C.magenta;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: -radius,
              left: -radius,
              width: radius * 2,
              height: radius * 2,
              borderRadius: "50%",
              border: `1.5px solid ${color}`,
              opacity: ringOpacity,
              boxShadow: `0 0 12px ${color}55`,
            }}
          />
        );
      })}
    </div>
  );
};

const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene 4: frames 370-490
  const sceneIn = interpolate(frame, [370, 396], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [468, 490], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // Animated counter: $0 → $5,000 over frames 385-450
  const counterValue = Math.floor(
    interpolate(frame, [385, 450], [0, 5000], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const counterGlow = interpolate(
    Math.sin((frame / 30) * Math.PI * 1.2),
    [-1, 1],
    [10, 28]
  );

  // "Monthly Recurring Revenue Target" fades in from frame 400
  const labelOpacity = interpolate(frame, [400, 422], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Tagline spring from frame 420
  const taglineSpring = spring({
    frame: frame - 420,
    fps,
    config: { damping: 20, stiffness: 80 },
  });
  const taglineY = interpolate(taglineSpring, [0, 1], [30, 0]);
  const taglineOpacity = interpolate(frame, [420, 440], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Badges spring in staggered from frame 440
  const BADGES = [
    "Scale to 6 Figures with AI",
    "Done-For-You Automations",
    "Elite Community Access",
  ];

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 36,
      }}
    >
      {/* Pulsing rings centered on MRR number */}
      <PulsingRings peakFrame={385} />

      {/* Animated counter */}
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 108,
            fontWeight: 700,
            color: C.gold,
            lineHeight: 1,
            textShadow: `0 0 ${counterGlow}px ${C.gold}cc, 0 0 ${counterGlow * 2}px ${C.gold}55`,
            letterSpacing: -2,
          }}
        >
          ${counterValue.toLocaleString()}+
        </div>
      </div>

      {/* Label */}
      <div
        style={{
          opacity: labelOpacity,
          textAlign: "center",
          padding: "0 80px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 28,
            fontWeight: 400,
            color: C.white,
            letterSpacing: 2,
            textTransform: "uppercase",
            opacity: 0.8,
          }}
        >
          Monthly Recurring Revenue Target
        </div>
      </div>

      {/* Tagline */}
      <div
        style={{
          opacity: taglineOpacity,
          transform: `translateY(${taglineY}px)`,
          textAlign: "center",
          padding: "0 60px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 34,
            fontWeight: 600,
            color: C.cyan,
            lineHeight: 1.3,
            textShadow: `0 0 14px ${C.cyan}88`,
          }}
        >
          Built by entrepreneurs, for entrepreneurs
        </div>
      </div>

      {/* Achievement badges */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
          padding: "0 60px",
          width: "100%",
        }}
      >
        {BADGES.map((badge, i) => {
          const badgeStart = 440 + i * 14;
          const badgeSpring = spring({
            frame: frame - badgeStart,
            fps,
            config: { damping: 20, stiffness: 180, mass: 0.6 },
          });
          const badgeX = interpolate(badgeSpring, [0, 1], [100, 0]);
          const badgeOpacity = interpolate(
            frame,
            [badgeStart, badgeStart + 12],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );

          return (
            <div
              key={i}
              style={{
                opacity: badgeOpacity,
                transform: `translateX(${badgeX}px)`,
                display: "flex",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  background: "rgba(0,212,170,0.12)",
                  border: `1px solid ${C.cyan}66`,
                  borderRadius: 50,
                  padding: "10px 30px",
                  boxShadow: `0 0 12px ${C.cyan}22`,
                }}
              >
                <div
                  style={{
                    fontFamily: FONT,
                    fontSize: 22,
                    fontWeight: 500,
                    color: C.cyan,
                    letterSpacing: 1,
                  }}
                >
                  ✦ {badge}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Vignette — darkens edges for cinematic depth
// ---------------------------------------------------------------------------
const Vignette: React.FC<{ startFrame: number }> = ({ startFrame }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [startFrame, startFrame + 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity,
        background:
          "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.65) 100%)",
        pointerEvents: "none",
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Scene 5: CTA Close
// ---------------------------------------------------------------------------
const Scene5: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scene 5: frames 490-600
  const sceneOpacity = interpolate(frame, [490, 514], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // "JOIN THE ACCELERANTS" bouncy spring from frame 498
  const ctaSpring = spring({
    frame: frame - 498,
    fps,
    config: { damping: 10, stiffness: 220, mass: 0.7 },
  });
  const ctaScale = interpolate(ctaSpring, [0, 1], [0, 1]);
  const ctaOpacity = interpolate(frame, [498, 518], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Gradient border animation on CTA button
  const borderAngle = interpolate(frame, [498, 600], [0, 360], {
    extrapolateRight: "clamp",
  });

  // CTA glow pulse
  const ctaGlow = interpolate(
    Math.sin((frame / 30) * Math.PI * 1.3),
    [-1, 1],
    [12, 35]
  );

  // "Your AI Empire Starts Here" typewriter from frame 516
  const tagline = "Your AI Empire Starts Here";
  const taglineChars = Math.floor(
    interpolate(frame, [518, 560], [0, tagline.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const visibleTagline = tagline.slice(0, taglineChars);

  // Brand watermark fades in from frame 540
  const brandOpacity = interpolate(frame, [540, 562], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Final pulse: frames 570-600, scale 1→1.02→1
  const finalPulse = interpolate(
    Math.sin(interpolate(frame, [570, 600], [0, Math.PI], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })),
    [0, 1],
    [1, 1.018]
  );

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 40,
        padding: "0 48px",
        transform: `scale(${finalPulse})`,
      }}
    >
      {/* "JOIN THE ACCELERANTS" CTA */}
      <div
        style={{
          opacity: ctaOpacity,
          transform: `scale(${ctaScale})`,
          width: "100%",
          display: "flex",
          justifyContent: "center",
        }}
      >
        {/* Outer animated gradient ring */}
        <div
          style={{
            borderRadius: 24,
            padding: 2,
            background: `linear-gradient(${borderAngle}deg, ${C.cyan}, ${C.electric}, ${C.magenta}, ${C.cyan})`,
            boxShadow: `0 0 ${ctaGlow}px ${C.cyan}66, 0 0 ${ctaGlow * 1.5}px ${C.magenta}44`,
            width: "100%",
          }}
        >
          <div
            style={{
              background: "rgba(10, 10, 35, 0.95)",
              borderRadius: 22,
              padding: "30px 40px",
              textAlign: "center",
              backdropFilter: "blur(16px)",
            }}
          >
            <div
              style={{
                fontFamily: FONT,
                fontSize: 52,
                fontWeight: 700,
                letterSpacing: 2,
                textTransform: "uppercase",
                background: `linear-gradient(90deg, ${C.cyan}, ${C.electric}, ${C.white})`,
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                lineHeight: 1.1,
              }}
            >
              JOIN THE
            </div>
            <div
              style={{
                fontFamily: FONT,
                fontSize: 52,
                fontWeight: 700,
                letterSpacing: 2,
                textTransform: "uppercase",
                background: `linear-gradient(90deg, ${C.magenta}, ${C.electric}, ${C.cyan})`,
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundClip: "text",
                lineHeight: 1.1,
              }}
            >
              ACCELERANTS
            </div>
          </div>
        </div>
      </div>

      {/* Typewriter tagline */}
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 36,
            fontWeight: 400,
            color: C.white,
            opacity: 0.85,
            letterSpacing: 1,
            lineHeight: 1.4,
            minHeight: "1.4em",
          }}
        >
          {visibleTagline}
          {taglineChars < tagline.length && (
            <span
              style={{
                display: "inline-block",
                width: 2,
                height: "0.8em",
                background: C.electric,
                marginLeft: 4,
                verticalAlign: "middle",
                boxShadow: `0 0 8px ${C.electric}`,
              }}
            />
          )}
        </div>
      </div>

      {/* Brand watermark */}
      <div
        style={{
          opacity: brandOpacity,
          textAlign: "center",
          position: "absolute",
          bottom: 100,
          left: 0,
          right: 0,
        }}
      >
        {/* Separator line */}
        <div
          style={{
            marginBottom: 18,
            height: 1,
            background: `linear-gradient(90deg, transparent, ${C.cyan}77, transparent)`,
            width: "60%",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        />
        <div
          style={{
            fontFamily: FONT,
            fontSize: 22,
            fontWeight: 400,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: C.cyan,
            textShadow: `0 0 12px ${C.cyan}88`,
            opacity: 0.9,
          }}
        >
          BENNET SPOONER
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Root composition — no props, named export
// ---------------------------------------------------------------------------
export const SkoolIntro: React.FC = () => {
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: C.bgMidnight }}>
      {/* ── Layer 0: Animated gradient background (entire video) ── */}
      <AnimatedBackground />

      {/* ── Layer 1: Glow orbs (entire video, ambient depth) ── */}
      <GlowOrbs />

      {/* ── Layer 2: Floating particles (entire video, upward drift) ── */}
      <FloatingParticles />

      {/* ── Layer 2b: DataStream (subtle Matrix-style data rain, entire video) ── */}
      <DataStream />

      {/* ── Layer 2c: HolographicGrid (Scene 4+5, perspective grid floor) ── */}
      <HolographicGrid startFrame={370} endFrame={600} />

      {/* ── Layer 2d: EnergyWave pulses at scene transitions ── */}
      <EnergyWave triggerFrame={120} />
      <EnergyWave triggerFrame={370} />
      <EnergyWave triggerFrame={490} />

      {/* ── Layer 3: Circuit pattern (Scene 3 fade-in) ── */}
      <CircuitPattern fadeInStart={228} opacity={0.18} />

      {/* ── Layer 4: Holographic hexagon (Scene 1, frames 8-120) ── */}
      <HolographicHexagon startFrame={8} endFrame={120} />

      {/* ── Layer 5: Scan line sweep (Scene 2, frames 120-225) ── */}
      <ScanLine startFrame={120} endFrame={225} />

      {/* ── Layer 6: Scene content ── */}

      {/* Scene 1: Opening Hook — frames 0-120 */}
      <Scene1 />

      {/* Scene 2: The Problem — frames 120-228 */}
      <Scene2 />

      {/* Scene 3: Transformation — frames 228-370 */}
      <Scene3 />

      {/* Scene 4: Social Proof — frames 370-490 */}
      <Scene4 />

      {/* Scene 5: CTA Close — frames 490-600 */}
      <Scene5 />

      {/* ── Layer 7: Transition flashes ── */}
      <TransitionFlash peakFrame={120} />
      <TransitionFlash peakFrame={228} />
      <TransitionFlash peakFrame={370} />
      <TransitionFlash peakFrame={490} />

      {/* ── Layer 8: Vignette (cinematic edge darkening) ── */}
      <Vignette startFrame={0} />
    </AbsoluteFill>
  );
};
