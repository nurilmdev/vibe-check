import os
import sys
from loguru import logger
from config import settings


def setup_logger():
    """Konfigurasi loguru logger dengan output ke console dan file."""
    os.makedirs("logs", exist_ok=True)

    # Hapus default handler
    logger.remove()

    # Console output
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File output (rotasi setiap 10MB, simpan 7 hari)
    logger.add(
        "logs/automation.log",
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
    )

    logger.success("Logger initialized. Level: {}", settings.LOG_LEVEL)
