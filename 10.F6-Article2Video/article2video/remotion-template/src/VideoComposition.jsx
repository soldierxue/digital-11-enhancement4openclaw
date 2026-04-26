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
const AVATAR_FPS = 30; // source animation fps

function AnimatedPresenter({height, style = {}}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  // Map video frame to avatar frame, respecting source fps
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

/* ── Ken Burns with alternating directions (landscape) ── */
function KenBurnsImage({src, durationFrames, index}) {
  const frame = useCurrentFrame();
  const {width: compW, height: compH} = useVideoConfig();
  const progress = frame / durationFrames;

  const imgAspect = 16 / 9;

  // Ken Burns via explicit pixel positioning — NO CSS transform.
  // Min zoom 1.02 to avoid sub-pixel gaps from float precision.
  const dirs = [
    {zf: 1.02, zt: 1.10, panXf: 0.50, panXt: 0.35, panYf: 0.50, panYt: 0.40},
    {zf: 1.08, zt: 1.02, panXf: 0.35, panXt: 0.60, panYf: 0.40, panYt: 0.55},
    {zf: 1.02, zt: 1.08, panXf: 0.60, panXt: 0.40, panYf: 0.55, panYt: 0.40},
    {zf: 1.06, zt: 1.02, panXf: 0.40, panXt: 0.60, panYf: 0.50, panYt: 0.40},
    {zf: 1.02, zt: 1.06, panXf: 0.55, panXt: 0.35, panYf: 0.45, panYt: 0.55},
  ];
  const d = dirs[index % dirs.length];
  const zoom = interpolate(progress, [0, 1], [d.zf, d.zt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const panX = interpolate(progress, [0, 1], [d.panXf, d.panXt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const panY = interpolate(progress, [0, 1], [d.panYf, d.panYt], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // Cover baseline
  const containerAspect = compW / compH;
  let baseW, baseH;
  if (imgAspect > containerAspect) {
    baseH = compH;
    baseW = Math.ceil(baseH * imgAspect);
  } else {
    baseW = compW;
    baseH = Math.ceil(baseW / imgAspect);
  }

  const imgW = Math.ceil(baseW * zoom);
  const imgH = Math.ceil(baseH * zoom);
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
        rgba(10,14,39,${opacity * 0.8}) 0%,
        rgba(10,14,39,${opacity}) 25%,
        rgba(10,14,39,${opacity}) 75%,
        rgba(10,14,39,${opacity * 0.9}) 100%)`,
    }} />
  );
}

/* ── Font family constant ── */
const FONT_FAMILY = '"Noto Sans CJK SC","Noto Sans SC","Microsoft YaHei",sans-serif';

/* ── Title Card (first slide) ── */
function TitleCard({title, subtitle, localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.2, fps * 1.0], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const slideUp = interpolate(localFrame, [fps * 0.2, fps * 1.0], [30, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const presenterSlide = interpolate(localFrame, [fps * 0.5, fps * 1.3], [60, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const presenterFade = interpolate(localFrame, [fps * 0.5, fps * 1.3], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const displaySubtitle = subtitle || '';

  return (
    <div style={{
      position: 'absolute', inset: 0,
      background: 'linear-gradient(135deg, #0a0e27 0%, #0d1340 30%, #131852 60%, #0a0e27 100%)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        position: 'absolute', top: '10%', left: '15%',
        width: 400, height: 400, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(34,211,238,0.06) 0%, transparent 70%)',
      }} />
      <div style={{
        position: 'absolute', bottom: '20%', right: '20%',
        width: 300, height: 300, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(0,212,255,0.04) 0%, transparent 70%)',
      }} />

      <div style={{
        opacity: Math.min(fadeIn, fadeOut),
        transform: `translateY(${slideUp}px)`,
        position: 'absolute',
        left: 80,
        top: '50%',
        marginTop: -290,
      }}>
        <div style={{
          width: 880, height: 560,
          transform: 'rotate(-1.5deg)',
          position: 'relative',
        }}>
          <div style={{
            position: 'absolute', inset: -3,
            borderRadius: 18,
            background: 'linear-gradient(135deg, rgba(34,211,238,0.5), rgba(0,150,255,0.3), rgba(34,211,238,0.5))',
            boxShadow: '0 0 30px rgba(34,211,238,0.2), 0 0 60px rgba(0,150,255,0.1)',
          }} />
          <div style={{
            position: 'absolute', inset: 0,
            borderRadius: 16,
            background: 'linear-gradient(145deg, rgba(240,243,248,0.95) 0%, rgba(225,230,240,0.92) 100%)',
            display: 'flex', flexDirection: 'column',
            justifyContent: 'center', alignItems: 'center',
            padding: '50px 60px',
            overflow: 'hidden',
          }}>
            {[
              {top: 12, left: 12}, {top: 12, right: 12},
              {bottom: 12, left: 12}, {bottom: 12, right: 12},
            ].map((pos, pi) => (
              <div key={pi} style={{
                position: 'absolute', ...pos,
                width: 8, height: 8, borderRadius: '50%',
                background: 'rgba(34,211,238,0.7)',
                boxShadow: '0 0 8px rgba(34,211,238,0.5)',
              }} />
            ))}

            <h1 style={{
              fontSize: 62, fontWeight: 900, color: '#1a1a2e',
              lineHeight: 1.2, textAlign: 'center',
              fontFamily: FONT_FAMILY, margin: 0,
              maxWidth: '100%',
            }}>
              {title}
            </h1>

            {displaySubtitle && (
              <p style={{
                fontSize: 36, color: '#4a5568', marginTop: 24,
                textAlign: 'center', fontFamily: FONT_FAMILY,
                fontWeight: 500,
              }}>
                {displaySubtitle}
              </p>
            )}

            <div style={{
              width: 100, height: 3, borderRadius: 2,
              background: 'linear-gradient(to right, #22d3ee, #3b82f6)',
              marginTop: 32,
            }} />

            <div style={{
              fontSize: 26, color: '#64748b', marginTop: 28,
              fontFamily: FONT_FAMILY, fontWeight: 500,
              letterSpacing: 2,
            }}>
              薛以致用 · AI 洞察
            </div>
          </div>
        </div>
      </div>

      <div style={{
        position: 'absolute',
        right: 40,
        bottom: 0,
        opacity: Math.min(presenterFade, fadeOut),
        transform: `translateX(${presenterSlide}px)`,
      }}>
        <AnimatedPresenter height={750} />
      </div>
    </div>
  );
}

/* ── Ending Card (last slide) ── */
function EndingCard({title, localFrame, fps, durationFrames}) {
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
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        position: 'absolute', top: '30%', left: '40%',
        width: 500, height: 500, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(34,211,238,0.08) 0%, transparent 70%)',
      }} />

      <div style={{
        opacity: Math.min(fadeIn, fadeOut),
        transform: `scale(${scaleIn})`,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <h1 style={{
          fontSize: 72, fontWeight: 900, color: '#fff',
          textAlign: 'center', fontFamily: FONT_FAMILY,
          textShadow: '0 3px 16px rgba(0,0,0,0.9)',
          margin: 0,
        }}>
          {title || '感谢观看'}
        </h1>

        <div style={{
          width: 80, height: 3, borderRadius: 2,
          background: 'linear-gradient(to right, #22d3ee, #00e676)',
          marginTop: 32,
        }} />

        <div style={{
          fontSize: 28, color: 'rgba(255,255,255,0.5)',
          marginTop: 28, fontFamily: FONT_FAMILY,
          letterSpacing: 2,
        }}>
          薛以致用 · AI 洞察
        </div>
      </div>

      <div style={{
        position: 'absolute',
        right: 60,
        bottom: 0,
        opacity: Math.min(fadeIn, fadeOut) * 0.85,
      }}>
        <AnimatedPresenter height={500} />
      </div>
    </div>
  );
}

/* ── Content slide title (top area, for slides 2..N-1) ── */
function SlideTitle({title, slideIndex, totalSlides, localFrame, fps, durationFrames}) {
  const fadeIn = interpolate(localFrame, [fps * 0.3, fps * 1.0], [0, 1], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const fadeOut = interpolate(localFrame, [durationFrames - fps * 0.5, durationFrames], [1, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  const slideDown = interpolate(localFrame, [fps * 0.3, fps * 1.0], [-15, 0], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0,
      padding: '56px 64px 0',
      opacity: Math.min(fadeIn, fadeOut),
      transform: `translateY(${slideDown}px)`,
    }}>
      <div style={{
        display: 'inline-block',
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
        fontSize: 54, fontWeight: 900, color: '#fff',
        lineHeight: 1.2,
        textShadow: '0 3px 12px rgba(0,0,0,0.9), 0 0 30px rgba(0,0,0,0.4)',
        fontFamily: FONT_FAMILY, margin: 0,
        maxWidth: '75%',
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
   StructuredContent — data-driven visual overlays
   ══════════════════════════════════════════════════════════ */

const CARD_BG = 'rgba(10,14,39,0.75)';
const CARD_RADIUS = 16;
const CARD_BLUR = 'none';

function cardStyle(extra) {
  return {
    background: CARD_BG,
    borderRadius: CARD_RADIUS,
    padding: '20px 24px',
    ...extra,
  };
}

/* stats: big number cards */
function StatsCards({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'flex', gap: 28, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({flex: 1, textAlign: 'center', border: `2px solid ${it.color}40`}),
        }}>
          <div style={{
            fontSize: 52, fontWeight: 900, lineHeight: 1,
            color: it.color,
            textShadow: `0 0 20px ${it.color}40`,
            fontFamily: FONT_FAMILY,
          }}>
            {it.value}
          </div>
          <div style={{
            fontSize: 18, fontWeight: 600, color: '#fff',
            marginTop: 10, fontFamily: FONT_FAMILY,
          }}>
            {it.label}
          </div>
        </div>
      ))}
    </div>
  );
}

/* list: icon list with left colored border */
function IconList({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'flex', flexDirection: 'column', gap: 16, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({display: 'flex', alignItems: 'center', gap: 16, borderLeft: `4px solid ${it.color}`}),
        }}>
          <div style={{fontSize: 32, flexShrink: 0}}>{it.icon}</div>
          <div>
            <div style={{fontSize: 20, fontWeight: 700, color: it.color, fontFamily: FONT_FAMILY}}>
              {it.title}
            </div>
            <div style={{fontSize: 16, color: 'rgba(255,255,255,0.85)', lineHeight: 1.5, fontFamily: FONT_FAMILY}}>
              {it.desc}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* comparison: left vs right columns */
function ComparisonView({items, fadeIn, slideUpPx}) {
  if (!items) return null;
  return (
    <div style={{display: 'flex', gap: 24, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {/* Left column */}
      <div style={{flex: 1, ...cardStyle({border: '2px solid rgba(251,146,60,0.3)'})}}>
        <div style={{fontSize: 20, fontWeight: 700, color: '#fb923c', marginBottom: 16, fontFamily: FONT_FAMILY, textAlign: 'center'}}>
          {items.left_title}
        </div>
        {(items.left_items || []).map((it, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12}}>
            <span style={{fontSize: 22}}>{it.icon}</span>
            <span style={{fontSize: 17, color: 'rgba(255,255,255,0.85)', fontFamily: FONT_FAMILY}}>{it.text}</span>
          </div>
        ))}
      </div>
      {/* Right column */}
      <div style={{flex: 1, ...cardStyle({border: '2px solid rgba(74,222,128,0.3)'})}}>
        <div style={{fontSize: 20, fontWeight: 700, color: '#4ade80', marginBottom: 16, fontFamily: FONT_FAMILY, textAlign: 'center'}}>
          {items.right_title}
        </div>
        {(items.right_items || []).map((it, i) => (
          <div key={i} style={{display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12}}>
            <span style={{fontSize: 22}}>{it.icon}</span>
            <span style={{fontSize: 17, color: 'rgba(255,255,255,0.85)', fontFamily: FONT_FAMILY}}>{it.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* quote: big quote block */
function QuoteBlock({items, fadeIn, slideUpPx}) {
  if (!items) return null;
  return (
    <div style={{opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      <div style={{
        ...cardStyle({border: '2px solid rgba(192,132,252,0.3)', borderLeft: '4px solid #c084fc', padding: '28px 32px'}),
      }}>
        <div style={{fontSize: 42, color: 'rgba(192,132,252,0.4)', marginBottom: -12, fontFamily: 'serif'}}>"</div>
        <div style={{fontSize: 24, color: '#fff', lineHeight: 1.6, fontStyle: 'italic', fontFamily: FONT_FAMILY}}>
          {items.text}
        </div>
        {items.source && (
          <div style={{fontSize: 16, color: 'rgba(255,255,255,0.5)', marginTop: 12, fontFamily: FONT_FAMILY}}>
            — {items.source}
          </div>
        )}
      </div>
    </div>
  );
}

/* grid: 2x2 grid */
function GridView({items, fadeIn, slideUpPx}) {
  return (
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, opacity: fadeIn, transform: `translateY(${slideUpPx}px)`}}>
      {(items || []).slice(0, 4).map((it, i) => (
        <div key={i} style={{
          ...cardStyle({border: `2px solid ${it.color}40`}),
        }}>
          <div style={{fontSize: 20, fontWeight: 700, color: it.color, fontFamily: FONT_FAMILY}}>
            {it.icon} {it.title}
          </div>
          <div style={{fontSize: 16, color: 'rgba(255,255,255,0.85)', lineHeight: 1.5, marginTop: 8, fontFamily: FONT_FAMILY}}>
            {it.desc}
          </div>
        </div>
      ))}
    </div>
  );
}

/* Main dispatcher */
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
      top: 220,
      left: 64,
      right: 340,
      bottom: 120,
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
      right: 20,
      bottom: 50,
      opacity: Math.min(fadeIn, fadeOut),
    }}>
      <AnimatedPresenter height={380} />
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
      position: 'absolute', bottom: 50, left: '50%', transform: 'translateX(-50%)',
      maxWidth: '85%', padding: '12px 32px',
      background: 'rgba(0,0,0,0.8)', borderRadius: 10,
      border: '1px solid rgba(0,212,255,0.15)',
    }}>
      <div style={{
        color: 'white', fontSize: 30, textAlign: 'center', lineHeight: 1.5,
        textShadow: '0 1px 3px rgba(0,0,0,0.5)',
        fontFamily: FONT_FAMILY,
      }}>
        {currentText}
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
      position: 'absolute', top: 16, right: 24,
      color: 'rgba(255,255,255,0.25)', fontSize: 14,
      fontFamily: FONT_FAMILY,
    }}>
      {brandText}
    </div>
  );
}

/* ── Progress bar (bottom 3px) ── */
function ProgressBar({frame, totalFrames}) {
  return (
    <div style={{
      position: 'absolute', bottom: 0, left: 0, height: 3,
      background: 'linear-gradient(to right, #00d4ff, #00e676)',
      width: `${(frame / totalFrames) * 100}%`,
      boxShadow: '0 0 8px rgba(0,212,255,0.5)',
    }} />
  );
}

/* ── Main Landscape Composition ── */
export function VideoComposition() {
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
              <TitleCard
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
              <EndingCard
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
            <KenBurnsImage src={staticFile(slide.image)} durationFrames={dur} index={i} />
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
