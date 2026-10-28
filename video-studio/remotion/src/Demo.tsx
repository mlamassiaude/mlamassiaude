import { Audio } from "@remotion/media";
import { noise2D } from "@remotion/noise";
import { springTiming, TransitionSeries } from "@remotion/transitions";
import { slide } from "@remotion/transitions/slide";
import {
  AbsoluteFill,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

const INK = "#f4f1ea";
const GROUND = "#0e0f13";

export const demoSchemaDefaults = {
  title: "Video Studio",
  accent: "#ff5a36",
};

type DemoProps = typeof demoSchemaDefaults;

const SCENE = 120;
const TRANSITION = 20;
export const DEMO_DURATION = SCENE * 2 - TRANSITION;

// Slowly drifting dots, driven by deterministic noise so every render matches.
const Field: React.FC<{ accent: string }> = ({ accent }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const dots = Array.from({ length: 40 }, (_, i) => {
    const x = (noise2D("x", i, frame / 240) * 0.5 + 0.5) * width;
    const y = (noise2D("y", i, frame / 240) * 0.5 + 0.5) * height;
    const size = 4 + (i % 5) * 3;
    return (
      <div
        key={i}
        style={{
          position: "absolute",
          left: x,
          top: y,
          width: size,
          height: size,
          borderRadius: "50%",
          background: i % 4 === 0 ? accent : "#2a2d38",
        }}
      />
    );
  });
  return <AbsoluteFill>{dots}</AbsoluteFill>;
};

const TitleScene: React.FC<DemoProps> = ({ title, accent }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 200 } });
  const bar = spring({ frame: frame - 15, fps, config: { damping: 18, stiffness: 120 } });
  const kicker = interpolate(frame, [5, 25], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: GROUND, alignItems: "center", justifyContent: "center", fontFamily: "Inter" }}>
      <Field accent={accent} />
      <div style={{ color: accent, fontSize: 30, letterSpacing: "0.3em", opacity: kicker, marginBottom: 24 }}>
        REMOTION · REACT · TYPESCRIPT
      </div>
      <h1
        style={{
          color: INK,
          fontSize: 168,
          fontWeight: 900,
          letterSpacing: "-0.04em",
          margin: 0,
          transform: `scale(${interpolate(pop, [0, 1], [1.12, 1])})`,
          filter: `blur(${interpolate(pop, [0, 1], [10, 0])}px)`,
        }}
      >
        {title}
      </h1>
      <div style={{ width: 520, height: 10, marginTop: 28, background: accent, transform: `scaleX(${bar})`, transformOrigin: "left" }} />
    </AbsoluteFill>
  );
};

const STACK = [
  ["01", "HyperFrames", "HTML + GSAP, seeked frame by frame"],
  ["02", "Remotion", "React components as video"],
  ["03", "FFmpeg", "Encode, cut, mix, convert"],
];

const StackScene: React.FC<DemoProps> = ({ accent }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const vertical = height > width;

  return (
    <AbsoluteFill
      style={{
        background: GROUND,
        flexDirection: vertical ? "column" : "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 48,
        fontFamily: "Inter",
      }}
    >
      {STACK.map(([num, name, role], i) => {
        const enter = spring({ frame: frame - i * 6, fps, config: { damping: 12, mass: 0.8 } });
        return (
          <div
            key={name}
            style={{
              width: 460,
              height: vertical ? 420 : 520,
              padding: "56px 48px",
              borderRadius: 28,
              background: "#191b22",
              border: "2px solid #2a2d38",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              opacity: interpolate(enter, [0, 1], [0, 1]),
              transform: `translateY(${interpolate(enter, [0, 1], [120, 0])}px) rotate(${interpolate(enter, [0, 1], [-4, 0])}deg)`,
            }}
          >
            <div style={{ color: accent, fontSize: 34 }}>{num}</div>
            <div>
              <div style={{ color: INK, fontSize: 58, fontWeight: 900, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 18 }}>
                {name}
              </div>
              <div style={{ color: "#9a9cab", fontSize: 34, lineHeight: 1.3 }}>{role}</div>
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

export const Demo: React.FC<DemoProps> = (props) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const volume = interpolate(frame, [0, 20, durationInFrames - 30, durationInFrames], [0, 0.8, 0.8, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: GROUND }}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={SCENE}>
          <TitleScene {...props} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={slide({ direction: "from-right" })} timing={springTiming({ durationInFrames: TRANSITION, config: { damping: 200 } })} />
        <TransitionSeries.Sequence durationInFrames={SCENE}>
          <StackScene {...props} />
        </TransitionSeries.Sequence>
      </TransitionSeries>
      <Audio src={staticFile("pad.mp3")} volume={volume} />
    </AbsoluteFill>
  );
};
