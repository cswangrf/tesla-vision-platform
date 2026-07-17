tesla-vision-platform/
├── docker-compose.yml
├── .env
├── backup/                         # 其他项目的代码备份
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口
│   │   ├── config.py
│   │   ├── routers/
│   │   │   ├── videos.py
│   │   │   ├── tasks.py
│   │   │   └── chat.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── annotation_engine.py # 联合标注服务客户端
│   │   │   ├── ollama_client.py
│   │   │   └── spark_client.py
│   │   └── utils/
│   │       └── video_utils.py
│   └── tasks/                       # Celery 任务
│       ├── celery_app.py
│       └── process_video.py
├── annotation-worker/               # 独立推理微服务 (可选)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── server.py                    # Triton 或 FastAPI 推理服务
│   ├── chinese_clip.py
│   └── locate_anything.py
├── spark-jobs/
│   ├── Dockerfile.spark
│   ├── requirements.txt
│   ├── data_cleaning.py             # 质量过滤 & 筛选
│   └── metadata_aggregation.py
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── MultiViewPlayer.tsx
│   │   │   └── ChatPanel.tsx
│   │   └── services/api.ts
│   └── public/
├── minio/
│   └── init-buckets.sh              # 初始化存储桶脚本
└── nginx/
    └── default.conf