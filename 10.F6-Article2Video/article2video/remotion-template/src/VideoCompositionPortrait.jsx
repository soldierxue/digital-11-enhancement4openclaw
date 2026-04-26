import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  staticFile,
} from 'remotion';
import data from '../public/data.json';

/* ── Animated Presenter (looping PNG sequence) ── */
const AVATAR_TOTAL_FRAMES = data.avatarFrames || 302;
const AVATAR_FPS = 30;

function AnimatedPresenter({height, style = {}}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const avatarFrame = Math.floor((frame / fps) * AVATAR_FPS) % AVATAR_TOTAL_FRAMES;
  const padded = String(avatarFrame).padStart(4, '0');
  return (
    <Img
      src={staticFile(`avatar/frame-${padded}.png`)}
      style={{
        height,
        objectFit: 'contain',
        filter: 'drop-shadow(0 4px 20px rgba(0,0,0,0.5))',
        ...style,
      }}
    />
  );
}

/* ── Ken Burns with alternating directions (portrait-optimized) ── */
function KenBurnsImage({src, durationFrames, index}) {
  const frame = useCurrentFrame();
  const {width: compW, height: compH} = useVideoConfig();
  const progress = frame / durationFrames;

  // Ken Burns via explicit pixel positioning — NO CSS transform.
  // For 16:9 source in 9:16 container, cover = match height, overflow width.
  // Zoom is achieved by scaling the image dimensions above the cover baseline.
  // Pan is achieved by shifting top/left pixel offsets.
  const imgAspect = 16 / 9;

  const dirs = [
    {zf: 1.02, zt: 1.08, panXf: 0.50, panXt: 0.48, panYf: 0.50, panYt: 0.48},
    {zf: 1.06, zt: 1.02, panXf: 0.48, panXt: 0.52, panYf: 0.48, panYt: 0.52},
    {zf: 1.02, zt: 1.06, panXf: 0.52, panXt: 0.48, panYf: 0.52, panYt: 0.48},
    {zf: 1.05, zt: 1.02, panXf: 0.48, panXt: 0.52, panYf: 0.49, panYt: 0.51},
    {zf: 1.02, zt: 1.05, panXf: 0.51, panXt: 0.48, panYf: 0.48, panYt: 0.52},
  ];
  const d = dirs[index % dirs.length];
  const zoom = interpolate(progress, [0, 1], [d.zf, d.zt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const panX = interpolate(progress, [0, 1], [d.panXf, d.panXt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const panY = interpolate(progress, [0, 1], [d.panYf, d.panYt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // Cover baseline: match container height, width overflows
  const baseH = compH;
  const baseW = Math.ceil(baseH * imgAspect);

  // Apply zoom — use ceil to ensure image always >= container
  const imgW = Math.ceil(baseW * zoom);
  const imgH = Math.ceil(baseH * zoom);

  // Pan offset — use floor for negative values to ensure full coverage
  const overflowX = imgW - compW;
  const overflowY = imgH - compH;
  const left = Math.floor(-(overflowX * panX));
  const top = Math.floor(-(overflowY * panY));

  return (
    <div style={{position: 'absolute', top: 0, left: 0, width: compW, height: compH, overflow: 'hidden'}}>
      <Img src={src} style={{
        position: 'absolute',
        top,
        left,
        width: imgW,
        height: imgH,
      }} />
    </div>
  );
}

/* ── Dark gradient overlay ── */
function DarkOverlay({opacity = 0.55}) {
  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: `linear-gradient(180deg,
        rgba(10,14,39,${opacity * 0.7}) 0%,
        rgba(10,14,39,${opacity * 0.4}) 30%,
        rgba(10,14,39,${opacity * 0.4}) 55%,
        rgba(10,14,39,${opacity * 0.9}) 75%,
        rgba(10,14,39,${opacity}) 100%)`,
    }} />
  );
}

/* ── Font family constant ── */
const FONT_FAMILY = '"Noto Sans CJK SC","Noto Sans SC","Microsoft YaHei",sans-serif';

/* ── Title Card (first slide - portrait) ── */
function TitleCardPortrait({title, subtitle, localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.2, fps * 1.0], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const slideUp = interpolate(localFrame, [fps * 0.2, fps * 1.0], [30, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const presenterSlide = interpolate(localFrame, [fps * 0.5, fps * 1.3], [80, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const presenterFade = interpolate(localFrame, [fps * 0.5, fps * 1.3], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #131852 60%, #0a0e27 100%)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'flex-start',
    }}>
      <div style={{
        position: 'absolute', top: '5%', left: '20%',
        width: 300, height: 300, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(34,211,238,0.06) 0%, transparent 70%)',
      }} />

      <div style={{
        opacity: Math.min(fadeIn, fadeOut),
        transform: `translateY(${slideUp}px)`,
        marginTop: 100,
        position: 'relative',
      }}>
        <div style={{
          width: 620, height: 400,
          transform: 'rotate(-1.5deg)',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', inset: -3,
            borderRadius: 16,
            background: 'linear-gradient(135deg, rgba(34,211,238,0.5), rgba(0,150,255,0.3), rgba(34,211,238,0.5))',
            boxShadow: '0 0 25px rgba(34,211,238,0.2), 0 0 50px rgba(0,150,255,0.1)',
          }} />
          <div style={{
            position: 'absolute', inset: 0,
            borderRadius: 14,
            background: 'linear-gradient(145deg, rgba(240,243,248,0.95) 0%, rgba(225,230,240,0.92) 100%)',
            display: 'flex', flexDirection: 'column',
            justifyContent: 'center', alignItems: 'center',
            padding: '36px 40px',
            overflow: 'hidden',
          }}>
            {[
              {top: 10, left: 10}, {top: 10, right: 10},
              {bottom: 10, left: 10}, {bottom: 10, right: 10},
            ].map((pos, pi) => (
              <div key={pi} style={{
                position: 'absolute', ...pos,
                width: 6, height: 6, borderRadius: '50%',
                background: 'rgba(34,211,238,0.7)',
                boxShadow: '0 0 6px rgba(34,211,238,0.5)',
              }} />
            ))}

            <h1 style={{
              fontSize: 48, fontWeight: 900, color: '#1a1a2e',
              lineHeight: 1.25, textAlign: 'center',
              fontFamily: FONT_FAMILY, margin: 0,
            }}>
              {title}
            </h1>

            {subtitle && (
              <p style={{
                fontSize: 30, color: '#4a5568', marginTop: 16,
                textAlign: 'center', fontFamily: FONT_FAMILY,
              }}>
                {subtitle}
              </p>
            )}

            <div style={{
              width: 80, height: 3, borderRadius: 2,
              background: 'linear-gradient(to right, #22d3ee, #3b82f6)',
              marginTop: 24,
            }} />

            <div style={{
              fontSize: 22, color: '#64748b', marginTop: 20,
              fontFamily: FONT_FAMILY, letterSpacing: 2,
            }}>
              薛以致用 · AI 洞察
            </div>
          </div>
        </div>
      </div>

      <div style={{
        position: 'absolute',
        bottom: 0,
        right: 20,
        opacity: Math.min(presenterFade, fadeOut),
        transform: `translateY(${presenterSlide}px)`,
      }}>
        <AnimatedPresenter height={550} />
      </div>
    </div>
  );
}

/* ── Ending Card (last slide - portrait) ── */
function EndingCardPortrait({title, localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.2, fps * 1.0], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const scaleIn = interpolate(localFrame, [fps * 0.2, fps * 1.0], [0.95, 1.0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #131852 60%, #0a0e27 100%)',
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        position: 'absolute', top: '30%', left: '30%',
        width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)',
      }} />

      <div style={{
        opacity: Math.min(fadeIn, fadeOut),
        transform: `scale(${scaleIn})`,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center',
        marginBottom: 200,
      }}>
        <h1 style={{
          fontSize: 56, fontWeight: 900, color: '#fff',
          textAlign: 'center', fontFamily: FONT_FAMILY,
          textShadow: '0 3px 16px rgba(0,0,0,0.9)',
          margin: 0, padding: '0 40px',
        }}>
          {title || '感谢观看'}
        </h1>

        <div style={{
          width: 70, height: 3, borderRadius: 2,
          background: 'linear-gradient(to right, #22d3ee, #00e676)',
          marginTop: 28,
        }} />

        <div style={{
          fontSize: 24, color: 'rgba(255,255,255,0.5)',
          marginTop: 24, fontFamily: FONT_FAMILY,
          letterSpacing: 2,
        }}>
          薛以致用 · AI 洞察
        </div>
      </div>

      <div style={{
        position: 'absolute', bottom: 0, right: 10,
        opacity: Math.min(fadeIn, fadeOut) * 0.85,
      }}>
        <AnimatedPresenter height={420} />
      </div>
    </div>
  );
}

/* ── Slide Title (top area for content slides) ── */
function SlideTitle({title, slideIndex, totalSlides, localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.2, fps * 0.8], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const slideDown = interpolate(localFrame, [fps * 0.2, fps * 0.8], [-15, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute',
      top: 0, left: 0, right: 0,
      padding: '60px 36px 30px',
      opacity: Math.min(fadeIn, fadeOut),
      transform: `translateY(${slideDown}px)`,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center',
    }}>
      <div style={{
        background: 'rgba(34,211,238,0.15)',
        border: '1px solid rgba(34,211,238,0.4)',
        borderRadius: 20, padding: '4px 16px',
        marginBottom: 16,
        color: '#67e8f9', fontSize: 16, fontWeight: 600,
        fontFamily: FONT_FAMILY,
      }}>
        {slideIndex + 1} / {totalSlides}
      </div>

      <h1 style={{
        fontSize: 42, fontWeight: 900, color: '#fff',
        lineHeight: 1.25, textAlign: 'center',
        textShadow: '0 3px 12px rgba(0,0,0,0.9), 0 0 30px rgba(0,0,0,0.4)',
        fontFamily: FONT_FAMILY,
        margin: 0, padding: '0 8px',
      }}>
        {title}
      </h1>

      <div style={{
        width: 60, height: 3, borderRadius: 2,
        background: 'linear-gradient(to right, #00d4ff, #00e676)',
        marginTop: 20, opacity: 0.7,
      }} />
    </div>
  );
}

/* ══════════════════════════════════════════════════════════
   StructuredContent — portrait version
   ══════════════════════════════════════════════════════════ */

const CARD_BG = 'rgba(10,14,39,0.75)';
const CARD_RADIUS = 16;
const CARD_BLUR = 'none';

function cardStyle(extra) {
  return {
    background: CARD_BG,
    borderRadius: CARD_RADIUS,
    padding: '16px 20px',
    ...extra,
  };
}

function StatsCards({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 16, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({display: 'flex', alignItems: 'center', gap: 16, border: `2px solid ${it.color}40`}),
        }}>
          <div style={{
            fontSize: 42, fontWeight: 900, lineHeight: 1,
            color: it.color,
            textShadow: `0 0 20px ${it.color}40`,
            fontFamily: FONT_FAMILY,
            flexShrink: 0,
            minWidth: 140,
            textAlign: 'center',
          }}>
            {it.value}
          </div>
          <div style={{
            fontSize: 18, fontWeight: 600, color: '#fff',
            fontFamily: FONT_FAMILY,
          }}>
            {it.label}
          </div>
        </div>
      ))}
    </div>
  );
}

function IconList({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 12, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({display: 'flex', alignItems: 'center', gap: 14, borderLeft: `4px solid ${it.color}`}),
        }}>
          <div style={{fontSize: 28, flexShrink: 0}}>{it.icon}</div>
          <div>
            <div style={{fontSize: 18, fontWeight: 700, color: it.color, fontFamily: FONT_FAMILY}}>
              {it.title}
            </div>
            <div style={{fontSize: 15, color: 'rgba(255,255,255,0.85)', lineHeight: 1.4, fontFamily: FONT_FAMILY}}>
              {it.desc}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ComparisonView({items, fadeIn, slideUpPx}) {
  if (!items) return null;
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 16, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      <div style={{...cardStyle({border: '2px solid rgba(251,146,60,0.3)'})}}>
        <div style={{fontSize: 18, fontWeight: 700, color: '#fb923c', marginBottom: 12, fontFamily: FONT_FAMILY, textAlign: 'center'}}>
          {items.left_title}
        </div>
        {(items.left_items || []).map((it, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8}}>
            <span style={{fontSize: 20}}>{it.icon}</span>
            <span style={{fontSize: 16, color: 'rgba(255,255,255,0.85)', fontFamily: FONT_FAMILY}}>{it.text}</span>
          </div>
        ))}
      </div>
      <div style={{...cardStyle({border: '2px solid rgba(74,222,128,0.3)'})}}>
        <div style={{fontSize: 18, fontWeight: 700, color: '#4ade80', marginBottom: 12, fontFamily: FONT_FAMILY, textAlign: 'center'}}>
          {items.right_title}
        </div>
        {(items.right_items || []).map((it, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8}}>
            <span style={{fontSize: 20}}>{it.icon}</span>
            <span style={{fontSize: 16, color: 'rgba(255,255,255,0.85)', fontFamily: FONT_FAMILY}}>{it.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function QuoteBlock({items, fadeIn, slideUpPx}) {
  if (!items) return null;
  return (
    <div style={{opacity: fadeIn, transform: `translateY(${slideUpPx}px)`, width: '100%'}}>
      <div style={{
        ...cardStyle({border: '2px solid rgba(192,132,252,0.3)', borderLeft: '4px solid #c084fc', padding: '24px 28px'}),
      }}>
        <div style={{fontSize: 36, color: 'rgba(192,132,252,0.4)', marginBottom: -10, fontFamily: 'serif'}}>"</div>
        <div style={{fontSize: 22, color: '#fff', lineHeight: 1.6, fontStyle: 'italic', fontFamily: FONT_FAMILY}}>
          {items.text}
        </div>
        {items.source && (
          <div style={{fontSize: 15, color: 'rgba(255,255,255,0.5)', marginTop: 10, fontFamily: FONT_FAMILY}}>
            — {items.source}
          </div>
        )}
      </div>
    </div>
  );
}

function GridView({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).slice(0, 4).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({border: `2px solid ${it.color}40`}),
        }}>
          <div style={{fontSize: 18, fontWeight: 700, color: it.color, fontFamily: FONT_FAMILY}}>
            {it.icon} {it.title}
          </div>
          <div style={{fontSize: 14, color: 'rgba(255,255,255,0.85)', lineHeight: 1.4, marginTop: 6, fontFamily: FONT_FAMILY}}>
            {it.desc}
          </div>
        </div>
      ))}
    </div>
  );
}

function StructuredContent({keyFacts, localFrame, fps, durationFrames}) {
  if (!keyFacts) return null;

  const fadeIn = interpolate(localFrame, [fps * 0.8, fps * 1.5], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const slideUpPx = interpolate(localFrame, [fps * 0.8, fps * 1.5], [25, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const combinedFade = Math.min(fadeIn, fadeOut);

  const content = (() => {
    switch (keyFacts.type) {
      case 'stats': return <StatsCards items={keyFacts.items} fadeIn={combinedFade} slideUpPx={slideUpPx} />;
      case 'list': return <IconList items={keyFacts.items} fadeIn={combinedFade} slideUpPx={slideUpPx} />;
      case 'comparison': return <ComparisonView items={keyFacts.items} fadeIn={combinedFade} slideUpPx={slideUpPx} />;
      case 'quote': return <QuoteBlock items={keyFacts.items} fadeIn={combinedFade} slideUpPx={slideUpPx} />;
      case 'grid': return <GridView items={keyFacts.items} fadeIn={combinedFade} slideUpPx={slideUpPx} />;
      default: return null;
    }
  })();

  return (
    <div style={{
      position: 'absolute',
      top: 240,
      left: 28,
      right: 28,
      bottom: 500,
      display: 'flex',
      alignItems: 'flex-start',
    }}>
      {content}
    </div>
  );
}

/* ── Presenter overlay (bottom-right, for content slides) ── */
function PresenterOverlay({localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.5, fps * 1.2], [0, 0.85], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.4, durationFrames], [0.85, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute',
      right: 10,
      bottom: 90,
      opacity: Math.min(fadeIn, fadeOut),
    }}>
      <AnimatedPresenter height={400} />
    </div>
  );
}

/* ── Subtitle bar ── */
function SubtitleBar({subtitles, globalFrame, fps}) {
  const currentTimeMs = (globalFrame / fps) * 1000;
  let currentText = '';
  for (const sub of subtitles) {
    if (currentTimeMs >= sub.fromMs && currentTimeMs <= sub.toMs) {
      currentText = sub.text;
      break;
    }
  }
  if (!currentText) return null;
  return (
    <div style={{
      position: 'absolute',
      bottom: 100,
      left: 24, right: 24,
      display: 'flex', justifyContent: 'center',
    }}>
      <div style={{
        maxWidth: '95%',
        padding: '14px 28px',
        background: 'rgba(0,0,0,0.8)',
        borderRadius: 12,
        border: '1px solid rgba(0,212,255,0.15)',
        border: '1px solid rgba(0,212,255,0.15)',
      }}>
        <div style={{
          color: 'white', fontSize: 36,
          textAlign: 'center', lineHeight: 1.5,
          textShadow: '0 1px 3px rgba(0,0,0,0.5)',
          fontFamily: FONT_FAMILY,
        }}>
          {currentText}
        </div>
      </div>
    </div>
  );
}

/* ── Branding (top-right) ── */
function Branding() {
  const brandText = data.branding || '薛以致用 · AI 洞察';
  if (!brandText) return null;
  return (
    <div style={{
      position: 'absolute', top: 20, right: 20,
      color: 'rgba(255,255,255,0.25)', fontSize: 14,
      fontFamily: FONT_FAMILY,
    }}>
      {brandText}
    </div>
  );
}

/* ── Progress bar ── */
function ProgressBar({frame, totalFrames}) {
  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, height: 4,
      background: 'linear-gradient(to right, #00d4ff, #00e676)',
      width: `${(frame / totalFrames) * 100}%`,
      boxShadow: '0 0 8px rgba(0,212,255,0.5)',
    }} />
  );
}

/* ── Main Portrait Composition ── */
export function VideoCompositionPortrait() {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const FADE = Math.round(fps * 0.5);
  const totalFrames = Math.ceil((data.totalDurationMs / 1000) * fps);
  const totalSlides = data.slides.length;

  return (
    <AbsoluteFill style={{background: '#0a0e27'}}>
      <Audio src={staticFile('full-audio.mp3')} />

      {data.slides.map((slide, i) => {
        const startFrame = Math.round((slide.startMs / 1000) * fps);
        const endFrame = Math.round((slide.endMs / 1000) * fps);
        const dur = endFrame - startFrame;
        const local = frame - startFrame;
        if (local < -FADE || local > dur + FADE) return null;

        const opacity = interpolate(local, [0, FADE, dur - FADE, dur], [0, 1, 1, 0], {
          extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
        });

        const isFirst = i === 0;
        const isLast = i === totalSlides - 1;
        const slideTitle = slide.title || `Slide ${i + 1}`;

        if (isFirst) {
          return (
            <AbsoluteFill key={i} style={{opacity}}>
              <TitleCardPortrait
                title={slideTitle}
                subtitle={slide.subtitle || ''}
                localFrame={local}
                fps={fps}
                durationFrames={dur}
              />
            </AbsoluteFill>
          );
        }

        if (isLast) {
          return (
            <AbsoluteFill key={i} style={{opacity}}>
              <EndingCardPortrait
                title={slideTitle}
                localFrame={local}
                fps={fps}
                durationFrames={dur}
              />
            </AbsoluteFill>
          );
        }

        return (
          <AbsoluteFill key={i} style={{opacity}}>
            <KenBurnsImage
              src={staticFile(slide.image)}
              durationFrames={dur}
              index={i}
            />
            <DarkOverlay opacity={0.55} />
            <SlideTitle
              title={slideTitle}
              slideIndex={i}
              totalSlides={totalSlides}
              localFrame={local}
              fps={fps}
              durationFrames={dur}
            />
            <StructuredContent
              keyFacts={slide.key_facts}
              localFrame={local}
              fps={fps}
              durationFrames={dur}
            />
            <PresenterOverlay
              localFrame={local}
              fps={fps}
              durationFrames={dur}
            />
          </AbsoluteFill>
        );
      })}

      <SubtitleBar subtitles={data.subtitles} globalFrame={frame} fps={fps} />
      <Branding />
      <ProgressBar frame={frame} totalFrames={totalFrames} />
    </AbsoluteFill>
  );
}
