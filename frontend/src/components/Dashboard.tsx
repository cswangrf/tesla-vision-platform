import React, { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Button, Spin, Empty, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getStats, StatsSummary } from '../services/api';

const { Title, Text } = Typography;

// 顺序色阶（蓝，550→250）：横向条形图按数量从大到小取深→浅（量值编码）
const BLUE_RAMP = ['#1c5cab', '#2a78d6', '#5598e7', '#6da7ec', '#86b6ef'];
// 墨色（图表文字始终用墨色，不用系列色）
const INK_PRIMARY = '#0b0b0b';
const INK_SECONDARY = '#52514e';
const INK_MUTED = '#898781';
// 轨道 / 分隔线（发丝线）
const TRACK_COLOR = 'rgba(193, 194, 183, 0.35)';
const HAIRLINE = 'rgba(225, 224, 217, 0.8)';

const formatBytes = (bytes: number): string => {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
};

/** KPI 数字块（hero number，不是图表） */
const StatTile: React.FC<{ label: string; value: string | number; hint?: string }> = ({
  label, value, hint,
}) => (
  <div
    style={{
      background: '#fff',
      border: '1px solid #e8e8e8',
      borderRadius: 8,
      padding: '16px 20px',
    }}
  >
    <div
      style={{
        fontSize: 28,
        fontWeight: 600,
        lineHeight: 1.2,
        color: INK_PRIMARY,
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {value}
    </div>
    <div style={{ marginTop: 6, fontSize: 13, color: INK_SECONDARY }}>{label}</div>
    {hint && <div style={{ marginTop: 2, fontSize: 12, color: INK_MUTED }}>{hint}</div>}
  </div>
);

/** 横向条形图：名称在左、细条 + 4px 圆角、值直接标注、行悬停高亮 */
const DistributionBars: React.FC<{ data: Record<string, number>; emptyText: string }> = ({
  data, emptyText,
}) => {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  const max = entries.length > 0 ? entries[0][1] : 1;

  if (entries.length === 0) {
    return (
      <div style={{ padding: '32px 0', textAlign: 'center' }}>
        <Text type="secondary">{emptyText}</Text>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 4 }}>
      {entries.map(([name, count], idx) => {
        const ratio = max > 0 ? count / max : 0;
        const color = BLUE_RAMP[Math.min(idx, BLUE_RAMP.length - 1)];
        return (
          <div
            key={name}
            title={`${name}: ${count}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '4px 8px',
              borderRadius: 6,
              cursor: 'default',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(0, 0, 0, 0.04)'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
          >
            <Text
              style={{
                width: 96,
                flexShrink: 0,
                color: INK_PRIMARY,
                fontSize: 13,
                textAlign: 'right',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {name}
            </Text>
            <div style={{ flex: 1, height: 18, position: 'relative' }}>
              {/* 轨道（发丝线，帮助读取量值） */}
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  background: TRACK_COLOR,
                  borderRadius: 4,
                }}
              />
              {/* 数据条 */}
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${Math.max(ratio * 100, count > 0 ? 2.5 : 0)}%`,
                  background: color,
                  borderRadius: 4,
                }}
              />
            </div>
            <Text
              style={{
                width: 56,
                flexShrink: 0,
                color: INK_SECONDARY,
                fontSize: 13,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {count}
            </Text>
          </div>
        );
      })}
    </div>
  );
};

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<StatsSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStats();
      setStats(data);
    } catch (err: any) {
      setError(err?.message || '加载看板数据失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    // 每 30 秒自动刷新（标注处理进度会随时间变化）
    const timer = setInterval(fetchStats, 30000);
    return () => clearInterval(timer);
  }, [fetchStats]);

  const videos = stats?.videos;
  const ann = stats?.annotations ?? {};
  const matchedVideos = ann.matched_videos ?? [];

  return (
    <div style={{ padding: 24, maxWidth: 1100, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>数据看板</Title>
        <Button icon={<ReloadOutlined />} onClick={fetchStats} loading={loading}>
          刷新
        </Button>
      </div>

      {loading && !stats ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin tip="加载看板数据..." />
        </div>
      ) : error ? (
        <Card>
          <Text type="danger">{error}</Text>
        </Card>
      ) : (
        <>
          {/* KPI 行：核心数字用数字块而非图表 */}
          <Row gutter={16}>
            <Col span={6}>
              <StatTile
                label="视频片段"
                value={videos?.clips ?? '-'}
                hint={`${(videos?.devices ?? []).length} 台设备`}
              />
            </Col>
            <Col span={6}>
              <StatTile
                label="视频文件（视角）"
                value={videos?.total_files ?? '-'}
                hint={videos ? `共 ${formatBytes(videos.total_size_bytes)}` : undefined}
              />
            </Col>
            <Col span={6}>
              <StatTile
                label="已标注帧数"
                value={ann.total_frames ?? '-'}
                hint={
                  ann.matched_frames !== undefined && ann.matched_frames !== ann.total_frames
                    ? `匹配 ${ann.matched_frames} 帧`
                    : undefined
                }
              />
            </Col>
            <Col span={6}>
              <StatTile
                label="已标注视频"
                value={matchedVideos.length}
                hint={stats ? `共提交任务 ${stats.tasks?.total ?? 0} 个` : undefined}
              />
            </Col>
          </Row>

          {/* 分布图：横向条形 + 单色顺序色阶（量值比较） */}
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={12}>
              <Card size="small" title="检测目标分布">
                <DistributionBars
                  data={ann.object_distribution ?? {}}
                  emptyText="暂无检测目标数据，请先上传视频并完成标注"
                />
              </Card>
            </Col>
            <Col span={12}>
              <Card size="small" title="场景标签分布">
                <DistributionBars
                  data={ann.tag_distribution ?? {}}
                  emptyText="暂无场景标签数据，请先上传视频并完成标注"
                />
              </Card>
            </Col>
          </Row>

          {/* 已标注视频列表：超过 7 类用表格（此处为明细列表） */}
          <Card size="small" title="已标注视频" style={{ marginTop: 16 }}>
            {matchedVideos.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无标注数据"
                style={{ padding: '24px 0' }}
              />
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${HAIRLINE}` }}>
                    {['视频 ID', '内容日期', '上传日期', '标注帧数'].map((h, i) => (
                      <th
                        key={h}
                        style={{
                          textAlign: i === 3 ? 'right' : 'left',
                          padding: '6px 8px',
                          fontSize: 12,
                          fontWeight: 500,
                          color: INK_SECONDARY,
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {matchedVideos.map((v) => (
                    <tr key={v.video_id} style={{ borderBottom: `1px solid ${TRACK_COLOR}` }}>
                      <td style={{ padding: '8px', fontSize: 13 }}>
                        <Text code>{v.video_id}</Text>
                      </td>
                      <td style={{ padding: '8px', fontSize: 13, color: INK_SECONDARY }}>{v.date}</td>
                      <td style={{ padding: '8px', fontSize: 13, color: INK_SECONDARY }}>{v.uploaded_date}</td>
                      <td
                        style={{
                          padding: '8px',
                          fontSize: 13,
                          color: INK_PRIMARY,
                          textAlign: 'right',
                          fontVariantNumeric: 'tabular-nums',
                        }}
                      >
                        {v.matched_frames}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </>
      )}
    </div>
  );
};

export default Dashboard;
