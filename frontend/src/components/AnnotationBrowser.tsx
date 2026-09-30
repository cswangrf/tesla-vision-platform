import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Button, Card, Col, Drawer, Empty, message, Progress, Row, Select, Slider,
  Space, Spin, Table, Tag, Typography,
} from 'antd';
import {
  LeftOutlined, ReloadOutlined, RightOutlined, SearchOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import videojs from 'video.js';
import 'video.js/dist/video-js.css';
import {
  getAnnotationFrameUrl, getAnnotationFrames, getAnnotationOptions,
  searchAnnotations,
} from '../services/api';
import type {
  AnnotationFrameDetail, AnnotationOptions, AnnotationRun,
} from '../services/api';

const { Text, Title } = Typography;

// 视角中文标签
const VIEW_LABELS: Record<string, string> = {
  front: '前视',
  back: '后视',
  left_repeater: '左后',
  right_repeater: '右后',
};

// 检测目标画框色板（按 OBJECT_PROMPTS 词表顺序）
const OBJECT_COLORS: Record<string, string> = {
  '车辆': '#ff4d4f',
  '行人': '#52c41a',
  '交通标志': '#1890ff',
  '红绿灯': '#faad14',
  '障碍物': '#722ed1',
  '自行车': '#13c2c2',
  '摩托车': '#eb2f96',
};
const FALLBACK_COLOR = '#fa8c16';

// ============================================================
// 缩略图（原始视频已删除或加载失败时显示占位）
// ============================================================
const Thumbnail: React.FC<{ run: AnnotationRun }> = ({ run }) => {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [run.thumbnail_url]);

  if (!run.has_raw_video || failed) {
    return (
      <div
        style={{
          width: 120, height: 68, background: '#f0f0f0', borderRadius: 4,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <Text type="secondary" style={{ fontSize: 11 }}>
          {run.has_raw_video ? '加载失败' : '视频已删除'}
        </Text>
      </div>
    );
  }
  return (
    <img
      src={run.thumbnail_url}
      alt="帧缩略图"
      onError={() => setFailed(true)}
      style={{ width: 120, height: 68, objectFit: 'cover', borderRadius: 4 }}
    />
  );
};

// ============================================================
// 视频切片播放器（video.js 命令式创建，React 只持有容器 div）
// ============================================================
const ClipPlayer: React.FC<{
  run: AnnotationRun;
  onReady: (player: any) => void;
  onTimeUpdate: (frameIndex: number) => void;
}> = ({ run, onReady, onTimeUpdate }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const el = document.createElement('video');
    el.className = 'video-js vjs-default-skin';
    el.style.width = '100%';
    el.style.height = '100%';
    container.replaceChildren(el);

    const player = videojs(el, {
      controls: true,
      fill: true,
      autoplay: false,
      preload: 'auto',
      sources: [{ src: run.clip_url, type: 'video/mp4' }],
    });
    player.on('timeupdate', () => {
      // 切片 t=0 对应 run.start_frame，播放时帧面板跟随
      const t = Math.floor((player.currentTime() ?? 0) + run.start_frame);
      onTimeUpdate(Math.min(run.end_frame, Math.max(run.start_frame, t)));
    });
    onReady(player);

    return () => {
      onReady(null);
      player.dispose();
    };
  }, [run.run_id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: 340, background: '#000', borderRadius: 6 }}
    />
  );
};

// ============================================================
// run 详情（Drawer 内容）：播放器 + 逐帧查看（检测框叠加） + 信息面板
// ============================================================
const RunDetail: React.FC<{ run: AnnotationRun }> = ({ run }) => {
  const [frames, setFrames] = useState<AnnotationFrameDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentFrame, setCurrentFrame] = useState(run.start_frame);
  const [imgFailed, setImgFailed] = useState(false);
  const playerApiRef = useRef<any>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  // 打开详情时一次性拉取 run 内逐帧明细
  useEffect(() => {
    setLoading(true);
    getAnnotationFrames(run.video_id, run.start_frame, run.end_frame)
      .then((res) => {
        setFrames(res.frames);
        // 初始定位到代表帧（中位帧）
        setCurrentFrame(
          res.frames.length > 0
            ? res.frames[Math.floor(res.frames.length / 2)].frame_index
            : run.start_frame
        );
      })
      .catch((err: any) => {
        message.error('加载帧明细失败: ' + (err?.message || '网络错误'));
      })
      .finally(() => setLoading(false));
  }, [run.run_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // 换帧时重置图片错误状态
  useEffect(() => {
    setImgFailed(false);
  }, [currentFrame]);

  // 在帧图上绘制检测框（bbox 为原始分辨率坐标，按显示比例缩放）
  const drawBoxes = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas || img.naturalWidth === 0) return;

    const frame = frames.find((f) => f.frame_index === currentFrame);
    const scaleX = img.clientWidth / img.naturalWidth;
    const scaleY = img.clientHeight / img.naturalHeight;
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.max(1, Math.round(img.clientWidth * dpr));
    canvas.height = Math.max(1, Math.round(img.clientHeight * dpr));
    canvas.style.width = `${img.clientWidth}px`;
    canvas.style.height = `${img.clientHeight}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, img.clientWidth, img.clientHeight);
    if (!frame) return;

    for (const o of frame.objects) {
      const b = o.bbox;
      if (!b) continue;
      const color = OBJECT_COLORS[o.class_name] || FALLBACK_COLOR;
      const x = b.x * scaleX;
      const y = b.y * scaleY;
      const w = b.width * scaleX;
      const h = b.height * scaleY;

      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);

      // 框上方标签：类名 + 置信度
      const label = `${o.class_name} ${Math.round(o.confidence * 100)}%`;
      ctx.font = '12px sans-serif';
      const tw = ctx.measureText(label).width;
      ctx.fillStyle = color;
      ctx.fillRect(x, Math.max(0, y - 18), tw + 8, 18);
      ctx.fillStyle = '#fff';
      ctx.fillText(label, x + 4, Math.max(12, y - 5));
    }
  }, [frames, currentFrame]);

  // 帧导航（同步视频播放进度）
  const goFrame = useCallback((f: number) => {
    const clamped = Math.min(run.end_frame, Math.max(run.start_frame, f));
    setCurrentFrame(clamped);
    try {
      playerApiRef.current?.currentTime(clamped - run.start_frame + 0.01);
    } catch {
      // 播放器未就绪时忽略
    }
  }, [run]);

  const frameInfo = frames.find((f) => f.frame_index === currentFrame);
  const showPlayer = run.has_raw_video && run.frame_count > 1;

  return (
    <Spin spinning={loading} tip="加载帧明细...">
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {/* 片段信息栏 */}
        <div
          style={{
            padding: '8px 12px', background: '#fafafa', borderRadius: 6,
            border: '1px solid #e8e8e8',
          }}
        >
          <Space wrap size={12}>
            <Text strong>{run.device_id || '未知设备'}</Text>
            <Tag color="blue">{VIEW_LABELS[run.camera_view] || run.camera_view}</Tag>
            <Text type="secondary">{run.content_date || run.uploaded_date}</Text>
            <Text code>{run.video_id}</Text>
            <Text type="secondary">
              帧 {run.start_frame}–{run.end_frame} · {run.frame_count} 帧 ·{' '}
              {run.end_sec - run.start_sec + 1}s
            </Text>
            {!run.has_raw_video && <Tag color="red">原始视频已删除</Tag>}
          </Space>
        </div>

        {/* 视频切片播放器 */}
        {showPlayer && (
          <ClipPlayer
            run={run}
            onReady={(p) => { playerApiRef.current = p; }}
            onTimeUpdate={(f) => setCurrentFrame(f)}
          />
        )}
        {run.has_raw_video && run.frame_count === 1 && (
          <Text type="secondary">单帧片段（无视频切片）</Text>
        )}
        {!run.has_raw_video && (
          <div
            style={{
              background: '#fafafa', border: '1px dashed #d9d9d9', borderRadius: 6,
              padding: '24px 0', textAlign: 'center',
            }}
          >
            <Text type="secondary">原始视频已删除，无法显示画面与切片</Text>
          </div>
        )}

        <Row gutter={16}>
          {/* 左列：帧图 + 导航 */}
          <Col span={15}>
            <div
              style={{
                display: 'flex', justifyContent: 'center', alignItems: 'center',
                background: '#000', borderRadius: 6, overflow: 'hidden',
                minHeight: 280,
              }}
            >
              {imgFailed || !run.has_raw_video ? (
                <Text type="secondary" style={{ color: '#999', padding: 24 }}>
                  画面不可用
                </Text>
              ) : (
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <img
                    ref={imgRef}
                    src={getAnnotationFrameUrl(run.video_id, currentFrame)}
                    alt={`第 ${currentFrame} 帧`}
                    onLoad={drawBoxes}
                    onError={() => setImgFailed(true)}
                    style={{ display: 'block', maxWidth: '100%', maxHeight: 440 }}
                  />
                  <canvas
                    ref={canvasRef}
                    style={{
                      position: 'absolute', inset: 0,
                      width: '100%', height: '100%', pointerEvents: 'none',
                    }}
                  />
                  <div
                    style={{
                      position: 'absolute', top: 8, left: 8,
                      background: 'rgba(0, 0, 0, 0.6)', color: '#fff',
                      padding: '2px 10px', borderRadius: 4, fontSize: 12,
                    }}
                  >
                    第 {currentFrame} 帧 · t={currentFrame}s
                  </div>
                </div>
              )}
            </div>

            {/* 帧导航 */}
            <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Button
                size="small"
                icon={<LeftOutlined />}
                disabled={currentFrame <= run.start_frame}
                onClick={() => goFrame(currentFrame - 1)}
              />
              <Slider
                style={{ flex: 1, margin: '0 4px' }}
                min={run.start_frame}
                max={run.end_frame}
                step={1}
                value={currentFrame}
                onChange={(v) => goFrame(v as number)}
                tooltip={{ formatter: (v) => `第 ${v} 帧` }}
              />
              <Button
                size="small"
                icon={<RightOutlined />}
                disabled={currentFrame >= run.end_frame}
                onClick={() => goFrame(currentFrame + 1)}
              />
            </div>
            <div style={{ marginTop: 4 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                当前帧: {currentFrame} / {run.frame_count} 帧
              </Text>
            </div>
          </Col>

          {/* 右列：帧信息 + 目标/标签 */}
          <Col span={9}>
            <Card size="small" title="当前帧信息" style={{ marginBottom: 12 }}>
              <Space direction="vertical" size={4}>
                <Text>
                  帧序号: <Text strong>{frameInfo?.frame_index ?? currentFrame}</Text>
                </Text>
                <Text>
                  时间: <Text strong>{frameInfo?.timestamp_sec ?? currentFrame}s</Text>
                </Text>
                <Text>
                  质量分: <Text strong>{frameInfo?.quality_score?.toFixed(1) ?? '-'}</Text>
                </Text>
                <Text>
                  清晰度: <Text strong>{frameInfo?.blur_score?.toFixed(0) ?? '-'}</Text>
                </Text>
              </Space>
              {frameInfo && frameInfo.global_tags.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>场景标签</Text>
                  <div style={{ marginTop: 4 }}>
                    {frameInfo.global_tags.map((t) => (
                      <Tag key={t} color="geekblue" style={{ marginBottom: 4 }}>{t}</Tag>
                    ))}
                  </div>
                </div>
              )}
              {frameInfo && frameInfo.objects.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>检测目标</Text>
                  <div style={{ marginTop: 4 }}>
                    {frameInfo.objects.map((o, i) => (
                      <div
                        key={`${o.class_name}-${i}`}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '4px 0',
                        }}
                      >
                        <span
                          style={{
                            width: 10, height: 10, borderRadius: 2,
                            background: OBJECT_COLORS[o.class_name] || FALLBACK_COLOR,
                            flexShrink: 0,
                          }}
                        />
                        <Text style={{ fontSize: 13 }}>{o.class_name}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {(o.confidence * 100).toFixed(0)}% ·{' '}
                          {Math.round(o.bbox.width)}×{Math.round(o.bbox.height)}
                        </Text>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            <Card size="small" title="片段汇总">
              <div style={{ marginBottom: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>检测目标</Text>
                <div style={{ marginTop: 4 }}>
                  {run.objects.length === 0 && <Text type="secondary">无</Text>}
                  {run.objects.map((o) => (
                    <Tag
                      key={o.class_name}
                      color={OBJECT_COLORS[o.class_name] || FALLBACK_COLOR}
                      style={{ marginBottom: 4 }}
                    >
                      {o.class_name} ×{o.count}
                    </Tag>
                  ))}
                </div>
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>场景标签</Text>
                <div style={{ marginTop: 4 }}>
                  {run.tags.length === 0 && <Text type="secondary">无</Text>}
                  {run.tags.map((t) => (
                    <Tag key={t.name} color="geekblue" style={{ marginBottom: 4 }}>
                      {t.name} ×{t.count}
                    </Tag>
                  ))}
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>平均质量分</Text>
                <div style={{ marginTop: 4 }}>
                  <Text strong style={{ fontSize: 18 }}>{run.avg_quality.toFixed(1)}</Text>
                </div>
              </div>
            </Card>
          </Col>
        </Row>
      </Space>
    </Spin>
  );
};

// ============================================================
// 标注检索页面
// ============================================================
const AnnotationBrowser: React.FC = () => {
  const [options, setOptions] = useState<AnnotationOptions | null>(null);
  const [selectedObjects, setSelectedObjects] = useState<string[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [data, setData] = useState<AnnotationRun[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [selectedRun, setSelectedRun] = useState<AnnotationRun | null>(null);

  const doSearch = useCallback(
    async (p: number, objs: string[], tags: string[]) => {
      setLoading(true);
      try {
        const res = await searchAnnotations({
          objects: objs, tags, page: p, page_size: pageSize,
        });
        setData(res.items);
        setTotal(res.total);
        setPage(res.page);
      } catch (err: any) {
        message.error('查询失败: ' + (err?.message || '网络错误'));
      } finally {
        setLoading(false);
      }
    },
    [pageSize]
  );

  // 初始化：拉取筛选项词表 + 全量列表
  useEffect(() => {
    getAnnotationOptions()
      .then(setOptions)
      .catch((err: any) => {
        message.error('加载筛选项失败: ' + (err?.message || '网络错误'));
      });
    doSearch(1, [], []);
  }, [doSearch]);

  const columns: ColumnsType<AnnotationRun> = [
    {
      title: '缩略图',
      dataIndex: 'thumbnail_url',
      width: 140,
      render: (_, run) => <Thumbnail run={run} />,
    },
    {
      title: '视频',
      key: 'video',
      width: 220,
      render: (_, run) => (
        <div>
          <Space size={4}>
            <Text strong style={{ fontSize: 13 }}>{run.device_id || '未知设备'}</Text>
            <Tag color="blue" style={{ fontSize: 10, marginRight: 0 }}>
              {VIEW_LABELS[run.camera_view] || run.camera_view}
            </Tag>
          </Space>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {run.content_date || run.uploaded_date || '-'}
            </Text>
          </div>
          <Text code style={{ fontSize: 11 }}>{run.video_id}</Text>
        </div>
      ),
    },
    {
      title: '帧范围',
      key: 'frames',
      width: 170,
      render: (_, run) => (
        <div>
          <Text style={{ fontSize: 13 }}>
            {run.start_frame}–{run.end_frame}
          </Text>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>
              {run.frame_count} 帧 · {run.end_sec - run.start_sec + 1}s
            </Text>
          </div>
        </div>
      ),
    },
    {
      title: '检测目标',
      dataIndex: 'objects',
      render: (objs: AnnotationRun['objects']) => (
        <div>
          {objs.length === 0 && <Text type="secondary">无</Text>}
          {objs.map((o) => (
            <Tag
              key={o.class_name}
              color={OBJECT_COLORS[o.class_name] || FALLBACK_COLOR}
              style={{ marginBottom: 2, fontSize: 11 }}
            >
              {o.class_name} ×{o.count}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '场景标签',
      dataIndex: 'tags',
      render: (tags: AnnotationRun['tags']) => (
        <div>
          {tags.length === 0 && <Text type="secondary">无</Text>}
          {tags.map((t) => (
            <Tag key={t.name} color="geekblue" style={{ marginBottom: 2, fontSize: 11 }}>
              {t.name} ×{t.count}
            </Tag>
          ))}
        </div>
      ),
    },
    {
      title: '平均质量分',
      dataIndex: 'avg_quality',
      width: 140,
      render: (v: number) => (
        <Progress
          percent={Math.min(v, 100)}
          size="small"
          format={(p) => `${(p ?? 0).toFixed(0)}`}
        />
      ),
    },
  ];

  return (
    <div style={{ padding: 24, maxWidth: 1280, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>标注检索</Title>
      </div>

      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap size={8}>
          <Text strong>检测目标</Text>
          <Select
            mode="multiple"
            allowClear
            placeholder="全部目标"
            style={{ minWidth: 260 }}
            maxTagCount="responsive"
            value={selectedObjects}
            onChange={setSelectedObjects}
            options={(options?.objects ?? []).map((o) => ({ label: o, value: o }))}
          />
          <Text strong>场景标签</Text>
          <Select
            mode="multiple"
            allowClear
            placeholder="全部标签"
            style={{ minWidth: 260 }}
            maxTagCount="responsive"
            value={selectedTags}
            onChange={setSelectedTags}
            options={(options?.tags ?? []).map((t) => ({ label: t, value: t }))}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            loading={loading}
            onClick={() => doSearch(1, selectedObjects, selectedTags)}
          >
            查询
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setSelectedObjects([]);
              setSelectedTags([]);
              doSearch(1, [], []);
            }}
          >
            重置
          </Button>
        </Space>
      </Card>

      {/* 结果表 */}
      <Card size="small">
        <Table<AnnotationRun>
          rowKey="run_id"
          columns={columns}
          dataSource={data}
          loading={loading}
          size="middle"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: false,
            showTotal: (t) => `共 ${t} 个片段`,
            onChange: (p) => doSearch(p, selectedObjects, selectedTags),
          }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="暂无匹配的标注数据，请先上传视频并完成标注"
              />
            ),
          }}
          onRow={(run) => ({
            onClick: () => setSelectedRun(run),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {/* 详情抽屉 */}
      <Drawer
        title={`标注片段 ${selectedRun?.run_id ?? ''}`}
        width={960}
        open={selectedRun !== null}
        onClose={() => setSelectedRun(null)}
        destroyOnClose
      >
        {selectedRun && <RunDetail run={selectedRun} />}
      </Drawer>
    </div>
  );
};

export default AnnotationBrowser;
