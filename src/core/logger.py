from loguru import logger
import sys
from pathlib import Path
from src.core.config import settings


def setup_logger():
    """Configure application-wide logging."""
    
    # Remove default handler
    logger.remove()
    
    # Console handler with color
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.log_level,
        colorize=True
    )
    
    # File handler with rotation
    log_path = Path("logs")
    log_path.mkdir(exist_ok=True)
    
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        level=settings.log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )
    
    return logger


# Initialize logger
log = setup_logger()