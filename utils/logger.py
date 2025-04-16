# utils/logger.py – Centralized logger with rotation and env-level control

import os
import logging
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'logs'))
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

LOG_PATH = os.path.join(LOG_DIR, 'poster_pipeline.log')

# Get log level from env (default: INFO)
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level, logging.INFO)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# File handler with rotation (2MB max, 5 backups)
file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2*1024*1024, backupCount=5)
file_handler.setFormatter(formatter)

# Stream handler (console)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

# Unified logger
logger = logging.getLogger("poster_pipeline")
logger.setLevel(log_level)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

# Silence overly verbose libraries (optional)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("tweepy").setLevel(logging.WARNING)
