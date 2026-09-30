from fastapi import FastAPI
from app.routers import videos, tasks, chat, stats, annotations

app = FastAPI(title="Tesla Vision Platform")

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(annotations.router, prefix="/api/annotations", tags=["annotations"])

@app.get("/health")
async def health():
    return {"status": "ok"}
