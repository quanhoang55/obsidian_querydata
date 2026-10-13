"""FastAPI application factory and route registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.endpoints.routes import router

app = FastAPI(
    title="Obsidian Querydata API",
    version="0.1.0",
    description="Local API for querying an Obsidian vault.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
