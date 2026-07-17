import React, { useRef, useState, useEffect, useCallback } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import { Empty, Typography } from 'antd';
import { getVideoStreamUrl } from '../services/api';

const { Text } = Typography;

const VIEWS = ['front', 'back', 'left_repeater', 'right_repeater'] as const;

export interface VideoClip {
  device_id: string;
  timestamp: string;
  views: Record<string, string>; // view -> video_id
}

interface MultiViewPlayerProps {
  clip: VideoClip | null;
}

const MultiViewPlayer: React.FC<MultiViewPlayerProps> = ({ clip }) => {
  const playersRef = useRef<Record<string, any>>({});
  const [mainView, setMainView] = useState<string>('front');
  const [isReady, setIsReady] = useState(false);

  // 初始化播放器
  const initPlayers = useCallback(() => {
    if (!clip) return;

    VIEWS.forEach((view) => {
      const el = document.getElementById(`video-${view}`);
      if (!el) return;

      // 销毁已存在的播放器
      if (playersRef.current[view]) {
        playersRef.current[view].dispose();
      }

      const videoId = clip.views[view];
      const src = videoId ? getVideoStreamUrl(videoId) : '';

      const player = videojs(
        `video-${view}`,
        {
          controls: true,
          fluid: true,
          autoplay: false,
          preload: 'auto',
          sources: src
            ? [{ src, type: 'video/mp4' }]
            : [],
        },
        () => {
          if (view === VIEWS[VIEWS.length - 1]) {
            setIsReady(true);
          }
        }
      );

      playersRef.current[view] = player;
    });
  }, [clip]);

  useEffect(() => {
    // 先清理旧播放器
    VIEWS.forEach((view) => {
      if (playersRef.current[view]) {
        playersRef.current[view].dispose();
        delete playersRef.current[view];
      }
    });
    setIsReady(false);

    if (clip) {
      // 延迟初始化，确保 DOM 已存在
      const timer = setTimeout(() => initPlayers(), 100);
      return () => {
        clearTimeout(timer);
        VIEWS.forEach((view) => {
          if (playersRef.current[view]) {
            playersRef.current[view].dispose();
          }
        });
      };
    }
  }, [clip, initPlayers]);

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

  // 无视频时显示空状态
  if (!clip) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100%',
          minHeight: 400,
          background: '#f0f2f5',
          borderRadius: 8,
          margin: 16,
        }}
      >
        <Empty
          description={
            <span>
              暂无视频数据<br />
              <Text type="secondary">请先上传 Tesla 视频或从列表中选择一个视频片段</Text>
            </span>
          }
        />
      </div>
    );
  }

  // 网格布局
  const otherViews = VIEWS.filter((v) => v !== mainView);

  return (
    <div style={{ padding: 16, height: '100%' }}>
      <div
        style={{
          marginBottom: 12,
          padding: '8px 12px',
          background: '#fff',
          borderRadius: 6,
          border: '1px solid #e8e8e8',
        }}
      >
        <Text strong>当前播放：</Text>
        <Text code style={{ marginLeft: 8 }}>
          {clip.device_id}
        </Text>
        <Text type="secondary" style={{ marginLeft: 8 }}>
          {clip.timestamp}
        </Text>
      </div>
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
          maxHeight: 'calc(100vh - 150px)',
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
