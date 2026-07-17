import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Space, Tag, Typography, message, Card,
} from 'antd';
import {
  UploadOutlined, ReloadOutlined, PlayCircleOutlined,
  DeleteOutlined, VideoCameraOutlined, UpOutlined, DownOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import MultiViewPlayer, { VideoClip } from './MultiViewPlayer';
import VideoUploadModal from './VideoUploadModal';
import { getVideos, deleteVideo, VideoMetadata } from '../services/api';

const { Text } = Typography;

// 将视频列表按 device_id + timestamp 分组成 VideoClip
function groupVideosIntoClips(videos: VideoMetadata[]): Map<string, VideoClip> {
  const clips = new Map<string, VideoClip>();

  videos.forEach((v) => {
    // timestamp 可能是字符串或 Date，统一归一化为 YYYY-MM-DD_HH-MM-SS 格式
    let ts: string;
    if (typeof v.timestamp === 'string') {
      ts = v.timestamp
        .replace(/\.\d+/, '')      // strip microseconds (.816450)
        .replace(/Z$/, '')          // strip trailing Z
        .replace('T', '_')          // 2024-06-05_11:41:22
        .replace(/:/g, '-')         // 2024-06-05_11-41-22
        .slice(0, 19);
    } else {
      ts = new Date(v.timestamp).toISOString().replace(/T/, '_').replace(/:/g, '-').slice(0, 19);
    }

    const key = `${v.device_id}__${ts}`;

    if (!clips.has(key)) {
      clips.set(key, {
        device_id: v.device_id,
        timestamp: ts,
        views: {},
      });
    }
    const clip = clips.get(key)!;
    clip.views[v.camera_view] = v.video_id;
  });

  return clips;
}

const VideoBrowser: React.FC = () => {
  const [videos, setVideos] = useState<VideoMetadata[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedClipKey, setSelectedClipKey] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  // 面板展开/折叠状态：有选中片段时默认折叠
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  const pageSize = 20;
  const isPlaying = selectedClipKey !== null;

  // 选中/取消播放时自动折叠/展开面板
  useEffect(() => {
    if (isPlaying) {
      // 短暂延迟后自动折叠，让用户先看到播放器
      const timer = setTimeout(() => setPanelCollapsed(true), 1500);
      return () => clearTimeout(timer);
    } else {
      setPanelCollapsed(false);
    }
  }, [isPlaying, selectedClipKey]);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getVideos(page, pageSize);
      setVideos(data.videos);
      setTotal(data.total);
    } catch (err) {
      message.error('获取视频列表失败');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  const handleDelete = async (videoId: string) => {
    try {
      await deleteVideo(videoId);
      message.success('视频已删除');
      const clips = groupVideosIntoClips(videos);
      for (const [key, clip] of clips) {
        if (Object.values(clip.views).includes(videoId) && key === selectedClipKey) {
          setSelectedClipKey(null);
          break;
        }
      }
      fetchVideos();
    } catch {
      message.error('删除失败');
    }
  };

  const handleSelectClip = (key: string) => {
    if (selectedClipKey === key) {
      // 再次点击已选中的：停止播放
      setSelectedClipKey(null);
    } else {
      setSelectedClipKey(key);
    }
  };

  const clips = groupVideosIntoClips(videos);
  const selectedClip = selectedClipKey ? clips.get(selectedClipKey) || null : null;

  // 将 clips 转为表格数据
  const clipList = Array.from(clips.entries()).map(([key, clip]) => ({
    key,
    ...clip,
    viewCount: Object.keys(clip.views).length,
  }));

  const columns: ColumnsType<typeof clipList[0]> = [
    {
      title: '设备 ID',
      dataIndex: 'device_id',
      key: 'device_id',
      render: (text: string) => <Text code>{text}</Text>,
    },
    {
      title: '时间戳',
      dataIndex: 'timestamp',
      key: 'timestamp',
      render: (text: string) => <Text>{text.replace('_', ' ')}</Text>,
    },
    {
      title: '视角数',
      dataIndex: 'viewCount',
      key: 'viewCount',
      width: 80,
      render: (count: number) => (
        <Tag color={count >= 4 ? 'green' : 'orange'}>
          {count}/4
        </Tag>
      ),
    },
    {
      title: '可用视角',
      key: 'views',
      render: (_, record) => (
        <Space size={4} wrap>
          {Object.keys(record.views).map((view) => (
            <Tag key={view} color="blue" style={{ margin: 0 }}>
              {view.replace('_', ' ')}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_, record) => (
        <Space>
          <Button
            type={selectedClipKey === record.key ? 'primary' : 'default'}
            size="small"
            icon={<PlayCircleOutlined />}
            onClick={() => handleSelectClip(record.key)}
          >
            {selectedClipKey === record.key ? '播放中' : '播放'}
          </Button>
          <Button
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => {
              Object.values(record.views).forEach((vid) => handleDelete(vid));
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  // 面板折叠时的拖拽手柄高度
  const HANDLE_HEIGHT = 36;

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
      position: 'relative',
    }}>
      {/* 播放器区域 */}
      <div style={{
        flex: 1,
        minHeight: 0,
        overflow: 'hidden',
      }}>
        <MultiViewPlayer clip={selectedClip} />
      </div>

      {/* 视频列表面板 — 播放时自动折叠到底部 */}
      <div style={{
        position: 'relative',
        flexShrink: 0,
        height: panelCollapsed ? HANDLE_HEIGHT : 'auto',
        maxHeight: panelCollapsed ? HANDLE_HEIGHT : '45%',
        transition: 'height 0.35s cubic-bezier(0.4, 0, 0.2, 1), max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1)',
        overflow: 'hidden',
      }}>
        {/* 拖拽手柄 — 始终可见 */}
        <div
          onClick={() => setPanelCollapsed(!panelCollapsed)}
          style={{
            height: HANDLE_HEIGHT,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(180deg, #fafafa 0%, #f0f0f0 100%)',
            borderTop: '1px solid #d9d9d9',
            borderBottom: panelCollapsed ? '1px solid #d9d9d9' : 'none',
            borderRadius: panelCollapsed ? '8px 8px 0 0' : 0,
            cursor: 'pointer',
            userSelect: 'none',
            flexShrink: 0,
          }}
          title={panelCollapsed ? '点击展开视频列表' : '点击收起视频列表'}
        >
          {panelCollapsed ? (
            <Space size={4}>
              <UpOutlined style={{ fontSize: 12, color: '#1890ff' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                视频列表
              </Text>
              <Tag color="blue" style={{ margin: 0, fontSize: 11, lineHeight: '16px' }}>
                {total} 个文件
              </Tag>
              <UpOutlined style={{ fontSize: 12, color: '#1890ff' }} />
            </Space>
          ) : (
            <DownOutlined style={{ fontSize: 12, color: '#999' }} />
          )}
        </div>

        {/* 面板内容 */}
        <Card
          size="small"
          style={{
            border: 'none',
            borderRadius: 0,
            height: '100%',
            overflow: 'auto',
          }}
          bodyStyle={{ padding: '8px 12px' }}
          title={
            <Space>
              <VideoCameraOutlined />
              <Text strong>视频列表</Text>
              <Tag>{total} 个文件</Tag>
            </Space>
          }
          extra={
            <Space>
              <Button
                type="primary"
                icon={<UploadOutlined />}
                onClick={() => setUploadOpen(true)}
              >
                上传视频
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={fetchVideos}
                loading={loading}
              >
                刷新
              </Button>
            </Space>
          }
        >
          <Table
            columns={columns}
            dataSource={clipList}
            loading={loading}
            size="small"
            pagination={{
              current: page,
              pageSize,
              total,
              onChange: (p) => setPage(p),
              showSizeChanger: false,
              showTotal: (t) => `共 ${t} 个片段`,
            }}
          />
        </Card>
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
