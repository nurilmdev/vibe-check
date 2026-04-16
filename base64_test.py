import base64
from loguru import logger

logger.info(base64.urlsafe_b64encode("R@h4s!a".encode('utf-8')))