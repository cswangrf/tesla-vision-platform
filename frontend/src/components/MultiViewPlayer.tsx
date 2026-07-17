import React, { useRef, useState, useEffect, useCallback } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';

const VIEWS = ['front', 'back', 'left_repeater', 'right_repeater'] as const;

interface MultiViewPlayerProps {
  baseUrl: string;
}

const MultiViewPlayer: React.FC<MultiViewPlayerProps> = ({ baseUrl }) => {
  const playersRef = useRef<Record<string, any>>({});
  const [mainView, setMainView] = useState<string>('front');
  const [isReady, setIsReady] = useState(false);

  // 初始化播放器
  const initPlayers = useCallback(() => {
    VIEWS.forEach((view) => {
      const el = document.getElementById(`video-${view}`);
      if (!el) return;

      // 销毁已存在的播放器
      if (playersRef.current[view]) {
        playersRef.current[view].dispose();
      }

      const player = videojs(
        `video-${view}`,
        {
          controls: true,
          fluid: true,
          autoplay: false,
          preload: 'auto',
          sources: [
            {
              src: `${baseUrl}/stream/${view}`,
              type: 'video/mp4',
            },
          ],
        },
        () => {
          if (view === VIEWS[VIEWS.length - 1]) {
            setIsReady(true);
          }
        }
      );

      playersRef.current[view] = player;
    });
  }, [baseUrl]);

  useEffect(() => {
    initPlayers();

    return () => {
      // 清理所有播放器
      VIEWS.forEach((view) => {
        if (playersRef.current[view]) {
          playersRef.current[view].dispose();
        }
      });
    };
  }, [initPlayers]);

  // 同步播放器
  useEffect(() => {
    if (!isReady) return;

    const mainPlayer = playersRef.current[mainView];
    if (!mainPlayer) return;

    const onTimeUpdate = () => {
      const currentTime = mainPlayer.currentTime();
      VIEWS.forEach((v) => {
        const p = playersRef.current[v];
        if (v !== mainView && p && Math.abs(p.currentTime() - currentTime) > 0.5) {
          p.currentTime(currentTime);
        }
      });
    };

    mainPlayer.on('timeupdate', onTimeUpdate);
    mainPlayer.on('play', () => {
      VIEWS.forEach((v) => {
        if (v !== mainView && playersRef.current[v]) {
          playersRef.current[v].play();
        }
      });
    });
    mainPlayer.on('pause', () => {
      VIEWS.forEach((v) => {
        if (v !== mainView && playersRef.current[v]) {
          playersRef.current[v].pause();
        }
      });
    });

    return () => {
      mainPlayer.off('timeupdate', onTimeUpdate);
    };
  }, [mainView, isReady]);

  // 网格布局
  const otherViews = VIEWS.filter((v) => v !== mainView);

  return (
    <div style={{ padding: 16, height: '100%' }}>
      <div
        className="player-grid"
        style={{
          display: 'grid',
          gridTemplateAreas: `
            "${mainView} ${mainView}"
            "${otherViews[0] || 'none1'} ${otherViews[1] || 'none2'}"
            "${otherViews[2] || 'none3'} none4"
          `,
          gridTemplateColumns: '1fr 1fr',
          gridTemplateRows: mainView ? '2fr 1fr 1fr' : '1fr 1fr',
          gap: 8,
          height: '100%',
          maxHeight: 'calc(100vh - 100px)',
        }}
      >
        {VIEWS.map((view) => (
          <div
            key={view}
            onClick={() => setMainView(view)}
            style={{
              gridArea: view,
              position: 'relative',
              border: view === mainView ? '2px solid #1890ff' : '1px solid #d9d9d9',
              borderRadius: 4,
              overflow: 'hidden',
              cursor: 'pointer',
              background: '#000',
              transition: 'all 0.3s ease',
            }}
          >
            <div
              style={{
                position: 'absolute',
                top: 8,
                left: 8,
                zIndex: 10,
                background: 'rgba(0,0,0,0.6)',
                color: '#fff',
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              {view.replace('_', ' ').toUpperCase()}
            </div>
            <video
              id={`video-${view}`}
              className="video-js vjs-default-skin"
              style={{ width: '100%', height: '100%' }}
            />
          </div>
        ))}
      </div>
    </div>
  );
};

export default MultiViewPlayer;
