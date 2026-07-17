import React, { useState, useCallback } from 'react';
import {
  Modal, Upload, Form, Input, Select, Button, Space, message,
  Progress, Typography, Divider, Tag,
} from 'antd';
import {
  InboxOutlined, UploadOutlined, PlusOutlined,
  DeleteOutlined, CloudUploadOutlined,
} from '@ant-design/icons';
import type { UploadFile, RcFile } from 'antd/es/upload/interface';
import { uploadVideo, createTask } from '../services/api';

const { Dragger } = Upload;
const { Text } = Typography;

const CAMERA_VIEWS = ['front', 'back', 'left_repeater', 'right_repeater'];
const DEFAULT_DEVICE_ID = 'Tesla-ModelY-001';

interface UploadItem {
  key: string;
  file: RcFile;
  camera_view: string;
  status: 'pending' | 'uploading' | 'done' | 'error';
  progress?: number;
  error?: string;
}

interface VideoUploadModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * 从文件名中尝试解析时间戳。
 * 支持格式: YYYY-MM-DD_HH-MM-SS 或 YYYYMMDD_HHMMSS
 * 例如: "2025-01-15_18-30-00-front.mp4" → "2025-01-15_18-30-00"
 */
function parseTimestampFromFilename(filename: string): string | null {
  // 匹配 YYYY-MM-DD_HH-MM-SS
  const match1 = filename.match(/(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})/);
  if (match1) return match1[1];
  // 匹配 YYYYMMDD_HHMMSS
  const match2 = filename.match(/(\d{8}_\d{6})/);
  if (match2) return match2[1];
  return null;
}

/**
 * 从文件名中尝试解析相机视角。
 * 例如: "...front.mp4" → "front"
 *       "...back.mp4"  → "back"
 *       "...left_repeater.mp4" → "left_repeater"
 *       "...right_repeater.mp4" → "right_repeater"
 */
function parseCameraViewFromFilename(filename: string): string | null {
  const lower = filename.toLowerCase();
  // 优先匹配完整关键词
  if (lower.includes('right_repeater') || lower.includes('right-repeater')) return 'right_repeater';
  if (lower.includes('left_repeater') || lower.includes('left-repeater')) return 'left_repeater';
  if (lower.includes('front')) return 'front';
  if (lower.includes('back') || lower.includes('rear')) return 'back';
  return null;
}

const VideoUploadModal: React.FC<VideoUploadModalProps> = ({
  open, onClose, onSuccess,
}) => {
  const [form] = Form.useForm();
  const [uploadItems, setUploadItems] = useState<UploadItem[]>([]);
  const [batchUploading, setBatchUploading] = useState(false);

  // 处理文件拖拽/选择 – 自动解析文件名中的时间戳和视角
  const handleFilesAdded = useCallback((files: RcFile[]) => {
    const newItems: UploadItem[] = files.map((file, idx) => {
      // 尝试从文件名解析视角
      const parsedView = parseCameraViewFromFilename(file.name);
      const cameraView = parsedView || CAMERA_VIEWS[idx % CAMERA_VIEWS.length] || 'front';
      return {
        key: `${Date.now()}-${idx}`,
        file,
        camera_view: cameraView,
        status: 'pending' as const,
      };
    });

    setUploadItems((prev) => [...prev, ...newItems]);

    // 从第一个文件名中尝试提取时间戳并自动填入表单
    if (files.length > 0) {
      const ts = parseTimestampFromFilename(files[0].name);
      if (ts && !form.getFieldValue('timestamp')) {
        form.setFieldsValue({ timestamp: ts });
      }
    }
  }, [form]);

  const handleRemoveItem = (key: string) => {
    setUploadItems((prev) => prev.filter((item) => item.key !== key));
  };

  const handleCameraViewChange = (key: string, value: string) => {
    setUploadItems((prev) =>
      prev.map((item) => (item.key === key ? { ...item, camera_view: value } : item))
    );
  };

  // 批量上传所有待上传项
  const handleBatchUpload = async () => {
    const deviceId = form.getFieldValue('device_id');
    const timestamp = form.getFieldValue('timestamp');

    if (!deviceId || !timestamp) {
      message.warning('请填写设备ID和时间戳');
      return;
    }
    if (uploadItems.length === 0) {
      message.warning('请添加至少一个视频文件');
      return;
    }

    setBatchUploading(true);
    let successCount = 0;
    let failCount = 0;
    const uploadedVideoIds: string[] = [];

    const updatedItems = [...uploadItems];

    for (let i = 0; i < updatedItems.length; i++) {
      const item = updatedItems[i];
      if (item.status === 'done') continue;

      updatedItems[i] = { ...item, status: 'uploading', progress: 0 };
      setUploadItems([...updatedItems]);

      try {
        const formData = new FormData();
        formData.append('file', item.file);
        formData.append('device_id', deviceId);
        formData.append('timestamp', timestamp);
        formData.append('camera_view', item.camera_view);

        const result = await uploadVideo(formData);
        uploadedVideoIds.push(result.video_id);
        updatedItems[i] = { ...updatedItems[i], status: 'done', progress: 100 };
        successCount++;
      } catch (err: any) {
        updatedItems[i] = {
          ...updatedItems[i],
          status: 'error',
          error: err?.response?.data?.detail || err?.message || '上传失败',
        };
        failCount++;
      }

      setUploadItems([...updatedItems]);
    }

    setBatchUploading(false);

    if (failCount === 0) {
      message.success(`全部 ${successCount} 个视频上传成功！`);

      // 自动触发标注任务
      if (uploadedVideoIds.length > 0) {
        try {
          const task = await createTask(uploadedVideoIds);
          message.info(`已自动提交标注任务 (${task.task_id})`, 5);
        } catch {
          message.warning('标注任务提交失败，可稍后手动触发');
        }
      }

      onSuccess();
      // 重置状态
      setUploadItems([]);
      form.resetFields();
      onClose();
    } else {
      message.warning(`${successCount} 个成功，${failCount} 个失败`);
    }
  };

  // 关闭时重置
  const handleClose = () => {
    if (batchUploading) return;
    setUploadItems([]);
    form.resetFields();
    onClose();
  };

  const pendingCount = uploadItems.filter((i) => i.status === 'pending').length;
  const doneCount = uploadItems.filter((i) => i.status === 'done').length;
  const errorCount = uploadItems.filter((i) => i.status === 'error').length;

  return (
    <Modal
      title={
        <Space>
          <CloudUploadOutlined />
          上传 Tesla 视频
        </Space>
      }
      open={open}
      onCancel={handleClose}
      width={720}
      footer={null}
      destroyOnClose
    >
      {/* 拖拽上传区域 */}
      <Dragger
        multiple
        accept="video/*"
        showUploadList={false}
        beforeUpload={(file) => {
          handleFilesAdded([file as RcFile]);
          return false; // 阻止自动上传
        }}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽视频文件到此区域</p>
        <p className="ant-upload-hint">
          支持批量选择 Tesla 四视角视频（front / back / left_repeater / right_repeater）
        </p>
      </Dragger>

      {/* 设备信息表单 */}
      <Form
        form={form}
        layout="inline"
        initialValues={{ device_id: DEFAULT_DEVICE_ID }}
        style={{ marginBottom: 16, gap: 8, flexWrap: 'wrap' }}
      >
        <Form.Item
          name="device_id"
          label="设备 ID"
          rules={[{ required: true, message: '请输入设备ID' }]}
          style={{ flex: '1 1 200px' }}
        >
          <Input placeholder="例如: Tesla-ModelY-001" />
        </Form.Item>
        <Form.Item
          name="timestamp"
          label="时间戳"
          rules={[{ required: true, message: '请输入时间戳' }]}
          style={{ flex: '1 1 200px' }}
        >
          <Input placeholder="例如: 2025-01-15_18-30-00" />
        </Form.Item>
      </Form>

      {/* 文件列表 */}
      {uploadItems.length > 0 && (
        <div
          style={{
            maxHeight: 280,
            overflow: 'auto',
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            padding: 12,
          }}
        >
          {uploadItems.map((item) => (
            <div
              key={item.key}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 0',
                borderBottom: '1px solid #fafafa',
              }}
            >
              <Text
                style={{
                  flex: 1,
                  minWidth: 0,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={item.file.name}
              >
                {item.file.name}
              </Text>

              <Select
                size="small"
                value={item.camera_view}
                onChange={(v) => handleCameraViewChange(item.key, v)}
                style={{ width: 120 }}
                disabled={item.status === 'uploading' || batchUploading}
                options={CAMERA_VIEWS.map((v) => ({
                  value: v,
                  label: v.replace('_', ' ').toUpperCase(),
                }))}
              />

              {item.status === 'uploading' && (
                <Progress
                  percent={item.progress}
                  size="small"
                  style={{ width: 100, margin: 0 }}
                />
              )}

              {item.status === 'done' && (
                <Tag color="success" style={{ margin: 0 }}>完成</Tag>
              )}

              {item.status === 'error' && (
                <Tag color="error" style={{ margin: 0 }} title={item.error}>
                  失败
                </Tag>
              )}

              {item.status !== 'uploading' && (
                <Button
                  type="text"
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => handleRemoveItem(item.key)}
                  disabled={batchUploading}
                />
              )}
            </div>
          ))}
        </div>
      )}

      {/* 底部操作栏 */}
      <Divider style={{ margin: '12px 0' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary">
          {uploadItems.length > 0
            ? `共 ${uploadItems.length} 个文件 | 待上传: ${pendingCount} | 已完成: ${doneCount} | 失败: ${errorCount}`
            : '请添加视频文件'}
        </Text>
        <Space>
          <Button onClick={handleClose} disabled={batchUploading}>
            取消
          </Button>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={handleBatchUpload}
            loading={batchUploading}
            disabled={uploadItems.filter((i) => i.status === 'pending').length === 0}
          >
            批量上传
          </Button>
        </Space>
      </div>
    </Modal>
  );
};

export default VideoUploadModal;
