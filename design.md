# 平台设计方案

## 1. 系统架构总览

采用微服务 + 数据湖架构，分为五层：

```
┌──────────────────────────────────────────────────────────┐
│                    前端展示层 (React)                      │
│  视频同步播放器 | 智能问答界面 | 标注可视化 | 数据看板      │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP/WebSocket
┌──────────────────────┴───────────────────────────────────┐
│                     API 网关层 (FastAPI)                    │
│  用户管理 | 任务调度 | 对话管理 | 视频检索接口            │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│                    智能处理服务层                           │
│  ┌───────────────┐ ┌──────────────┐ ┌─────────────────┐ │
│  │ 多模态标注引擎 │ │ 对话推理服务 │ │ 数据筛选服务    │ │
│  │ Chinese-CLIP + │ │ Ollama       │ │ Spark + Parquet │ │
│  │ LocateAnything │ │ Qwen2.5:7B   │ │ 质量评估过滤    │ │
│  └───────────────┘ └──────────────┘ └─────────────────┘ │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────┐
│                  数据湖 & 存储层                           │
│  ┌─────────────────────┐ ┌─────────────────────────────┐ │
│  │ 原始视频 (MinIO/S3) │ │ Parquet 标注库 + 元数据      │ │
│  └─────────────────────┘ └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

## 2. 核心技术栈

- **前端**：React + TypeScript + Video.js (同步多视频播放) + Ant Design
- **后端 API**：Python FastAPI + Celery (异步任务)
- **模型推理**：Chinese-CLIP (HuggingFace/CN-CLIP) 、LocateAnything-3B（可基于 Florence-2 微调或 Grounding DINO 等）、Ollama 管理 Qwen2.5:7B
- **大数据处理**：PySpark + Parquet + Delta Lake (版本化元数据)
- **存储**：MinIO (兼容 S3) 作为视频存储，Apache Hudi/Iceberg 管理 PB 级元数据
- **消息队列**：Redis + RabbitMQ (任务调度)
- **部署**：Docker Compose + NVIDIA Container Toolkit

## 3. 数据接入与处理管线

### 3.1 原始数据上传

- 前端提供拖拽/文件夹上传，保留 Tesla 的时间-视角目录结构。
- 后端接收后解构为统一格式：
  ```
  /raw/{device_id}/{timestamp}/{camera_view}.mp4
  ```
- 视频元数据（时间戳、视角、GPS 等）写入 `videos_meta` Parquet 表。

### 3.2 联合标注流程（核心）

对每一个视频片段（1分钟）按 1 fps 抽帧，生成图像序列，同时送入两个模型：

- **Chinese-CLIP**：提取整帧的全局语义向量和文本对齐标签（如“城市街道”、“雨天”、“夜间”）。利用预设的自动驾驶场景文本集（如“施工路段”、“行人密集”）进行零样本分类，得到**全局语义标签向量**。
- **LocateAnything-3B**：输入文本 prompt（如“所有车辆”、“交通标志”、“行人”），输出**细粒度目标边界框、类别、属性**。

标注结果统一为 JSON，并转化为 Parquet 表 `frame_annotations`：
| 字段 | 说明 |
|------|------|
| video_id, frame_index | 帧标识 |
| global_embedding | Chinese-CLIP 的 512/768 维向量 |
| global_tags | 如 ["highway", "sunny"] |
| objects | Array of {bbox, class, confidence, attributes} |

同时更新视频级聚合标注，如该片段包含目标统计、主要场景等。

### 3.3 Spark 数据筛选与纯化

基于 PySpark 读取 `frame_annotations` 和 `videos_meta` 实现灵活筛选：

- **低质量过滤**：
  - 模糊检测：利用 Laplacian 方差（预先计算并在标注中加入 `blur_score`）。
  - 目标密度过低（如镜头对准天空/地面无有效目标）。
  - 夜视全黑、过曝帧比例过高。
  - 时间过短或损坏的视频。
- **语义筛选**：
  - 根据 Chinese-CLIP 全局标签与目标类别组合，例如：“同时包含‘十字路口’全局标签，且检测到>3个行人”。
  - 将筛选结果写回 `filtered_videos` 表，或仅添加 `quality_score` 列便于后续查询。

使用 **Delta Lake** 实现 ACID 事务和时间旅行，支持 PB 级元数据高效更新。

## 4. 大规模数据管理方案（PB 级）

- **视频存储**：MinIO 集群，设置生命周期策略，将冷数据自动迁移到归档存储。
- **元数据湖**：
  - 采用 **Apache Hudi** 管理 Parquet 文件，支持增量 upsert，按日期分区。
  - 使用 **Z-ordering** 按 `global_tags` 和 `timestamp` 优化文件布局，加速多维查询。
  - 通过 Spark SQL 对外提供统一查询接口。
- **特征向量索引**：为 Chinese-CLIP 向量构建 **Milvus** 向量数据库，实现海量帧的语义相似搜索。
- **访问层**：Alluxio 缓存热数据，加速前端预览加载。

## 5. Web 预览与交互设计

### 5.1 多视角同步播放器

- **播放器区域**：默认2x2网格展示四个视角（front, back, left_repeater, right_repeater）。
- **同步控制**：一个全局进度轴，拖动时四个视频同步 seek。
- **放大交互**：单击任一视角，该视频平滑过渡到占据整个播放器区域（75%面积），其余三个缩小并排列在右侧或底部，再次点击恢复。使用 CSS Grid 动画实现。
- **时间轴标记**：根据标注结果，在进度轴上高亮显示检测到重要事件（如“行人穿行”、“交通灯变化”）的片段，悬停显示缩略图。

### 5.2 智能问答模块

- **对话界面**：类似 ChatGPT 的聊天窗口，支持多轮对话。
- **后端连接**：FastAPI 通过 Ollama Python 库调用 Qwen2.5:7B，维护会话历史。
- **工具增强（Function Calling）**：为模型提供查询数据库的函数工具：
  - `search_videos_by_semantics(query, tags, objects)` -> 向量检索 + Spark SQL 查询，返回符合条件的视频片段列表和时间戳。
  - `get_annotation_summary(video_id)` -> 返回结构化标注摘要。
- **交互示例**：
  - 用户：“帮我找傍晚下雨天，十字路口有行人闯红灯的视频。”
  - 助手调用工具，解析意图（“傍晚”、“雨”、“十字路口”、“行人”），通过 Chinese-CLIP 文本编码获取语义向量，结合 Spark 筛选 `global_tags` 和 `objects`，返回精确的视频列表并在前端播放器上定位到事件时间。

## 6. 处理流程示例（端到端）

1. 用户通过 Web页面 或者 在页面上弹出Minio的上传命令 上传 Tesla 视频文件夹，保留原始结构。
2. 后端创建 Spark 任务：解析视频，抽帧，并行调用 Chinese-CLIP 和 LocateAnything 推理服务（GPU 池化），生成 `frame_annotations` Parquet 表。
3. Spark 自动执行质量评估脚本，标记低质量帧，输出视频质量报告。
4. 前端数据看板显示处理进度、标注统计。
5. 用户在问答界面用自然语言查询，系统实时返回高光片段，多视角播放器同步展示。

## 7. 界面线框图示意

```
┌─────────────────────────────────────────────────────────────┐
│  Logo   Dashboard   Video Browser   Smart Q&A   Settings    │
├──────────────────────────┬──────────────────────────────────┤
│                          │  Chat:                           │
│   [Front] [Back]         │  User: 帮我找昨天傍晚堵车的视频。 │
│   [Left]  [Right]        │  Bot: 正在检索... 找到3段，已定位 │
│  ──●─────────────────    │       到 2025-06-07 18:30 前后。  │
│   timeline with markers  │   [video card] [video card]      │
│                          │                                  │
│   (click to enlarge)     │                                  │
└──────────────────────────┴──────────────────────────────────┘
```

## 8. 部署

- **GPU 分配**：使用 Docker 限制显存，Chinese-CLIP 占用 GPU0，LocateAnything 占用 GPU1，Qwen 占用 GPU2。Spark 任务在 CPU 上运行，不占用 GPU。
- **服务编排**：推理模型使用 NVIDIA Triton Inference Server 或简单的 FastAPI 微服务封装，通过负载均衡调用。
- **扩展性**：当数据量达到 PB 级，可增加工作节点部署 Spark Executor 和 MinIO 节点，模型推理服务可通过 K8s 横向扩展。

### 8.1 服务器配置

```
(base) root@wrf-SYS-7049GP-TRT:~# nvidia-smi
Thu Jul 16 15:25:50 2026
+---------------------------------------------------------------------------------------+
| NVIDIA-SMI 535.171.04             Driver Version: 535.171.04   CUDA Version: 12.2     |
|-----------------------------------------+----------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id        Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |         Memory-Usage | GPU-Util  Compute M. |
|                                         |                      |               MIG M. |
|=========================================+======================+======================|
|   0  NVIDIA GeForce RTX 2080 Ti     Off | 00000000:18:00.0 Off |                  N/A |
| 22%   33C    P8              16W / 250W |    688MiB / 11264MiB |      0%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+
|   1  NVIDIA GeForce RTX 2080 Ti     Off | 00000000:3B:00.0 Off |                  N/A |
| 22%   32C    P8              20W / 250W |    864MiB / 11264MiB |      0%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+
|   2  NVIDIA GeForce RTX 2080 Ti     Off | 00000000:86:00.0 Off |                  N/A |
| 22%   31C    P8               5W / 250W |   1080MiB / 11264MiB |      0%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+
|   3  NVIDIA GeForce RTX 2080 Ti     Off | 00000000:AF:00.0 Off |                  N/A |
| 22%   31C    P8              21W / 250W |      8MiB / 11264MiB |      0%      Default |
|                                         |                      |                  N/A |
+-----------------------------------------+----------------------+----------------------+

+---------------------------------------------------------------------------------------+
| Processes:                                                                            |
|  GPU   GI   CI        PID   Type   Process name                            GPU Memory |
|        ID   ID                                                             Usage      |
|=======================================================================================|
|    0   N/A  N/A      1460      G   /usr/lib/xorg/Xorg                            4MiB |
|    0   N/A  N/A   2923301      C   python                                      680MiB |
|    1   N/A  N/A      1460      G   /usr/lib/xorg/Xorg                            4MiB |
|    1   N/A  N/A      4536      C   python3                                     326MiB |
|    1   N/A  N/A      6541      C   /usr/bin/python3.9                          530MiB |
|    2   N/A  N/A      1460      G   /usr/lib/xorg/Xorg                            4MiB |
|    2   N/A  N/A      6435      C   /opt/conda/bin/python                      1072MiB |
|    3   N/A  N/A      1460      G   /usr/lib/xorg/Xorg                            4MiB |
+---------------------------------------------------------------------------------------+
(base) root@wrf-SYS-7049GP-TRT:~# nvcc -V
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2019 NVIDIA Corporation
Built on Sun_Jul_28_19:07:16_PDT_2019
Cuda compilation tools, release 10.1, V10.1.243
```
