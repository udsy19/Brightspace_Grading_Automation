import sys
from pathlib import Path
from loguru import logger

# Remove default stderr handler completely to ensure clean stdout for Rich TUI
logger.remove()

# Add a robust file handler that rotates automatically
LOG_FILE = Path(__file__).parent / "brightspace_grader.log"

logger.add(
    LOG_FILE,
    rotation="5 MB",
    retention="2 days",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    backtrace=True,
    diagnose=True,
)
