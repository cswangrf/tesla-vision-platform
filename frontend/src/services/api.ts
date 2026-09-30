/**
 * Tesla Vision Platform - API 服务层
 *
 * 与后端 FastAPI 服务通信的封装。
 */

import axios, { AxiosInstance } from 'axios';

// ============================================================
// API 客户端配置
// ============================================================
const API_BASE_URL = '/api';

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  // 不设置默认 Content-Type，让 axios 根据数据类型自动推断：
  // - FormData → multipart/form-data（含 boundary）
  // - 普通对象 → application/json
});

// ============================================================
// 类型定义
// ============================================================
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

// 检索结果：标注数据聚合统计（与后端 spark_client.search 的返回结构一致）
export interface VideoSearchResult {
  total_frames: number;
  matched_frames: number;
  time_range?: string | null;
  object_distribution: Record<string, number>;
  tag_distribution: Record<string, number>;
  matched_videos: Array<{
    video_id: string;
    date: string;
    uploaded_date: string;
    matched_frames: number;
  }>;
}

export interface ChatResponse {
  reply: string;
  videos: VideoSearchResult[];
}

export interface VideoMetadata {
  video_id: string;
  device_id: string;
  timestamp: string;
  camera_view: string;
  duration_sec: number;
  fps: number;
  resolution: string;
  file_size_bytes: number;
  storage_path: string;
  uploaded_at: string;
  status: string;
}

export interface VideoListResponse {
  videos: VideoMetadata[];
  total: number;
  page: number;
  page_size: number;
}

export interface TaskResponse {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  video_ids: string[];
  progress: number;
  created_at: string;
  updated_at?: string;
  result?: Record<string, unknown>;
  error?: string;
}

// ============================================================
// Chat API
// ============================================================
export async function chatQuery(
  message: string,
  history: ChatMessage[] = [],
): Promise<ChatResponse> {
  // LLM 在 CPU 上推理较慢（可能 30s+），单独放宽超时；nginx 侧限制为 600s
  const response = await apiClient.post<ChatResponse>(
    '/chat/query',
    { message, history },
    { timeout: 300000 },
  );
  return response.data;
}

// ============================================================
// Stats API（数据看板）
// ============================================================
export interface StatsSummary {
  videos: {
    total_files: number;
    clips: number;
    devices: string[];
    total_size_bytes: number;
  };
  annotations: {
    total_frames?: number;
    matched_frames?: number;
    object_distribution?: Record<string, number>;
    tag_distribution?: Record<string, number>;
    matched_videos?: Array<{
      video_id: string;
      date: string;
      uploaded_date: string;
      matched_frames: number;
    }>;
  };
  tasks: Record<string, number>;
}

export async function getStats(): Promise<StatsSummary> {
  const response = await apiClient.get<StatsSummary>('/stats/summary');
  return response.data;
}

// ============================================================
// Videos API
// ============================================================
export async function uploadVideo(
  formData: FormData,
): Promise<{ video_id: string; filename: string }> {
  // 视频文件可达数 GB，上传耗时远超默认 30s
  const response = await apiClient.post('/videos/upload', formData, {
    timeout: 600000,
  });
  return response.data;
}

export async function getVideos(
  page: number = 1,
  pageSize: number = 20,
  deviceId?: string,
): Promise<VideoListResponse> {
  const params: Record<string, string | number> = { page, page_size: pageSize };
  if (deviceId) params.device_id = deviceId;

  const response = await apiClient.get<VideoListResponse>('/videos/', { params });
  return response.data;
}

export async function deleteVideo(videoId: string): Promise<void> {
  await apiClient.delete(`/videos/${videoId}`);
}

// ============================================================
// Tasks API
// ============================================================
export async function createTask(videoIds: string[]): Promise<TaskResponse> {
  const response = await apiClient.post<TaskResponse>('/tasks/process', {
    video_ids: videoIds,
  });
  return response.data;
}

export async function getTaskStatus(taskId: string): Promise<TaskResponse> {
  const response = await apiClient.get<TaskResponse>(`/tasks/${taskId}`);
  return response.data;
}

export async function listTasks(status?: string): Promise<TaskResponse[]> {
  const params: Record<string, string> = {};
  if (status) params.status = status;

  const response = await apiClient.get<TaskResponse[]>('/tasks/', { params });
  return response.data;
}

// ============================================================
// 标注检索 API（标注结果可视化）
// ============================================================
export interface AnnotationOptions {
  objects: string[];
  tags: string[];
}

export interface AnnotationRunObjectStat {
  class_name: string;
  count: number;
  max_confidence: number;
}

export interface AnnotationRunTagStat {
  name: string;
  count: number;
}

// 连续帧片段：同一视频中连续命中的帧合并为一条结果
export interface AnnotationRun {
  run_id: string;
  video_id: string;
  device_id: string;
  camera_view: string;
  content_date: string;
  uploaded_date: string;
  start_frame: number;
  end_frame: number;
  frame_count: number;
  start_sec: number;
  end_sec: number;
  objects: AnnotationRunObjectStat[];
  tags: AnnotationRunTagStat[];
  avg_quality: number;
  has_raw_video: boolean;
  thumbnail_url: string;
  clip_url: string;
}

export interface AnnotationSearchResponse {
  items: AnnotationRun[];
  total: number;
  page: number;
  page_size: number;
}

export interface AnnotationBBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AnnotationDetectedObject {
  bbox: AnnotationBBox;
  class_name: string;
  confidence: number;
  attributes?: Record<string, unknown>;
}

export interface AnnotationFrameDetail {
  video_id: string;
  frame_index: number;
  timestamp_sec: number;
  global_tags: string[];
  objects: AnnotationDetectedObject[];
  blur_score: number | null;
  quality_score: number | null;
}

export interface AnnotationFramesResponse {
  video_id: string;
  frames: AnnotationFrameDetail[];
}

export async function getAnnotationOptions(): Promise<AnnotationOptions> {
  const response = await apiClient.get<AnnotationOptions>('/annotations/options');
  return response.data;
}

export async function searchAnnotations(params: {
  objects?: string[];
  tags?: string[];
  page: number;
  page_size: number;
}): Promise<AnnotationSearchResponse> {
  const query: Record<string, string | number> = {
    page: params.page,
    page_size: params.page_size,
  };
  if (params.objects && params.objects.length > 0) {
    query.objects = params.objects.join(',');
  }
  if (params.tags && params.tags.length > 0) {
    query.tags = params.tags.join(',');
  }
  const response = await apiClient.get<AnnotationSearchResponse>(
    '/annotations/search',
    { params: query },
  );
  return response.data;
}

export async function getAnnotationFrames(
  videoId: string,
  start: number,
  end: number,
): Promise<AnnotationFramesResponse> {
  const response = await apiClient.get<AnnotationFramesResponse>(
    `/annotations/frames/${encodeURIComponent(videoId)}`,
    { params: { start, end } },
  );
  return response.data;
}

/** 标注帧图 URL（按需抽取 + MinIO 缓存） */
export function getAnnotationFrameUrl(videoId: string, frameIndex: number): string {
  return `${API_BASE_URL}/annotations/frame/${encodeURIComponent(videoId)}/${frameIndex}`;
}

/** 标注视频切片 URL（[start_sec, end_sec+1) 时间段） */
export function getAnnotationClipUrl(
  videoId: string,
  startSec: number,
  endSec: number,
): string {
  return `${API_BASE_URL}/annotations/clip/${encodeURIComponent(videoId)}?start_sec=${startSec}&end_sec=${endSec}`;
}

// ============================================================
// 视频流 URL 工具
// ============================================================
/**
 * 获取视频流 URL。
 * 支持两种格式：
 * - 完整路径: device_id/timestamp/camera_view.mp4
 * - 短 ID: etag 前8位
 */
export function getVideoStreamUrl(videoId: string): string {
  return `${API_BASE_URL}/videos/stream/${encodeURIComponent(videoId)}`;
}

// ============================================================
// 健康检查
// ============================================================
export async function healthCheck(): Promise<{ status: string }> {
  const response = await apiClient.get('/health');
  return response.data;
}

export default apiClient;
