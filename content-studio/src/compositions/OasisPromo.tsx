import React from "react";
import {
  AbsoluteFill,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont, fontFamily as spaceGroteskFamily } from "@remotion/google-fonts/SpaceGrotesk";

// Load Space Grotesk with all weights we need
loadFont("normal", { weights: ["300", "400", "500", "700"], subsets: ["latin"] });

const FONT = spaceGroteskFamily;

const COLORS = {
  cyan: "#00D4AA",
  magenta: "#FF006E",
  white: "#FFFFFF",
  bgPurple: "#1a0533",
  bgTeal: "#0a2e3d",
  bgMidnight: "#0d1b3e",
};

const BULLETS = [
  "Automate Lead Follow-Up",
  "AI-Powered Scheduling",
  "24/7 Client Engagement",
];

type OasisPromoProps = {
  headline: string;
  subheadline: string;
  ctaText: string;
};

// ---------------------------------------------------------------------------
// Animated background — gradient shifts using interpolated angle + stops
// ---------------------------------------------------------------------------
const AnimatedBackground: React.FC = () => {
  const frame = useCurrentFrame();

  // Slowly rotate the gradient hue angle over 300 frames
  const angle = interpolate(frame, [0, 300], [135, 225], {
    extrapolateRight: "clamp",
  });

  // Fade in the background itself over the first 30 frames
  const bgOpacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity: bgOpacity,
        background: `linear-gradient(${angle}deg, ${COLORS.bgPurple} 0%, ${COLORS.bgMidnight} 45%, ${COLORS.bgTeal} 100%)`,
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Glowing accent orbs — cyan and magenta, slow pulse via sine
// ---------------------------------------------------------------------------
const GlowOrbs: React.FC = () => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Gentle pulse using a sine wave mapped to scale
  const pulse1 = interpolate(
    Math.sin((frame / 30) * Math.PI * 0.8),
    [-1, 1],
    [0.88, 1.12]
  );
  const pulse2 = interpolate(
    Math.sin((frame / 30) * Math.PI * 0.6 + 1.5),
    [-1, 1],
    [0.9, 1.1]
  );
  const pulse3 = interpolate(
    Math.sin((frame / 30) * Math.PI * 0.5 + 3),
    [-1, 1],
    [0.85, 1.15]
  );

  return (
    <div style={{ position: "absolute", inset: 0, opacity: fadeIn }}>
      {/* Top-right cyan orb */}
      <div
        style={{
          position: "absolute",
          top: 140,
          right: -120,
          width: 420,
          height: 420,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.cyan}55 0%, transparent 70%)`,
          filter: "blur(60px)",
          transform: `scale(${pulse1})`,
        }}
      />
      {/* Bottom-left magenta orb */}
      <div
        style={{
          position: "absolute",
          bottom: 260,
          left: -140,
          width: 480,
          height: 480,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.magenta}44 0%, transparent 70%)`,
          filter: "blur(70px)",
          transform: `scale(${pulse2})`,
        }}
      />
      {/* Center-bottom cyan accent */}
      <div
        style={{
          position: "absolute",
          bottom: -60,
          left: "50%",
          width: 360,
          height: 360,
          marginLeft: -180,
          borderRadius: "50%",
          background: `radial-gradient(circle, ${COLORS.cyan}33 0%, transparent 70%)`,
          filter: "blur(50px)",
          transform: `scale(${pulse3})`,
        }}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Floating geometric shapes — hexagons and circles with drift + rotation
// ---------------------------------------------------------------------------
type ShapeProps = {
  size: number;
  top: number;
  left: number;
  color: string;
  driftXAmp: number;
  driftYAmp: number;
  driftSpeed: number;
  driftOffset: number;
  rotateSpeed: number;
  shape: "hex" | "circle" | "diamond";
  blur: number;
  opacity: number;
};

const FloatingShape: React.FC<ShapeProps> = ({
  size,
  top,
  left,
  color,
  driftXAmp,
  driftYAmp,
  driftSpeed,
  driftOffset,
  rotateSpeed,
  shape,
  blur,
  opacity,
}) => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [0, 40], [0, 1], {
    extrapolateRight: "clamp",
  });

  const driftX = Math.sin((frame / 30) * Math.PI * driftSpeed + driftOffset) * driftXAmp;
  const driftY = Math.cos((frame / 30) * Math.PI * driftSpeed * 0.7 + driftOffset) * driftYAmp;
  const rotation = (frame * rotateSpeed) % 360;

  const borderRadius =
    shape === "circle" ? "50%" : shape === "diamond" ? "4px" : "18%";
  const diamondRotate = shape === "diamond" ? 45 : 0;

  return (
    <div
      style={{
        position: "absolute",
        top,
        left,
        width: size,
        height: size,
        borderRadius,
        border: `1.5px solid ${color}`,
        background: `${color}18`,
        filter: `blur(${blur}px)`,
        opacity: opacity * fadeIn,
        transform: `translate(${driftX}px, ${driftY}px) rotate(${rotation + diamondRotate}deg)`,
      }}
    />
  );
};

const FloatingShapes: React.FC = () => (
  <div style={{ position: "absolute", inset: 0 }}>
    <FloatingShape size={180} top={80} left={-30} color={COLORS.cyan} driftXAmp={18} driftYAmp={22} driftSpeed={0.4} driftOffset={0} rotateSpeed={0.12} shape="hex" blur={3} opacity={0.18} />
    <FloatingShape size={120} top={340} left={880} color={COLORS.magenta} driftXAmp={14} driftYAmp={18} driftSpeed={0.3} driftOffset={1.2} rotateSpeed={0.09} shape="hex" blur={2} opacity={0.15} />
    <FloatingShape size={90} top={1300} left={-20} color={COLORS.cyan} driftXAmp={20} driftYAmp={14} driftSpeed={0.5} driftOffset={2.4} rotateSpeed={0.15} shape="circle" blur={4} opacity={0.14} />
    <FloatingShape size={140} top={1100} left={900} color={COLORS.magenta} driftXAmp={16} driftYAmp={20} driftSpeed={0.35} driftOffset={0.8} rotateSpeed={0.1} shape="diamond" blur={3} opacity={0.12} />
    <FloatingShape size={200} top={580} left={820} color={COLORS.cyan} driftXAmp={12} driftYAmp={16} driftSpeed={0.28} driftOffset={3.6} rotateSpeed={0.08} shape="hex" blur={5} opacity={0.1} />
    <FloatingShape size={70} top={160} left={500} color={COLORS.magenta} driftXAmp={22} driftYAmp={12} driftSpeed={0.55} driftOffset={1.8} rotateSpeed={0.18} shape="circle" blur={2} opacity={0.13} />
  </div>
);

// ---------------------------------------------------------------------------
// Perspective grid lines at the bottom
// ---------------------------------------------------------------------------
const GridLines: React.FC = () => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [10, 50], [0, 1], {
    extrapolateRight: "clamp",
  });

  // 7 vertical vanishing lines + 5 horizontal bands
  const verticals = [-500, -300, -150, 0, 150, 300, 500];
  const horizontals = [0.0, 0.25, 0.5, 0.72, 0.9];

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        height: 380,
        opacity: fadeIn * 0.22,
        overflow: "hidden",
      }}
    >
      <svg
        width="1080"
        height="380"
        viewBox="0 0 1080 380"
        style={{ display: "block" }}
      >
        <defs>
          <linearGradient id="gridFade" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={COLORS.cyan} stopOpacity="0" />
            <stop offset="60%" stopColor={COLORS.cyan} stopOpacity="0.6" />
            <stop offset="100%" stopColor={COLORS.cyan} stopOpacity="0.4" />
          </linearGradient>
        </defs>
        {/* Vanishing vertical lines from horizon point at top-center */}
        {verticals.map((offset) => (
          <line
            key={`v${offset}`}
            x1={540}
            y1={0}
            x2={540 + offset}
            y2={380}
            stroke="url(#gridFade)"
            strokeWidth="0.8"
          />
        ))}
        {/* Horizontal bands at increasing intervals (perspective) */}
        {horizontals.map((t) => (
          <line
            key={`h${t}`}
            x1={0}
            y1={t * 380}
            x2={1080}
            y2={t * 380}
            stroke={COLORS.cyan}
            strokeWidth="0.6"
            strokeOpacity="0.35"
          />
        ))}
      </svg>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Brand name — "OASIS AI Solutions" slides up, frame 15-45
// ---------------------------------------------------------------------------
const BrandName: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const slideProgress = spring({
    frame: frame - 15,
    fps,
    config: { damping: 22, stiffness: 140, mass: 1 },
  });

  const translateY = interpolate(slideProgress, [0, 1], [50, 0]);
  const opacity = interpolate(frame, [15, 35], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtle glow pulse on the brand name
  const glowIntensity = interpolate(
    Math.sin((frame / 30) * Math.PI * 1.2),
    [-1, 1],
    [8, 22]
  );

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        textAlign: "center",
        letterSpacing: 8,
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 36,
          fontWeight: 700,
          letterSpacing: 8,
          textTransform: "uppercase",
          color: COLORS.cyan,
          textShadow: `0 0 ${glowIntensity}px ${COLORS.cyan}cc, 0 0 ${glowIntensity * 2}px ${COLORS.cyan}66`,
        }}
      >
        OASIS AI Solutions
      </div>
      {/* Thin separator line beneath brand name */}
      <div
        style={{
          marginTop: 10,
          height: 1,
          background: `linear-gradient(90deg, transparent, ${COLORS.cyan}88, transparent)`,
          width: "100%",
        }}
      />
    </div>
  );
};

// ---------------------------------------------------------------------------
// Headline — typewriter effect, frames 40-75
// ---------------------------------------------------------------------------
const Headline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();

  // Typewriter: reveal characters over frames 40-75 (35 frames for full text)
  const charsToShow = Math.floor(
    interpolate(frame, [40, 75], [0, text.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    })
  );
  const visibleText = text.slice(0, charsToShow);

  // Cursor blink after text is done
  const cursorVisible =
    charsToShow < text.length || Math.sin((frame / 30) * Math.PI * 4) > 0;

  const containerOpacity = interpolate(frame, [38, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity: containerOpacity,
        textAlign: "center",
        padding: "0 60px",
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 64,
          fontWeight: 700,
          color: COLORS.white,
          lineHeight: 1.15,
          textShadow: "0 4px 24px rgba(0,0,0,0.5)",
        }}
      >
        {visibleText}
        {cursorVisible && (
          <span
            style={{
              display: "inline-block",
              width: 3,
              height: "0.85em",
              background: COLORS.cyan,
              marginLeft: 4,
              verticalAlign: "middle",
              boxShadow: `0 0 8px ${COLORS.cyan}`,
            }}
          />
        )}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Subheadline — fades in, frames 70-100
// ---------------------------------------------------------------------------
const Subheadline: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - 70,
    fps,
    config: { damping: 26, stiffness: 100 },
  });

  const translateY = interpolate(progress, [0, 1], [30, 0]);
  const opacity = interpolate(frame, [70, 92], [0, 0.72], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        opacity,
        transform: `translateY(${translateY}px)`,
        textAlign: "center",
        padding: "0 80px",
      }}
    >
      <div
        style={{
          fontFamily: FONT,
          fontSize: 32,
          fontWeight: 400,
          color: COLORS.white,
          lineHeight: 1.5,
        }}
      >
        {text}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Bullet list — staggered spring-in from left, frames 90-180
// ---------------------------------------------------------------------------
const BulletList: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 28,
        padding: "0 72px",
        width: "100%",
      }}
    >
      {BULLETS.map((bullet, i) => {
        const startFrame = 90 + i * 30;

        const progress = spring({
          frame: frame - startFrame,
          fps,
          config: { damping: 20, stiffness: 160, mass: 0.9 },
        });

        const translateX = interpolate(progress, [0, 1], [-80, 0]);
        const opacity = interpolate(frame, [startFrame, startFrame + 18], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });

        // Dot glow pulse per bullet, slightly offset
        const dotGlow = interpolate(
          Math.sin((frame / 30) * Math.PI * 1.1 + i * 1.2),
          [-1, 1],
          [4, 14]
        );

        return (
          <div
            key={bullet}
            style={{
              opacity,
              transform: `translateX(${translateX}px)`,
              display: "flex",
              alignItems: "center",
              gap: 22,
            }}
          >
            {/* Glowing cyan dot indicator */}
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: COLORS.cyan,
                flexShrink: 0,
                boxShadow: `0 0 ${dotGlow}px ${COLORS.cyan}, 0 0 ${dotGlow * 2}px ${COLORS.cyan}66`,
              }}
            />
            <div
              style={{
                fontFamily: FONT,
                fontSize: 28,
                fontWeight: 500,
                color: COLORS.white,
                lineHeight: 1.3,
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

// ---------------------------------------------------------------------------
// CTA button — bouncy scale-in, frames 200-240, then glowing border pulse
// ---------------------------------------------------------------------------
const CTAButton: React.FC<{ text: string }> = ({ text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const scaleProgress = spring({
    frame: frame - 200,
    fps,
    config: { damping: 12, stiffness: 200, mass: 0.8 },
  });

  const scale = interpolate(scaleProgress, [0, 1], [0, 1]);

  const opacity = interpolate(frame, [200, 215], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Glowing border pulse after button appears
  const borderGlow = interpolate(
    Math.sin((frame / 30) * Math.PI * 1.4),
    [-1, 1],
    [10, 28]
  );

  // Subtle scale breathe after it arrives
  const breathe = interpolate(
    Math.sin((frame / 30) * Math.PI * 0.9),
    [-1, 1],
    [0.985, 1.015]
  );

  const finalScale = scale * breathe;

  return (
    <div
      style={{
        opacity,
        transform: `scale(${finalScale})`,
        display: "flex",
        justifyContent: "center",
      }}
    >
      {/* Outer glow ring */}
      <div
        style={{
          borderRadius: 60,
          padding: 2,
          background: `linear-gradient(135deg, ${COLORS.cyan}, ${COLORS.magenta})`,
          boxShadow: `0 0 ${borderGlow}px ${COLORS.cyan}88, 0 0 ${borderGlow * 1.5}px ${COLORS.magenta}55`,
        }}
      >
        {/* Inner button */}
        <div
          style={{
            background: "rgba(13, 27, 62, 0.92)",
            borderRadius: 58,
            padding: "26px 72px",
            backdropFilter: "blur(8px)",
          }}
        >
          <div
            style={{
              fontFamily: FONT,
              fontSize: 36,
              fontWeight: 700,
              letterSpacing: 1,
              background: `linear-gradient(90deg, ${COLORS.cyan}, #7eeeff, ${COLORS.magenta})`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
              whiteSpace: "nowrap",
            }}
          >
            {text}
          </div>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Outro fade/scale — frames 260-300
// ---------------------------------------------------------------------------
const useOutroTransform = () => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [260, 295], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [260, 300], [1, 0.94], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return { opacity, scale };
};

// ---------------------------------------------------------------------------
// Root composition
// ---------------------------------------------------------------------------
export const OasisPromo: React.FC<OasisPromoProps> = ({
  headline,
  subheadline,
  ctaText,
}) => {
  const { opacity: outroOpacity, scale: outroScale } = useOutroTransform();

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      {/* Layer 0 — animated gradient background */}
      <AnimatedBackground />

      {/* Layer 1 — glow orbs */}
      <GlowOrbs />

      {/* Layer 2 — floating geometric shapes */}
      <FloatingShapes />

      {/* Layer 3 — perspective grid at bottom */}
      <GridLines />

      {/* Layer 4 — all content, subject to outro fade/scale */}
      <AbsoluteFill
        style={{
          opacity: outroOpacity,
          transform: `scale(${outroScale})`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 44,
          padding: "80px 0",
        }}
      >
        {/* Brand name — frames 15-45 */}
        <BrandName />

        {/* Headline typewriter — frames 40-75 */}
        <Headline text={headline} />

        {/* Subheadline — frames 70-100 */}
        <Subheadline text={subheadline} />

        {/* Bullet list — frames 90-180 */}
        <BulletList />

        {/* CTA button — frames 200-240 */}
        <CTAButton text={ctaText} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
