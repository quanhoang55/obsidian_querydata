"""Frozen desktop sidecar entry point."""

from __future__ import annotations

import uvicorn

from backend.api.app import app
from backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=settings.port,
        log_level="info",
        access_log=False,
    )


if __name__ == "__main__":
    main()
