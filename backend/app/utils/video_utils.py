"""
Tesla Vision Platform - 视频处理工具

提供视频抽帧、格式转换、质量检测等功能。
"""

import os
import subprocess
import tempfile
import logging
from typing import List, Tuple, Optional

import cv2
import numpy as np

from app.config import FRAME_EXTRACT_INTERVAL, VIDEO_CLIP_DURATION_SEC

logger = logging.getLogger(__name__)


def extract_frames(
    video_path: str,
    output_dir: str,
    fps: float = 1.0,
    max_frames: Optional[int] = None,
) -> List[str]:
    """
    从视频中按指定 fps 抽帧。

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        fps: 抽帧频率（默认 1fps）
        max_frames: 最大帧数（可选）

    Returns:
        抽取的帧文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)
    frame_paths: List[str] = []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频文件: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS)
    if video_fps <= 0:
        video_fps = 30.0

    frame_interval = int(video_fps / fps) if fps > 0 else FRAME_EXTRACT_INTERVAL
    if frame_interval < 1:
        frame_interval = 1

    frame_idx = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            frame_filename = f"frame_{saved_count:06d}.jpg"
            frame_path = os.path.join(output_dir, frame_filename)
            cv2.imwrite(frame_path, frame)
            frame_paths.append(frame_path)
            saved_count += 1

            if max_frames and saved_count >= max_frames:
                break

        frame_idx += 1

    cap.release()
    logger.info(f"从 {video_path} 抽取了 {len(frame_paths)} 帧 (间隔={frame_interval})")
    return frame_paths


def get_video_info(video_path: str) -> dict:
    """
    获取视频基本信息。

    Returns:
        包含 duration, fps, width, height, codec 的字典
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频文件: {video_path}")

    info = {
        "duration_sec": cap.get(cv2.CAP_PROP_FRAME_COUNT) / max(cap.get(cv2.CAP_PROP_FPS), 1),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        "codec": int(cap.get(cv2.CAP_PROP_FOURCC)),
    }
    cap.release()
    return info


def compute_blur_score(image_path: str) -> float:
    """
    计算图像的模糊分数（Laplacian 方差）。

    值越高表示图像越清晰。

    Args:
        image_path: 图像文件路径

    Returns:
        模糊分数
    """
    image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if image is None:
        return 0.0

    laplacian = cv2.Laplacian(image, cv2.CV_64F)
    score = laplacian.var()
    return float(score)


def compute_brightness(image_path: str) -> float:
    """
    计算图像的平均亮度。

    Args:
        image_path: 图像文件路径

    Returns:
        平均亮度值 (0-255)
    """
    image = cv2.imread(image_path)
    if image is None:
        return 0.0

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def validate_video(video_path: str) -> Tuple[bool, str]:
    """
    验证视频文件是否有效。

    Returns:
        (是否有效, 错误信息)
    """
    if not os.path.exists(video_path):
        return False, f"文件不存在: {video_path}"

    try:
        info = get_video_info(video_path)
        if info["frame_count"] == 0:
            return False, "视频帧数为0"
        if info["duration_sec"] < 1.0:
            return False, f"视频时长过短 ({info['duration_sec']:.1f}s)"
        return True, ""
    except Exception as e:
        return False, str(e)


def split_video_clips(
    video_path: str,
    output_dir: str,
    clip_duration: int = VIDEO_CLIP_DURATION_SEC,
) -> List[str]:
    """
    将视频切分为固定时长的小片段。

    Args:
        video_path: 视频文件路径
        output_dir: 输出目录
        clip_duration: 每个片段的时长（秒）

    Returns:
        片段文件路径列表
    """
    os.makedirs(output_dir, exist_ok=True)

    info = get_video_info(video_path)
    total_duration = info["duration_sec"]

    clips: List[str] = []
    start_time = 0

    while start_time < total_duration:
        clip_name = f"clip_{start_time:04d}.mp4"
        clip_path = os.path.join(output_dir, clip_name)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-i", video_path,
            "-t", str(clip_duration),
            "-c", "copy",
            clip_path,
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            if os.path.exists(clip_path):
                clips.append(clip_path)
        except subprocess.CalledProcessError as e:
            logger.warning(f"切分片段失败 (start={start_time}): {e.stderr.decode()}")

        start_time += clip_duration

    logger.info(f"视频 {video_path} 切分为 {len(clips)} 个片段")
    return clips
