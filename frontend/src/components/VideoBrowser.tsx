import React, { useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Space, Tag, Typography, message, Spin, Card,
} from 'antd';
import {
  UploadOutlined, ReloadOutlined, PlayCircleOutlined,
  DeleteOutlined, VideoCameraOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import MultiViewPlayer, { VideoClip } from './MultiViewPlayer';
import VideoUploadModal from './VideoUploadModal';
import { getVideos, deleteVideo, VideoMetadata } from '../services/api';

const { Text, Title } = Typography;

// 将视频列表按 device_id + timestamp 分组成 VideoClip
function groupVideosIntoClips(videos: VideoMetadata[]): Map<string, VideoClip> {
  const clips = new Map<string, VideoClip>();

  videos.forEach((v) => {
    // timestamp 可能是字符串或 Date，统一处理
    const ts = typeof v.timestamp === 'string'
      ? v.timestamp
      : new Date(v.timestamp).toISOString().replace(/T/, '_').replace(/:/g, '-').slice(0, 19);

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

  const pageSize = 20;

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
      // 如果当前正在播放被删除的视频，清除选择
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
            onClick={() => setSelectedClipKey(record.key)}
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 播放器区域 */}
      <div style={{ flex: '0 0 auto', minHeight: 300, maxHeight: '60%' }}>
        <MultiViewPlayer clip={selectedClip} />
      </div>

      {/* 视频列表 */}
      <Card
        size="small"
        style={{ flex: 1, margin: '0 16px 16px', overflow: 'auto' }}
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
