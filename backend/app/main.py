from fastapi import FastAPI
from app.routers import videos, tasks, chat

app = FastAPI(title="Tesla Vision Platform")

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

@app.get("/health")
async def health():
    return {"status": "ok"}
