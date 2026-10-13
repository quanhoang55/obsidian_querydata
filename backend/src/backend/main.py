"""Application entry point retained for the documented run command."""

from backend.api.app import app
from backend.config import get_settings


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=get_settings().port)
