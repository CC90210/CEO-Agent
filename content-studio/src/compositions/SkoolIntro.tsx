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

// Agency Accelerants brand palette — black-first, clean, bold
const C = {
  white: "#FFFFFF",
  offWhite: "#E8E8E8",
  black: "#000000",
  bgDark: "#0A0A0A",
  bgCard: "#111111",
  patternA: "#1A1A1A",
  accent: "#CCCCCC",
  highlight: "#FFFFFF",
  subtleGlow: "#444444",
  dimText: "#888888",
};

// ---------------------------------------------------------------------------
// Repeating "A" pattern background — matches Agency Accelerants brand
// ---------------------------------------------------------------------------
const RepeatingABackground: React.FC = () => {
  const frame = useCurrentFrame();

  const fadeIn = interpolate(frame, [0, 20], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Subtle drift animation — pattern moves slowly
  const driftX = interpolate(frame, [0, 600], [0, -40], {
    extrapolateRight: "clamp",
  });
  const driftY = interpolate(frame, [0, 600], [0, -20], {
    extrapolateRight: "clamp",
  });

  // Grid of bold italic "A" characters
  const cols = 22;
  const rows = 14;
  const cellW = 110;
  const cellH = 100;

  const letters: React.ReactNode[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = c * cellW - 60;
      const y = r * cellH - 40;
      // Stagger odd rows for visual rhythm
      const offsetX = r % 2 === 1 ? cellW * 0.5 : 0;

      letters.push(
        <div
          key={`${r}-${c}`}
          style={{
            position: "absolute",
            left: x + offsetX,
            top: y,
            fontFamily: FONT,
            fontSize: 72,
            fontWeight: 700,
            fontStyle: "italic",
            color: C.patternA,
            lineHeight: 1,
            userSelect: "none",
          }}
        >
          A
        </div>,
      );
    }
  }

  return (
    <div
      style={{
        position: "absolute",
        inset: -100,
        opacity: fadeIn,
        transform: `translate(${driftX}px, ${driftY}px)`,
        overflow: "hidden",
      }}
    >
      {letters}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Subtle vignette — darkens edges for focus
// ---------------------------------------------------------------------------
const Vignette: React.FC<{ startFrame: number }> = ({ startFrame }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(frame, [startFrame, startFrame + 20], [0, 1], {
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
          "radial-gradient(ellipse at center, transparent 40%, rgba(0,0,0,0.7) 100%)",
        pointerEvents: "none",
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Clean transition wipe — horizontal sweep
// ---------------------------------------------------------------------------
const TransitionWipe: React.FC<{ peakFrame: number }> = ({ peakFrame }) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [peakFrame - 6, peakFrame, peakFrame + 10],
    [0, 0.2, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
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
// Minimal scan line — subtle horizontal sweep
// ---------------------------------------------------------------------------
const ScanLine: React.FC<{ startFrame: number; endFrame: number }> = ({
  startFrame,
  endFrame,
}) => {
  const frame = useCurrentFrame();

  const opacity = interpolate(
    frame,
    [startFrame, startFrame + 8, endFrame - 8, endFrame],
    [0, 0.25, 0.25, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const top = progress * 1080;

  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 0,
        right: 0,
        height: 1,
        background: `linear-gradient(90deg, transparent, ${C.accent}cc, transparent)`,
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

// ---------------------------------------------------------------------------
// Scene 1: Opening — Agency Accelerants hero
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
  const titleY = interpolate(titleSpring, [0, 1], [60, 0]);
  const titleOpacity = interpolate(frame, [20, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Subtitle fades in from frame 48
  const subtitleSpring = spring({
    frame: frame - 48,
    fps,
    config: { damping: 18, stiffness: 80 },
  });
  const subtitleY = interpolate(subtitleSpring, [0, 1], [30, 0]);
  const subtitleOpacity = interpolate(frame, [48, 70], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Separator line expands from center
  const lineScale = interpolate(frame, [30, 60], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Scene exit
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
        paddingBottom: 60,
      }}
    >
      {/* "AGENCY ACCELERANTS" — bold, white, italic to match brand */}
      <div
        style={{
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
          textAlign: "center",
          padding: "0 80px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 92,
            fontWeight: 700,
            fontStyle: "italic",
            letterSpacing: 6,
            textTransform: "uppercase",
            color: C.white,
            lineHeight: 1.05,
            textShadow: "0 4px 40px rgba(0,0,0,0.8)",
          }}
        >
          AGENCY
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 92,
            fontWeight: 700,
            fontStyle: "italic",
            letterSpacing: 6,
            textTransform: "uppercase",
            color: C.white,
            lineHeight: 1.05,
            textShadow: "0 4px 40px rgba(0,0,0,0.8)",
          }}
        >
          ACCELERANTS
        </div>
      </div>

      {/* Separator — clean white line */}
      <div
        style={{
          marginTop: 20,
          width: `${lineScale * 600}px`,
          height: 2,
          background: `linear-gradient(90deg, transparent, ${C.white}cc, transparent)`,
        }}
      />

      {/* "by Bennet Spooner" */}
      <div
        style={{
          marginTop: 18,
          opacity: subtitleOpacity,
          transform: `translateY(${subtitleY}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 24,
            fontWeight: 400,
            letterSpacing: 6,
            color: C.dimText,
            textTransform: "uppercase",
            textAlign: "center",
          }}
        >
          by Bennet Spooner
        </div>
      </div>
    </AbsoluteFill>
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

  const sceneIn = interpolate(frame, [120, 144], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [204, 228], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // Headline typewriter
  const headline = "Still doing everything manually?";
  const charsShown = Math.floor(
    interpolate(frame, [132, 178], [0, headline.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
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
        padding: "0 140px",
        gap: 40,
      }}
    >
      {/* Headline */}
      <div>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 60,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1.15,
            textShadow: "0 4px 30px rgba(0,0,0,0.7)",
          }}
        >
          {visibleHeadline}
          {cursorVisible && (
            <span
              style={{
                display: "inline-block",
                width: 3,
                height: "0.8em",
                background: C.white,
                marginLeft: 5,
                verticalAlign: "middle",
              }}
            />
          )}
        </div>
      </div>

      {/* Staggered bullet cards */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          gap: 28,
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
          const bulletY = interpolate(bulletProgress, [0, 1], [60, 0]);
          const bulletOpacity = interpolate(
            frame,
            [bulletStart, bulletStart + 14],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          );

          return (
            <div
              key={i}
              style={{
                opacity: bulletOpacity,
                transform: `translateY(${bulletY}px)`,
                flex: 1,
              }}
            >
              <div
                style={{
                  borderRadius: 12,
                  border: `1px solid ${C.subtleGlow}`,
                  background: "rgba(20,20,20,0.85)",
                  padding: "20px 24px",
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  backdropFilter: "blur(8px)",
                }}
              >
                <div
                  style={{
                    fontFamily: FONT,
                    fontSize: 22,
                    fontWeight: 400,
                    color: C.dimText,
                    flexShrink: 0,
                  }}
                >
                  ✕
                </div>
                <div
                  style={{
                    fontFamily: FONT,
                    fontSize: 28,
                    fontWeight: 500,
                    color: C.offWhite,
                    lineHeight: 1.25,
                  }}
                >
                  {bullet}
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

  const sceneIn = interpolate(frame, [228, 254], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [348, 370], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // "What if AI did 90% of it?" spring
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
        padding: "0 100px",
        gap: 40,
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
            fontSize: 64,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1.15,
            textShadow: "0 4px 40px rgba(0,0,0,0.8)",
          }}
        >
          What if AI did{" "}
          <span
            style={{
              fontStyle: "italic",
              textDecoration: "underline",
              textUnderlineOffset: 8,
            }}
          >
            90%
          </span>{" "}
          of it?
        </div>
      </div>

      {/* Feature cards */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          gap: 20,
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
          const cardY = interpolate(cardSpring, [0, 1], [60, 0]);
          const cardOpacity = interpolate(
            frame,
            [cardStart, cardStart + 16],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          );

          return (
            <div
              key={i}
              style={{
                opacity: cardOpacity,
                transform: `translateY(${cardY}px)`,
                flex: 1,
              }}
            >
              <div
                style={{
                  borderRadius: 16,
                  padding: 1.5,
                  background: `linear-gradient(135deg, ${C.accent}44, ${C.subtleGlow}22)`,
                  height: "100%",
                }}
              >
                <div
                  style={{
                    background: "rgba(15,15,15,0.92)",
                    borderRadius: 15,
                    padding: "28px 28px",
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    backdropFilter: "blur(12px)",
                  }}
                >
                  <div style={{ fontSize: 32, flexShrink: 0 }}>{card.icon}</div>
                  <div
                    style={{
                      fontFamily: FONT,
                      fontSize: 26,
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
const Scene4: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneIn = interpolate(frame, [370, 396], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOut = interpolate(frame, [468, 490], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sceneOpacity = Math.min(sceneIn, sceneOut);

  // Animated counter: $0 → $5,000
  const counterValue = Math.floor(
    interpolate(frame, [385, 450], [0, 5000], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );

  // "Monthly Recurring Revenue Target" fades in
  const labelOpacity = interpolate(frame, [400, 422], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Tagline spring
  const taglineSpring = spring({
    frame: frame - 420,
    fps,
    config: { damping: 20, stiffness: 80 },
  });
  const taglineY = interpolate(taglineSpring, [0, 1], [24, 0]);
  const taglineOpacity = interpolate(frame, [420, 440], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

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
        gap: 24,
      }}
    >
      {/* Animated counter */}
      <div style={{ textAlign: "center" }}>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 120,
            fontWeight: 700,
            color: C.white,
            lineHeight: 1,
            textShadow: "0 0 60px rgba(255,255,255,0.3), 0 4px 40px rgba(0,0,0,0.6)",
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
          padding: "0 120px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 24,
            fontWeight: 400,
            color: C.dimText,
            letterSpacing: 3,
            textTransform: "uppercase",
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
          padding: "0 80px",
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 30,
            fontWeight: 600,
            color: C.offWhite,
            lineHeight: 1.3,
          }}
        >
          Built by entrepreneurs, for entrepreneurs
        </div>
      </div>

      {/* Achievement badges */}
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          gap: 14,
          padding: "0 80px",
          width: "100%",
          justifyContent: "center",
        }}
      >
        {BADGES.map((badge, i) => {
          const badgeStart = 440 + i * 14;
          const badgeSpring = spring({
            frame: frame - badgeStart,
            fps,
            config: { damping: 20, stiffness: 180, mass: 0.6 },
          });
          const badgeY = interpolate(badgeSpring, [0, 1], [40, 0]);
          const badgeOpacity = interpolate(
            frame,
            [badgeStart, badgeStart + 12],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          );

          return (
            <div
              key={i}
              style={{
                opacity: badgeOpacity,
                transform: `translateY(${badgeY}px)`,
                display: "flex",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  background: "rgba(255,255,255,0.06)",
                  border: `1px solid ${C.subtleGlow}`,
                  borderRadius: 50,
                  padding: "8px 24px",
                  whiteSpace: "nowrap",
                }}
              >
                <div
                  style={{
                    fontFamily: FONT,
                    fontSize: 18,
                    fontWeight: 500,
                    color: C.offWhite,
                    letterSpacing: 1,
                  }}
                >
                  {badge}
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
// Scene 5: CTA Close
// ---------------------------------------------------------------------------
const Scene5: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const sceneOpacity = interpolate(frame, [490, 514], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // "JOIN THE ACCELERANTS" bouncy spring
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

  // Border shimmer
  const borderAngle = interpolate(frame, [498, 600], [0, 360], {
    extrapolateRight: "clamp",
  });

  // "Your AI Empire Starts Here" typewriter
  const tagline = "Your AI Empire Starts Here";
  const taglineChars = Math.floor(
    interpolate(frame, [518, 560], [0, tagline.length], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );
  const visibleTagline = tagline.slice(0, taglineChars);

  // Brand watermark
  const brandOpacity = interpolate(frame, [540, 562], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Final pulse
  const finalPulse = interpolate(
    Math.sin(
      interpolate(frame, [570, 600], [0, Math.PI], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      }),
    ),
    [0, 1],
    [1, 1.018],
  );

  return (
    <AbsoluteFill
      style={{
        opacity: sceneOpacity,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 32,
        padding: "0 120px",
        transform: `scale(${finalPulse})`,
      }}
    >
      {/* "JOIN THE ACCELERANTS" CTA */}
      <div
        style={{
          opacity: ctaOpacity,
          transform: `scale(${ctaScale})`,
          width: "100%",
          maxWidth: 1100,
          display: "flex",
          justifyContent: "center",
        }}
      >
        {/* Outer animated border ring */}
        <div
          style={{
            borderRadius: 20,
            padding: 2,
            background: `linear-gradient(${borderAngle}deg, ${C.white}88, ${C.accent}44, ${C.white}88)`,
            width: "100%",
          }}
        >
          <div
            style={{
              background: "rgba(10, 10, 10, 0.95)",
              borderRadius: 18,
              padding: "32px 48px",
              textAlign: "center",
              backdropFilter: "blur(16px)",
            }}
          >
            <div
              style={{
                fontFamily: FONT,
                fontSize: 64,
                fontWeight: 700,
                fontStyle: "italic",
                letterSpacing: 4,
                textTransform: "uppercase",
                color: C.white,
                lineHeight: 1.05,
                textShadow: "0 0 40px rgba(255,255,255,0.2)",
              }}
            >
              JOIN THE
            </div>
            <div
              style={{
                fontFamily: FONT,
                fontSize: 64,
                fontWeight: 700,
                fontStyle: "italic",
                letterSpacing: 4,
                textTransform: "uppercase",
                color: C.white,
                lineHeight: 1.05,
                textShadow: "0 0 40px rgba(255,255,255,0.2)",
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
            fontSize: 34,
            fontWeight: 400,
            color: C.offWhite,
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
                background: C.white,
                marginLeft: 4,
                verticalAlign: "middle",
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
          bottom: 48,
          left: 0,
          right: 0,
        }}
      >
        <div
          style={{
            marginBottom: 14,
            height: 1,
            background: `linear-gradient(90deg, transparent, ${C.accent}55, transparent)`,
            width: "40%",
            marginLeft: "auto",
            marginRight: "auto",
          }}
        />
        <div
          style={{
            fontFamily: FONT,
            fontSize: 18,
            fontWeight: 400,
            letterSpacing: 6,
            textTransform: "uppercase",
            color: C.dimText,
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
// Root composition
// ---------------------------------------------------------------------------
export const SkoolIntro: React.FC = () => {
  return (
    <AbsoluteFill style={{ overflow: "hidden", background: C.bgDark }}>
      {/* ── Layer 0: Black background with repeating "A" pattern ── */}
      <RepeatingABackground />

      {/* ── Layer 1: Vignette for focus ── */}
      <Vignette startFrame={0} />

      {/* ── Layer 2: Subtle scan line (Scene 2) ── */}
      <ScanLine startFrame={120} endFrame={225} />

      {/* ── Layer 3: Scene content ── */}

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

      {/* ── Layer 4: Transition wipes ── */}
      <TransitionWipe peakFrame={120} />
      <TransitionWipe peakFrame={228} />
      <TransitionWipe peakFrame={370} />
      <TransitionWipe peakFrame={490} />
    </AbsoluteFill>
  );
};
