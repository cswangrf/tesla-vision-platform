import React, { useRef, useState, useEffect, useCallback } from 'react';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import { Empty, Typography } from 'antd';
import { getVideoStreamUrl } from '../services/api';

const { Text } = Typography;

// 视角顺序：前/后 第一行，左/右 repeater 第二行
const VIEWS = ['front', 'back', 'left_repeater', 'right_repeater'] as const;

// 视角显示标签
const VIEW_LABELS: Record<string, string> = {
  front: '前视 (FRONT)',
  back: '后视 (BACK)',
  left_repeater: '左后 (LEFT)',
  right_repeater: '右后 (RIGHT)',
};

export interface VideoClip {
  device_id: string;
  timestamp: string;
  views: Record<string, string>; // view -> video_id
}

interface MultiViewPlayerProps {
  clip: VideoClip | null;
}

const MultiViewPlayer: React.FC<MultiViewPlayerProps> = ({ clip }) => {
  // 缩略视频的 4 个播放器实例
  const thumbPlayersRef = useRef<Record<string, any>>({});
  // 主视频播放器实例
  const mainPlayerRef = useRef<any>(null);
  const [mainView, setMainView] = useState<string>('front');
  const [isReady, setIsReady] = useState(false);

  // 销毁所有播放器
  const disposeAll = useCallback(() => {
    if (mainPlayerRef.current) {
      mainPlayerRef.current.dispose();
      mainPlayerRef.current = null;
    }
    VIEWS.forEach((view) => {
      if (thumbPlayersRef.current[view]) {
        thumbPlayersRef.current[view].dispose();
        delete thumbPlayersRef.current[view];
      }
    });
    setIsReady(false);
  }, []);

  // 初始化主视频播放器
  const initMainPlayer = useCallback((view: string) => {
    const el = document.getElementById('video-player-main');
    if (!el || !clip) return;

    if (mainPlayerRef.current) {
      mainPlayerRef.current.dispose();
      mainPlayerRef.current = null;
    }

    const videoId = clip.views[view];
    const src = videoId ? getVideoStreamUrl(videoId) : '';

    mainPlayerRef.current = videojs(
      'video-player-main',
      {
        controls: true,
        fluid: true,
        autoplay: false,
        preload: 'auto',
        aspectRatio: '4:3',
        sources: src ? [{ src, type: 'video/mp4' }] : [],
      }
    );
  }, [clip]);

  // 初始化 4 个缩略视频播放器
  const initThumbPlayers = useCallback(() => {
    if (!clip) return;

    let loadedCount = 0;
    VIEWS.forEach((view) => {
      const el = document.getElementById(`video-thumb-${view}`);
      if (!el) return;

      if (thumbPlayersRef.current[view]) {
        thumbPlayersRef.current[view].dispose();
      }

      const videoId = clip.views[view];
      const src = videoId ? getVideoStreamUrl(videoId) : '';

      const player = videojs(
        `video-thumb-${view}`,
        {
          controls: false,  // 缩略图不显示控件
          fluid: true,
          autoplay: false,
          preload: 'auto',
          aspectRatio: '4:3',
          sources: src ? [{ src, type: 'video/mp4' }] : [],
        },
        () => {
          loadedCount++;
          if (loadedCount >= VIEWS.length) {
            setIsReady(true);
          }
        }
      );

      thumbPlayersRef.current[view] = player;
    });
  }, [clip]);

  useEffect(() => {
    disposeAll();

    if (clip) {
      // 先初始化缩略图播放器，再初始化主播放器
      const timer = setTimeout(() => {
        initThumbPlayers();
        initMainPlayer(mainView);
      }, 100);

      return () => {
        clearTimeout(timer);
        disposeAll();
      };
    }
  }, [clip]); // eslint-disable-line react-hooks/exhaustive-deps

  // 切换主视图时重建主播放器
  useEffect(() => {
    if (clip && isReady) {
      initMainPlayer(mainView);
    }
  }, [mainView]); // eslint-disable-line react-hooks/exhaustive-deps

  // 同步播放：主播放器控制所有缩略播放器
  useEffect(() => {
    if (!isReady) return;

    const mainPlayer = mainPlayerRef.current;
    if (!mainPlayer) return;

    const onTimeUpdate = () => {
      const currentTime = mainPlayer.currentTime();
      VIEWS.forEach((v) => {
        const p = thumbPlayersRef.current[v];
        if (p && Math.abs(p.currentTime() - currentTime) > 0.5) {
          p.currentTime(currentTime);
        }
      });
    };

    mainPlayer.on('timeupdate', onTimeUpdate);
    mainPlayer.on('play', () => {
      VIEWS.forEach((v) => {
        if (thumbPlayersRef.current[v]) {
          thumbPlayersRef.current[v].play();
        }
      });
    });
    mainPlayer.on('pause', () => {
      VIEWS.forEach((v) => {
        if (thumbPlayersRef.current[v]) {
          thumbPlayersRef.current[v].pause();
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

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      gap: 8,
      padding: 12,
    }}>
      {/* 信息栏 */}
      <div style={{
        padding: '4px 12px',
        background: '#fff',
        borderRadius: 6,
        border: '1px solid #e8e8e8',
        display: 'flex',
        alignItems: 'center',
        flexShrink: 0,
      }}>
        <Text strong>当前播放：</Text>
        <Text code style={{ marginLeft: 8 }}>{clip.device_id}</Text>
        <Text type="secondary" style={{ marginLeft: 8 }}>{clip.timestamp}</Text>
      </div>

      {/* 主视频 */}
      <div style={{
        flex: 1,
        minHeight: 0,
        borderRadius: 6,
        border: '2px solid #1890ff',
        overflow: 'hidden',
        background: '#000',
        position: 'relative',
      }}>
        <div style={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 10,
          background: 'rgba(24, 144, 255, 0.85)',
          color: '#fff',
          padding: '2px 10px',
          borderRadius: 4,
          fontSize: 14,
          fontWeight: 600,
          pointerEvents: 'none',
        }}>
          {VIEW_LABELS[mainView] || mainView}
        </div>
        <video
          id="video-player-main"
          className="video-js vjs-default-skin"
          style={{ width: '100%', height: '100%' }}
        />
      </div>

      {/* 4 个小视频缩略图：2 行 × 2 列 */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gridTemplateRows: '1fr 1fr',
        gap: 6,
        flexShrink: 0,
        height: '35%',
        minHeight: 120,
      }}>
        {VIEWS.map((view) => {
          const isActive = view === mainView;
          return (
            <div
              key={view}
              onClick={() => setMainView(view)}
              style={{
                borderRadius: 4,
                border: isActive ? '2px solid #1890ff' : '1px solid #555',
                overflow: 'hidden',
                cursor: 'pointer',
                background: '#000',
                position: 'relative',
                opacity: isActive ? 0.55 : 1,
                transition: 'all 0.2s ease',
              }}
              title={`点击将此视角切换为主视图`}
            >
              <div style={{
                position: 'absolute',
                top: 4,
                left: 4,
                zIndex: 10,
                background: isActive ? 'rgba(24, 144, 255, 0.8)' : 'rgba(0, 0, 0, 0.55)',
                color: '#fff',
                padding: '1px 6px',
                borderRadius: 3,
                fontSize: 11,
                pointerEvents: 'none',
              }}>
                {VIEW_LABELS[view] || view}
                {isActive ? ' ✓' : ''}
              </div>
              <video
                id={`video-thumb-${view}`}
                className="video-js vjs-default-skin"
                style={{ width: '100%', height: '100%' }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default MultiViewPlayer;
