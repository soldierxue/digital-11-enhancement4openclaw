import {Composition, staticFile} from 'remotion';
import {VideoComposition} from './VideoComposition';
import {VideoCompositionPortrait} from './VideoCompositionPortrait';
import data from '../public/data.json';

export const RemotionRoot = () => {
  const fps = data.fps;
  const totalFrames = Math.ceil((data.totalDurationMs / 1000) * fps);

  return (
    <>
      <Composition
        id="AgentVideo"
        component={VideoComposition}
        durationInFrames={totalFrames}
        fps={fps}
        width={data.width}
        height={data.height}
      />
      <Composition
        id="AgentVideoPortrait"
        component={VideoCompositionPortrait}
        durationInFrames={totalFrames}
        fps={fps}
        width={720}
        height={1280}
      />
    </>
  );
};
