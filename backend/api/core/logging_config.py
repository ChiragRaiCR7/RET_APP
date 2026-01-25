import sys
from loguru import logger
from api.core.config import settings

def configure_logging():
    logger.remove()

    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time}</green> | <level>{level}</level> | {message}",
    )
