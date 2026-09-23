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
