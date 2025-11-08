#!/usr/bin/env python3
"""Client Outreach Agent - Minimal Entry Point (FastAPI + File Persistence)"""

import uvicorn
from pathlib import Path
from datetime import datetime
from src.core.logger import log
from src.core.config import settings
from src.api.main import app

# --- Directory Setup ---
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

log.info("=" * 60)
log.info("🚀 Starting Client Outreach System")
log.info("=" * 60)
log.info(f"Mode: {'🔴 DRY RUN' if settings.dry_run_mode else '🟢 PRODUCTION'}")
log.info(f"Persistence: File-Based ({DATA_DIR.resolve()})")
log.info(f"Timestamp: {datetime.now().isoformat()}")
log.info("=" * 60)


def start_api_server():
    """Start FastAPI server (main entry for all functions)."""
    try:
        log.info("✅ Initializing FastAPI app...")
        log.info("📡 Visit API Docs: http://localhost:8080/docs")
        uvicorn.run(app, host="0.0.0.0", port=8080)
    except Exception as e:
        log.error(f"❌ Failed to start API server: {e}", exc_info=True)


if __name__ == "__main__":
    start_api_server()