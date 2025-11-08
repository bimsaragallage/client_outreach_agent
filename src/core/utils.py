import time
import functools
from typing import Callable, Any
from src.core.logger import log
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
import os
from src.crew.outreach_lang_crew import CAMPAIGN_BASE_DIR, UPLOAD_DIR
CAMPAIGN_SUMMARY_FILE = "campaign_summary.json"

def retry_with_backoff(retries: int = 3, backoff_in_seconds: int = 1):
    """Retry decorator with exponential backoff."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            x = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if x == retries:
                        log.error(f"Failed after {retries} retries: {e}")
                        raise
                    else:
                        sleep_time = backoff_in_seconds * 2 ** x
                        log.warning(f"Retry {x+1}/{retries} after {sleep_time}s: {e}")
                        time.sleep(sleep_time)
                        x += 1
        return wrapper
    return decorator


def validate_email(email: str) -> bool:
    """Basic email validation."""

    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length with ellipsis."""
    
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def _read_json_file(path: Path) -> Any:
    """Reads and parses a JSON file."""
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            log.error(f"Error decoding JSON file: {path}")
            return None
    return None


def _get_campaign_summary(campaign_id: str) -> Optional[Dict]:
    """Retrieves a single campaign summary from file."""
    campaign_dir = CAMPAIGN_BASE_DIR / campaign_id
    summary_path = campaign_dir / CAMPAIGN_SUMMARY_FILE
    return _read_json_file(summary_path)


def _get_all_campaign_summaries() -> List[Dict]:
    """Retrieves all campaign summaries from campaign directories."""
    summaries = []
    for campaign_dir in CAMPAIGN_BASE_DIR.iterdir():
        if campaign_dir.is_dir():
            summary = _get_campaign_summary(campaign_dir.name)
            if summary:
                summaries.append(summary)
    return sorted(summaries, key=lambda x: x.get("timestamp", "0"), reverse=True)


def _get_latest_uploaded_leads_file() -> Optional[str]:
    """Finds the filename of the most recently uploaded leads JSON file."""
    try:
        if not UPLOAD_DIR.exists():
            return None
        
        json_files = [f for f in UPLOAD_DIR.iterdir() if f.suffix == '.json']
        
        if not json_files:
            return None
        
        # Sort files by modification time (most recent first)
        json_files.sort(key=os.path.getmtime, reverse=True)
        
        # Return only the filename (Path.name)
        return json_files[0].name
        
    except Exception as e:
        log.error(f"Error finding latest uploaded file: {e}")