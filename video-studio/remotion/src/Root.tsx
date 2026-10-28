import "@fontsource/inter/400.css";
import "@fontsource/inter/900.css";
import { Composition } from "remotion";
import { Demo, demoSchemaDefaults, DEMO_DURATION } from "./Demo";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Demo"
        component={Demo}
        durationInFrames={DEMO_DURATION}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={demoSchemaDefaults}
      />
      <Composition
        id="DemoVertical"
        component={Demo}
        durationInFrames={DEMO_DURATION}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={demoSchemaDefaults}
      />
    </>
  );
};
