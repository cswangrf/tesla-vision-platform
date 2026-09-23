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
  // React 只管理容器 div；<video> 元素由 video.js 动态创建/销毁，
  // 避免 video.js dispose 时移除 React 持有的 DOM 节点导致 removeChild 冲突
  const mainContainerRef = useRef<HTMLDivElement | null>(null);
  const thumbContainerRefs = useRef<Record<string, HTMLDivElement | null>>({});

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

  // 初始化主视频播放器：动态创建 <video> 元素挂到容器中
  const initMainPlayer = useCallback((view: string) => {
    const container = mainContainerRef.current;
    if (!container || !clip) return;

    if (mainPlayerRef.current) {
      mainPlayerRef.current.dispose();
      mainPlayerRef.current = null;
    }

    const el = document.createElement('video');
    el.className = 'video-js vjs-default-skin';
    el.style.width = '100%';
    el.style.height = '100%';
    container.replaceChildren(el);

    const videoId = clip.views[view];
    const src = videoId ? getVideoStreamUrl(videoId) : '';

    mainPlayerRef.current = videojs(el, {
      controls: true,
      fill: true,
      autoplay: false,
      preload: 'auto',
      sources: src ? [{ src, type: 'video/mp4' }] : [],
    });
  }, [clip]);

  // 初始化 4 个缩略视频播放器（同样动态创建 <video> 元素）
  const initThumbPlayers = useCallback(() => {
    if (!clip) return;

    let loadedCount = 0;
    VIEWS.forEach((view) => {
      const container = thumbContainerRefs.current[view];
      if (!container) return;

      if (thumbPlayersRef.current[view]) {
        thumbPlayersRef.current[view].dispose();
      }

      const videoId = clip.views[view];
      const src = videoId ? getVideoStreamUrl(videoId) : '';

      const el = document.createElement('video');
      el.className = 'video-js vjs-default-skin';
      el.style.width = '100%';
      el.style.height = '100%';
      container.replaceChildren(el);

      const player = videojs(
        el,
        {
          controls: false,  // 缩略图不显示控件
          fill: true,
          autoplay: false,
          preload: 'auto',
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

  // 剪辑变化：销毁旧播放器（video.js 会自行清理它创建的 <video> 元素），
  // 并在容器中重新创建全部播放器
  useEffect(() => {
    if (!clip) return;

    initThumbPlayers();
    initMainPlayer(mainView);

    return () => {
      disposeAll();
    };
  }, [clip]); // eslint-disable-line react-hooks/exhaustive-deps

  // 切换主视图：重建主播放器（首次初始化已由上面的 effect 完成，避免重复初始化）
  const prevMainViewRef = useRef(mainView);
  useEffect(() => {
    if (!clip) return;
    if (prevMainViewRef.current !== mainView) {
      initMainPlayer(mainView);
    }
    prevMainViewRef.current = mainView;
  }, [mainView, clip]); // eslint-disable-line react-hooks/exhaustive-deps

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

    const onPlay = () => {
      VIEWS.forEach((v) => {
        const p = thumbPlayersRef.current[v];
        if (p && p.paused()) {
          p.play();
        }
      });
    };

    const onPause = () => {
      VIEWS.forEach((v) => {
        const p = thumbPlayersRef.current[v];
        if (p && !p.paused()) {
          p.pause();
        }
      });
    };

    mainPlayer.on('timeupdate', onTimeUpdate);
    mainPlayer.on('play', onPlay);
    mainPlayer.on('pause', onPause);

    return () => {
      mainPlayer.off('timeupdate', onTimeUpdate);
      mainPlayer.off('play', onPlay);
      mainPlayer.off('pause', onPause);
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
        <div
          ref={(el) => { mainContainerRef.current = el; }}
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
              <div
                ref={(el) => { thumbContainerRefs.current[view] = el; }}
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
