# edgepilot/api/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..db import init_db
from ..scheduler import get_scheduler
from .routers import metrics as metrics_router
from .routers import runs as runs_router
from .routers import tasks as tasks_router
from .routers import policies as policies_router
from .routers import usage as usage_router

app = FastAPI(title="EdgePilot API", version="0.1.0")

# CORS for localhost UI & tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(metrics_router.router, prefix="/metrics", tags=["metrics"])
app.include_router(runs_router.router, prefix="/runs", tags=["runs"])
app.include_router(tasks_router.router, prefix="/tasks", tags=["tasks"])
app.include_router(policies_router.router, prefix="/policies", tags=["policies"])
app.include_router(usage_router.router, prefix="/usage", tags=["usage"])


@app.on_event("startup")
async def on_startup():
    init_db()
    # Start scheduler background worker
    get_scheduler()
