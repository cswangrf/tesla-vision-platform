# Tesla Vision Platform

> 自动驾驶视频智能标注与检索平台

基于多模态大模型的 Tesla 多视角视频标注、管理、智能问答一体化平台。支持视频上传、多视角同步播放、Chinese-CLIP + Grounding DINO 联合标注、自然语言检索和 Spark 大规模数据处理。

---

## 目录

- [系统架构](#系统架构)
- [核心技术栈](#核心技术栈)
- [功能特性](#功能特性)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [部署指南](#部署指南)
- [API 接口](#api-接口)
- [前端界面](#前端界面)
- [处理流程](#处理流程)
- [GPU 资源分配](#gpu-资源分配)
- [配置说明](#配置说明)

---

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                    前端展示层 (React)                      │
│  视频同步播放器 | 智能问答界面 | 视频上传管理 | 数据看板   │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────┴───────────────────────────────────┐
│                     API 网关层 (FastAPI)                    │
│  视频上传/流式传输 | 任务调度 | 对话管理 | 视频检索        │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│                    智能处理服务层                           │
│  ┌────────────────┐ ┌───────────────┐ ┌───────────────┐  │
│  │ 联合标注引擎    │ │ 对话推理服务   │ │ 数据筛选服务   │  │
│  │ Chinese-CLIP +  │ │ Ollama        │ │ Spark +       │  │
│  │ Grounding DINO  │ │ Qwen2.5:7B    │ │ Parquet       │  │
│  └────────────────┘ └───────────────┘ └───────────────┘  │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│                   数据湖 & 存储层                           │
│  ┌──────────────────────┐ ┌────────────────────────────┐  │
│  │ 原始视频 (MinIO/S3)   │ │ Parquet 标注库 + 元数据     │  │
│  └──────────────────────┘ └────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

采用微服务 + 数据湖架构，分为四层：
- **前端展示层**：React + TypeScript，提供多视角视频播放器、智能问答、视频上传管理
- **API 网关层**：FastAPI 后端，统一接入视频上传/流式传输、任务管理、对话接口
- **智能处理服务层**：GPU 推理服务（Chinese-CLIP + Grounding DINO）、Ollama LLM、Spark 数据处理
- **数据湖存储层**：MinIO 对象存储（视频文件）、Parquet 格式标注数据湖

---

## 核心技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **前端** | React 18 + TypeScript + Ant Design 5 | SPA 应用，组件化架构 |
| **视频播放** | Video.js 8 | 多视角同步播放器 |
| **后端** | Python FastAPI + Celery | RESTful API + 异步任务队列 |
| **消息队列** | Redis | Celery Broker + 缓存 |
| **对象存储** | MinIO (S3 API) | 视频文件存储与流式读取 |
| **大模型** | Ollama + Qwen2.5:7B | 对话推理，支持 Function Calling |
| **语义理解** | Chinese-CLIP (ViT-L-14) | 全局语义向量提取 + 零样本场景分类 |
| **目标检测** | Grounding DINO | 开放词汇细粒度目标检测 |
| **数据处理** | PySpark + Delta Lake + Parquet | 大规模标注数据清洗与聚合 |
| **部署** | Docker Compose + NVIDIA Container Toolkit | 一键编排启动 |
| **GPU 框架** | PyTorch 2.4 + CUDA 12.1 | 模型推理加速 |

---

## 功能特性

### 🎬 视频管理
- **拖拽/批量上传**：支持同时上传 Tesla 四视角视频（front / back / left_repeater / right_repeater）
- **目录结构保留**：自动按 `{device_id}/{timestamp}/{camera_view}.mp4` 组织存储
- **视频流式播放**：MinIO 直出视频流，前端通过 video.js 播放
- **视频列表管理**：分页查询、按设备筛选、批量删除

### 🖥️ 多视角同步播放器
- **2×2 网格布局**：同时展示四个 Tesla 摄像头视角
- **单击放大**：点击任一视角切换为主视图（占据 75% 面积）
- **同步控制**：播放/暂停/seek 四视角同步
- **空状态提示**：无视频时引导用户上传

### 🤖 智能问答
- **自然语言检索**：基于 Qwen2.5:7B 的理解能力，用自然语言查询视频数据
- **Function Calling**：模型自动调用搜索工具，查询 Spark 标注数据库
- **多轮对话**：维护对话历史，支持上下文连续提问
- **视频结果展示**：搜索结果包含视频 ID、时间戳、匹配标签

### 🔬 联合标注
- **Chinese-CLIP 全局标注**：提取帧级语义向量，零样本分类得到场景标签（高速公路、雨天、十字路口等 12 类）
- **Grounding DINO 目标检测**：检测车辆、行人、交通标志、红绿灯等 7 类目标
- **质量评估**：自动计算模糊度、亮度、目标密度，生成帧级质量分数
- **Parquet 存储**：标注结果以列式格式存储，支持高效 Spark 查询

### 📊 数据处理
- **低质量过滤**：过滤模糊、过暗、目标过少的帧
- **语义筛选**：按场景标签 + 目标类型组合查询
- **元数据聚合**：生成视频级统计（场景分布、目标分布、质量分布）
- **Delta Lake**：ACID 事务支持，版本化管理标注数据

---

## 项目结构

```
tesla-vision-platform/
├── docker-compose.yml                 # 容器编排（10 个服务）
├── .env                               # 环境变量配置
├── README.md
├── design.md                          # 详细设计方案
│
├── frontend/                          # React 前端
│   ├── Dockerfile                     # 多阶段构建 (Node → Nginx)
│   ├── nginx.conf                     # Nginx 反向代理配置
│   ├── package.json
│   ├── vite.config.ts                 # Vite 构建配置 (dev proxy)
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── App.tsx                    # 主应用（Layout + 路由）
│       ├── main.tsx                   # 入口
│       ├── components/
│       │   ├── MultiViewPlayer.tsx    # 多视角同步播放器
│       │   ├── VideoBrowser.tsx       # 视频浏览页（列表 + 播放器 + 上传入口）
│       │   ├── VideoUploadModal.tsx   # 视频上传弹窗（拖拽 + 批量上传）
│       │   └── ChatPanel.tsx          # 智能问答面板
│       └── services/
│           └── api.ts                 # API 客户端（所有后端接口封装）
│
├── backend/                           # FastAPI 后端
│   ├── Dockerfile                     # Python 3.11 镜像
│   ├── requirements.txt               # Python 依赖
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口 (路由注册)
│   │   ├── config.py                  # 全局配置 (环境变量)
│   │   ├── routers/
│   │   │   ├── videos.py              # 视频上传/列表/流式传输/删除
│   │   │   ├── tasks.py               # 任务创建/状态查询/取消
│   │   │   └── chat.py                # 智能问答 (Function Calling)
│   │   ├── models/
│   │   │   └── schemas.py             # Pydantic 数据模型
│   │   ├── services/
│   │   │   ├── annotation_engine.py   # 联合标注客户端 (CLIP + DINO)
│   │   │   ├── ollama_client.py       # Ollama LLM 客户端 (OpenAI API)
│   │   │   └── spark_client.py        # Spark SQL 查询客户端
│   │   └── utils/
│   │       └── video_utils.py         # 视频工具 (抽帧/模糊检测/切分)
│   └── tasks/
│       ├── celery_app.py              # Celery 配置
│       └── process_video.py           # 视频处理任务 (抽帧→标注→存储)
│
├── annotation-worker/                 # GPU 推理服务
│   ├── Dockerfile                     # PyTorch 2.4 + CUDA 12.1
│   ├── requirements.txt
│   ├── server.py                      # FastAPI 推理微服务
│   ├── chinese_clip.py                # Chinese-CLIP 封装 (ViT-L/H)
│   └── locate_anything.py             # Grounding DINO 目标检测
│
├── spark-jobs/                        # Spark 数据处理任务
│   ├── Dockerfile.spark               # Bitnami Spark 3.5
│   ├── requirements.txt
│   ├── data_cleaning.py               # 数据清洗 (低质量过滤 + 筛选)
│   └── metadata_aggregation.py        # 元数据聚合 (视频级统计)
│
├── minio/
│   └── init-buckets.sh                # MinIO 存储桶初始化
│
└── nginx/
    └── default.conf                   # 可选独立 Nginx 配置
```

---

## 快速开始

### 前置要求

- Docker 24+ & Docker Compose v2
- NVIDIA Container Toolkit（GPU 推理必需）
- 至少 4× NVIDIA GPU（推荐 4× RTX 2080 Ti，11GB 显存）
- 建议存储空间 ≥ 100GB（模型 + 视频数据）

### 本地开发启动

**前端开发**：

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000 (自动代理 /api 到 localhost:8000)
```

**后端开发**：

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:8000/docs (API 文档)
```

### Docker Compose 一键启动

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，按需修改端口、路径等

# 2. 拉取 Ollama 模型（仅首次）
docker compose exec ollama ollama pull qwen2.5:7b

# 3. 启动所有服务
docker compose up -d

# 4. 验证服务
docker compose ps
```

### 访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端界面 | `http://localhost:3000` | React SPA |
| 后端 API | `http://localhost:8000` | FastAPI |
| API 文档 | `http://localhost:8000/docs` | Swagger UI |
| MinIO 控制台 | `http://localhost:9003` | 对象存储管理 |
| Ollama API | `http://localhost:11435` | LLM 推理 |
| Spark Master UI | `http://localhost:8082` | 集群监控 |

---

## 部署指南

### 容器服务说明

| 服务 | 镜像 | GPU | 端口 | 说明 |
|------|------|-----|------|------|
| `redis` | redis:7-alpine | - | - | 消息队列 / 缓存 |
| `minio` | minio/minio | - | 9000/9001 | 对象存储 |
| `ollama` | ollama | GPU 2 | 11434 | LLM 推理 |
| `chinese-clip` | annotation-worker | GPU 0 | 8500 | 语义向量服务 |
| `locate-anything` | annotation-worker | GPU 1 | 8501 | 目标检测服务 |
| `api` | backend | - | 8000 | FastAPI 后端 |
| `celery-worker` | backend | - | - | 异步任务处理 |
| `spark-master` | bitnami/spark:3.5 | - | 7077/8080 | Spark 主节点 |
| `spark-worker` | bitnami/spark:3.5 | - | - | Spark 工作节点 |
| `frontend` | frontend | - | 80 | Nginx + React |

---

## API 接口

### 视频管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/videos/upload` | 上传视频（multipart，需 device_id/timestamp/camera_view） |
| `GET` | `/api/videos/` | 列出视频（分页，支持 device_id 过滤） |
| `GET` | `/api/videos/stream/{video_id}` | 流式播放视频（支持短 ID / 完整路径） |
| `DELETE` | `/api/videos/{video_id}` | 删除视频 |

### 任务管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/tasks/process` | 创建视频处理任务（标注） |
| `GET` | `/api/tasks/{task_id}` | 查询任务状态和进度 |
| `GET` | `/api/tasks/` | 列出所有任务（支持状态筛选） |
| `DELETE` | `/api/tasks/{task_id}` | 取消任务 |

### 智能问答

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/chat/query` | 发起对话查询（支持 Function Calling） |

### 推理服务

| 方法 | 路径 | 端口 | 说明 |
|------|------|------|------|
| `GET` | `/health` | 8500/8501 | 健康检查 |
| `POST` | `/embed` | 8500 | Chinese-CLIP 图像向量提取 |
| `POST` | `/classify` | 8500 | Chinese-CLIP 零样本分类 |
| `POST` | `/detect` | 8501 | Grounding DINO 目标检测 |

### 对话请求示例

```json
POST /api/chat/query
{
  "message": "帮我找傍晚下雨天，十字路口有行人的视频",
  "history": [
    {"role": "user", "content": "今天有哪些新上传的视频？"},
    {"role": "assistant", "content": "今天共有 12 段新视频..."}
  ]
}
```

---

## 前端界面

### 页面导航

| 页面 | 功能 |
|------|------|
| **Dashboard** | 数据看板（处理进度、标注统计） |
| **Video Browser** | 视频浏览（多视角播放器 + 视频列表 + 上传） |
| **Smart Q&A** | 智能问答（自然语言视频检索） |
| **Settings** | 平台配置 |

### Video Browser 页面

- **上方播放区**：2×2 网格展示 4 个摄像头视角，支持同步播放/暂停/seek
- **信息栏**：显示当前播放的设备 ID 和时间戳
- **下方列表区**：视频片段列表（按设备+时间分组），支持播放/删除操作
- **上传按钮**：打开上传弹窗
- **空状态**：无视频时显示引导提示

### 视频上传弹窗

- **拖拽上传区**：支持批量选择/拖拽视频文件
- **设备信息表单**：填写 device_id 和 timestamp
- **视角选择**：每个文件可选 front/back/left_repeater/right_repeater
- **批量上传**：一键上传所有待处理文件
- **进度反馈**：实时显示每个文件的上传状态（进行中/完成/失败）

---

## 处理流程

### 端到端流程

```
用户上传视频 (Web UI)
    ↓
MinIO 存储 (raw/{device_id}/{timestamp}/{view}.mp4)
    ↓
创建处理任务 (POST /api/tasks/process)
    ↓
Celery 异步任务
    ├── 1. 从 MinIO 下载视频
    ├── 2. 按 1fps 抽帧 (OpenCV)
    ├── 3. 并发调用 Chinese-CLIP + Grounding DINO 标注
    │       ├── Chinese-CLIP: 全局语义向量 + 零样本场景标签
    │       └── Grounding DINO: 目标边界框 + 类别 + 置信度
    ├── 4. 计算模糊分数 + 质量评分
    └── 5. 保存为 Parquet (frame_annotations)
    ↓
Spark 数据处理
    ├── data_cleaning.py: 低质量过滤 + 语义筛选
    └── metadata_aggregation.py: 视频级聚合统计
    ↓
前端查询播放
```

### 标注数据结构

帧标注结果存储在 `frame_annotations` Parquet 表中：

```json
{
  "video_id": "abc12345",
  "frame_index": 120,
  "timestamp_sec": 120.0,
  "global_embedding": [0.123, -0.456, ...],     // Chinese-CLIP 768 维向量
  "global_tags": ["十字路口", "白天", "城市街道"],  // 零样本分类标签
  "objects": [
    {
      "bbox": {"x": 320, "y": 180, "width": 120, "height": 80},
      "class_name": "车辆",
      "confidence": 0.92,
      "attributes": {}
    },
    {
      "bbox": {"x": 500, "y": 240, "width": 60, "height": 150},
      "class_name": "行人",
      "confidence": 0.85,
      "attributes": {}
    }
  ],
  "blur_score": 324.5,         // Laplacian 方差
  "quality_score": 85.0         // 综合质量分 (0-100)
}
```

### 检测类别

**场景标签**（Chinese-CLIP 零样本分类，12 类）：
高速公路、城市街道、隧道、雨天、夜间、停车场、十字路口、拥堵路段、施工路段、乡村道路、晴天、白天

**目标类别**（Grounding DINO 检测，7 类）：
车辆、行人、交通标志、红绿灯、障碍物、自行车、摩托车

---

## GPU 资源分配

```
GPU 0 → Chinese-CLIP (ViT-L-14, ~2-3GB 显存)
GPU 1 → Grounding DINO (LocateAnything, ~3-5GB 显存)
GPU 2 → Ollama + Qwen2.5:7B (~5-6GB 显存)
GPU 3 → 预留（可扩展模型或批量推理）
```

---

## 配置说明

### 主要环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MINIO_ROOT_USER` | `minioadmin` | MinIO 用户名 |
| `MINIO_ROOT_PASSWORD` | `minioadmin` | MinIO 密码 |
| `REDIS_URL` | `redis://redis:6379/0` | Redis 连接 |
| `OLLAMA_HOST` | `ollama:11434` | Ollama 服务地址 |
| `OLLAMA_MODEL` | `qwen2.5:7b` | 默认 LLM 模型 |
| `LLM_PROVIDER` | `ollama` | LLM 提供商 |
| `CLIP_SERVICE` | `http://chinese-clip:8500` | Chinese-CLIP 服务 |
| `LAM_SERVICE` | `http://locate-anything:8501` | 目标检测服务 |
| `FRAME_EXTRACT_INTERVAL` | `30` | 抽帧间隔（帧） |
| `VIDEO_CLIP_DURATION_SEC` | `60` | 视频切分片段时长 |
| `DATA_ROOT` | `/mnt/sdc/vision-platform` | 数据持久化根目录 |
| `FRONTEND_PORT` | `3000` | 前端端口 |
| `API_PORT` | `8000` | API 端口 |
| `MINIO_API_PORT` | `9002` | MinIO API 端口 |
| `MINIO_CONSOLE_PORT` | `9003` | MinIO 控制台端口 |
| `OLLAMA_HOST_PORT` | `11435` | Ollama API 端口 |
| `CLIP_GPU_DEVICE` | `0` | Chinese-CLIP 绑定的 GPU |
| `LAM_GPU_DEVICE` | `1` | 目标检测绑定的 GPU |
| `OLLAMA_GPU_DEVICE` | `2` | Ollama 绑定的 GPU |
| `SPARK_WORKER_MEMORY` | `16G` | Spark Worker 内存 |
| `SPARK_WORKER_CORES` | `8` | Spark Worker 核心数 |

### 视频存储目录结构

```
/raw/{device_id}/{timestamp}/{camera_view}.mp4

示例:
/raw/Tesla-ModelY-001/2025-01-15_18-30-00/front.mp4
/raw/Tesla-ModelY-001/2025-01-15_18-30-00/back.mp4
/raw/Tesla-ModelY-001/2025-01-15_18-30-00/left_repeater.mp4
/raw/Tesla-ModelY-001/2025-01-15_18-30-00/right_repeater.mp4
```

---

## License

MIT
