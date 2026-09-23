import React, { useState, useEffect, useCallback } from 'react';
import { List, Typography, Button, message, Spin, Tag, Space, Tooltip, Popconfirm } from 'antd';
import { UploadOutlined, ReloadOutlined, PlayCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import { getVideos, deleteVideo } from '../services/api';
import type { VideoMetadata } from '../services/api';
import MultiViewPlayer, { type VideoClip } from './MultiViewPlayer';
import VideoUploadModal from './VideoUploadModal';

const { Text, Title } = Typography;

// 视角标签映射
const VIEW_LABELS: Record<string, string> = {
  front: '前视',
  back: '后视',
  left_repeater: '左后',
  right_repeater: '右后',
};

/**
 * 将扁平的视频列表按 (device_id, timestamp) 聚合为 VideoClip。
 */
function groupVideosIntoClips(videos: VideoMetadata[]): VideoClip[] {
  const clipMap = new Map<string, VideoClip>();

  for (const v of videos) {
    const key = `${v.device_id}|${v.timestamp}`;
    if (!clipMap.has(key)) {
      clipMap.set(key, {
        device_id: v.device_id,
        timestamp: v.timestamp,
        views: {},
      });
    }
    clipMap.get(key)!.views[v.camera_view] = v.video_id;
  }

  // 按时间戳降序排列（最新的在前）
  return Array.from(clipMap.values()).sort((a, b) =>
    b.timestamp.localeCompare(a.timestamp)
  );
}

const VideoBrowser: React.FC = () => {
  const [clips, setClips] = useState<VideoClip[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedClip, setSelectedClip] = useState<VideoClip | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  // 加载视频列表
  const fetchVideos = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getVideos(1, 500);
      const grouped = groupVideosIntoClips(res.videos || []);
      setClips(grouped);
      // 自动选中第一个（如果当前无选中或选中的已不在列表中）
      if (grouped.length > 0) {
        setSelectedClip((prev) => {
          if (!prev) return grouped[0];
          const stillExists = grouped.some(
            (c) => c.device_id === prev.device_id && c.timestamp === prev.timestamp
          );
          return stillExists ? prev : grouped[0];
        });
      } else {
        setSelectedClip(null);
      }
    } catch (err: any) {
      message.error('加载视频列表失败: ' + (err?.message || '网络错误'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  // 删除片段（含该片段全部视角的视频文件）
  const handleDeleteClip = useCallback(
    async (clip: VideoClip) => {
      const videoIds = Object.values(clip.views);
      try {
        await Promise.all(videoIds.map((id) => deleteVideo(id)));
        message.success(`已删除片段 ${clip.device_id}（${videoIds.length} 个视角）`);
        // 若删除的是当前播放的片段，清除选中状态
        setSelectedClip((prev) => {
          if (
            prev &&
            prev.device_id === clip.device_id &&
            prev.timestamp === clip.timestamp
          ) {
            return null;
          }
          return prev;
        });
        fetchVideos();
      } catch (err: any) {
        message.error(`删除失败: ${err?.message || '未知错误'}`);
      }
    },
    [fetchVideos]
  );

  return (
    <div style={{ display: 'flex', height: '100%', minHeight: 0 }}>
      {/* ======== 左侧面板：视频片段列表 ======== */}
      <div
        style={{
          width: 300,
          minWidth: 260,
          borderRight: '1px solid #e8e8e8',
          background: '#fafafa',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* 标题栏 */}
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid #e8e8e8',
            background: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Title level={5} style={{ margin: 0 }}>
            视频片段
          </Title>
          <Tooltip title="刷新列表">
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={fetchVideos}
              loading={loading}
            />
          </Tooltip>
        </div>

        {/* 上传区域 */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e8e8e8', background: '#fff' }}>
          <Button
            icon={<UploadOutlined />}
            block
            onClick={() => setUploadOpen(true)}
          >
            上传 Tesla 视频
          </Button>
          <Text type="secondary" style={{ fontSize: 11, display: 'block', marginTop: 6 }}>
            支持同时上传多个视角，系统会自动按时间戳分组
          </Text>
        </div>

        {/* 片段列表 */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading && clips.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin tip="加载中..." />
            </div>
          ) : clips.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Text type="secondary">暂无视频，请先上传</Text>
            </div>
          ) : (
            <List
              dataSource={clips}
              split={false}
              renderItem={(clip) => {
                const viewCount = Object.keys(clip.views).length;
                const isActive =
                  selectedClip?.device_id === clip.device_id &&
                  selectedClip?.timestamp === clip.timestamp;

                return (
                  <List.Item
                    onClick={() => setSelectedClip(clip)}
                    style={{
                      padding: '10px 16px',
                      cursor: 'pointer',
                      background: isActive ? '#e6f7ff' : 'transparent',
                      borderLeft: isActive ? '3px solid #1890ff' : '3px solid transparent',
                      transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive)
                        (e.currentTarget as HTMLElement).style.background = '#f5f5f5';
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive)
                        (e.currentTarget as HTMLElement).style.background = 'transparent';
                    }}
                  >
                    <div style={{ width: '100%' }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Space size={4}>
                          <PlayCircleOutlined
                            style={{ color: isActive ? '#1890ff' : '#999', fontSize: 16 }}
                          />
                          <Text
                            strong
                            style={{
                              fontSize: 13,
                              color: isActive ? '#1890ff' : undefined,
                            }}
                          >
                            {clip.device_id}
                          </Text>
                        </Space>
                        <Space size={4}>
                          <Tag color={viewCount >= 4 ? 'green' : 'orange'}>
                            {viewCount} 视角
                          </Tag>
                          <Popconfirm
                            title="删除该片段？"
                            description={`将删除 ${viewCount} 个视角的视频文件，不可恢复`}
                            okText="删除"
                            cancelText="取消"
                            okButtonProps={{ danger: true }}
                            onConfirm={() => handleDeleteClip(clip)}
                          >
                            <Button
                              size="small"
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={(e) => e.stopPropagation()}
                              title="删除片段"
                            />
                          </Popconfirm>
                        </Space>
                      </div>
                      <Text
                        type="secondary"
                        style={{ fontSize: 11, display: 'block', marginTop: 2 }}
                      >
                        {clip.timestamp}
                      </Text>
                      <div style={{ marginTop: 4 }}>
                        {['front', 'back', 'left_repeater', 'right_repeater'].map((view) => (
                          <Tag
                            key={view}
                            color={clip.views[view] ? 'blue' : 'default'}
                            style={{ fontSize: 10, marginBottom: 2 }}
                          >
                            {VIEW_LABELS[view] || view}
                          </Tag>
                        ))}
                      </div>
                    </div>
                  </List.Item>
                );
              }}
            />
          )}
        </div>
      </div>

      {/* ======== 右侧主区域：多视角播放器 ======== */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <MultiViewPlayer clip={selectedClip} />
      </div>

      {/* 上传弹窗 */}
      <VideoUploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={fetchVideos}
      />
    </div>
  );
};

export default VideoBrowser;
