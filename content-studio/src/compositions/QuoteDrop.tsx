import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont, fontFamily } from "@remotion/google-fonts/SpaceGrotesk";

loadFont();

// ─── Palette ────────────────────────────────────────────────────────────────
const COLORS = {
  bgDeep: "#2d0a3e",   // dark magenta
  bgOcean: "#0a1628",  // deep ocean blue
  bgAmber: "#3d2200",  // warm amber shadow
  magenta: "#FF006E",  // accent / quote marks
  cyan: "#00D4FF",     // line left
  quote: "#FFFFFF",
  author: "rgba(255,255,255,0.6)",
};

// ─── Particles ───────────────────────────────────────────────────────────────
interface Particle {
  x: number;        // 0–1 normalized to frame width
  y: number;        // starting y, 0–1
  size: number;     // px radius
  speed: number;    // frames to travel full height
  delay: number;    // frame offset
  opacity: number;  // base opacity
}

const PARTICLES: Particle[] = [
  { x: 0.12, y: 0.95, size: 4, speed: 180, delay: 0,  opacity: 0.7 },
  { x: 0.28, y: 0.85, size: 2, speed: 220, delay: 10, opacity: 0.5 },
  { x: 0.45, y: 0.90, size: 6, speed: 160, delay: 5,  opacity: 0.6 },
  { x: 0.62, y: 0.80, size: 3, speed: 200, delay: 15, opacity: 0.8 },
  { x: 0.75, y: 0.92, size: 2, speed: 240, delay: 3,  opacity: 0.4 },
  { x: 0.88, y: 0.75, size: 5, speed: 170, delay: 20, opacity: 0.65 },
  { x: 0.20, y: 0.70, size: 3, speed: 210, delay: 8,  opacity: 0.55 },
  { x: 0.55, y: 0.65, size: 2, speed: 190, delay: 12, opacity: 0.45 },
  { x: 0.93, y: 0.88, size: 4, speed: 150, delay: 7,  opacity: 0.7 },
];

const FloatingParticles: React.FC = () => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  // Fade in the entire particle layer 0→15
  const layerOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div style={{ position: "absolute", inset: 0, opacity: layerOpacity }}>
      {PARTICLES.map((p, i) => {
        // Each particle travels upward continuously, looping
        const elapsed = Math.max(0, frame - p.delay);
        // progress 0→1 across one full cycle
        const progress = (elapsed % p.speed) / p.speed;
        const yPos = (p.y - progress) * height;
        // Fade out near top so it disappears gracefully
        const particleOpacity = p.opacity * interpolate(progress, [0.7, 1.0], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        // Gentle horizontal drift using a sine pattern per particle
        const xDrift = Math.sin(elapsed * 0.02 + i) * 20;

        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p.x * width + xDrift,
              top: yPos,
              width: p.size * 2,
              height: p.size * 2,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${COLORS.cyan}, ${COLORS.magenta})`,
              opacity: particleOpacity,
              boxShadow: `0 0 ${p.size * 4}px ${p.size}px ${COLORS.cyan}55`,
            }}
          />
        );
      })}
    </div>
  );
};

// ─── Animated Gradient Background ────────────────────────────────────────────
const AnimatedBackground: React.FC = () => {
  const frame = useCurrentFrame();

  // Fade in 0→15
  const bgOpacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Slowly morph the gradient angle over the clip's lifetime
  const angle = interpolate(frame, [0, 150], [145, 165], {
    extrapolateRight: "clamp",
  });

  // The amber mid-stop shifts slightly to breathe warmth in and out
  const amberStop = interpolate(frame, [0, 75, 150], [30, 45, 30], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(${angle}deg, ${COLORS.bgDeep} 0%, ${COLORS.bgAmber} ${amberStop}%, ${COLORS.bgOcean} 100%)`,
        opacity: bgOpacity,
      }}
    />
  );
};

// ─── Oversized Decorative Quote Marks ────────────────────────────────────────
const DecorativeQuoteMark: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Scale in frames 5–25 with a spring
  const springValue = spring({
    frame: frame - 5,
    fps,
    config: { damping: 14, stiffness: 80, mass: 1.2 },
  });
  const scale = interpolate(springValue, [0, 1], [0.4, 1], {
    extrapolateRight: "clamp",
  });

  // Subtle breathe pulse after frame 25 — maps a slow sine to scale offset
  const breathe = interpolate(
    Math.sin(Math.max(0, frame - 25) * 0.04),
    [-1, 1],
    [0.98, 1.02]
  );

  const finalScale = scale * breathe;

  // Fade in coincides with spring entrance
  const opacity = interpolate(frame, [5, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 160,
        left: 60,
        fontSize: 320,
        lineHeight: 1,
        fontFamily: `${fontFamily}, serif`,
        fontWeight: 700,
        color: COLORS.magenta,
        opacity: opacity * 0.15,
        transform: `scale(${finalScale})`,
        transformOrigin: "top left",
        userSelect: "none",
        // Soft blur so it reads as a behind-glass texture, not a character
        filter: "blur(2px)",
        letterSpacing: -10,
      }}
    >
      &ldquo;
    </div>
  );
};

// ─── Accent Line ──────────────────────────────────────────────────────────────
const AccentLine: React.FC = () => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();

  // Draw left-to-right frames 10–30
  const progress = interpolate(frame, [10, 30], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Fade out near the end 130→150
  const fadeOut = interpolate(frame, [130, 150], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 520,
        left: 80,
        width: (width - 160) * progress,
        height: 2,
        background: `linear-gradient(90deg, ${COLORS.cyan}, ${COLORS.magenta})`,
        opacity: fadeOut,
        borderRadius: 2,
        boxShadow: `0 0 12px 2px ${COLORS.cyan}88`,
      }}
    />
  );
};

// ─── Typewriter Quote ─────────────────────────────────────────────────────────
const TypewriterQuote: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  // Type frames 20→90 (70-frame window)
  const charsToShow = Math.floor(
    interpolate(frame, [20, 90], [0, text.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );

  // Fade out 130→150
  const fadeOut = interpolate(frame, [130, 150], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Gentle scale up on exit 130→150
  const exitScale = interpolate(frame, [130, 150], [1, 1.04], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        fontSize: 52,
        fontWeight: 500,
        color: COLORS.quote,
        fontFamily: `${fontFamily}, sans-serif`,
        lineHeight: 1.4,
        textAlign: "center",
        maxWidth: "85%",
        whiteSpace: "pre-wrap",
        opacity: fadeOut,
        transform: `scale(${exitScale})`,
      }}
    >
      {text.slice(0, charsToShow)}
    </div>
  );
};

// ─── Author Line ──────────────────────────────────────────────────────────────
const AuthorLine: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Fade + slide up frames 95→115
  const springValue = spring({
    frame: frame - 95,
    fps,
    config: { damping: 18, stiffness: 100 },
  });

  const opacity = interpolate(springValue, [0, 1], [0, 1], {
    extrapolateRight: "clamp",
  });
  const translateY = interpolate(springValue, [0, 1], [20, 0], {
    extrapolateRight: "clamp",
  });

  // Fade out 130→150
  const fadeOut = interpolate(frame, [130, 150], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const exitScale = interpolate(frame, [130, 150], [1, 1.04], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: opacity * fadeOut,
        transform: `translateY(${translateY}px) scale(${exitScale})`,
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 16,
      }}
    >
      {/* Thin gradient separator */}
      <div
        style={{
          width: 56,
          height: 1,
          background: `linear-gradient(90deg, transparent, ${COLORS.cyan}, transparent)`,
        }}
      />
      <div
        style={{
          fontSize: 28,
          color: COLORS.author,
          fontFamily: `${fontFamily}, sans-serif`,
          fontWeight: 400,
          fontStyle: "italic",
          letterSpacing: 1,
        }}
      >
        — {text}
      </div>
    </div>
  );
};

// ─── Root Composition ─────────────────────────────────────────────────────────
export const QuoteDrop: React.FC<{ quote: string; author: string }> = ({
  quote,
  author,
}) => {
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Layer 0: morphing gradient bg */}
      <AnimatedBackground />

      {/* Layer 1: floating firefly particles */}
      <FloatingParticles />

      {/* Layer 2: oversized decorative quote mark (behind text) */}
      <DecorativeQuoteMark />

      {/* Layer 3: horizontal accent line */}
      <AccentLine />

      {/* Layer 4: quote + author, vertically centered */}
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          flexDirection: "column",
          gap: 48,
          paddingTop: 80,
        }}
      >
        <TypewriterQuote text={quote} />
        <AuthorLine text={author} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
