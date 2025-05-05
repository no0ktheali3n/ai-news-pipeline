# utils/logger.py – AWS Lambda-compatible enhanced logging (dynamic log levels, development = DEBUG, production less verbose INFO))

import os
import logging

def get_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    
    # Clear any existing handlers to avoid duplication
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler()
    
    # Create formatter
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Set log level based on environment
    env = os.getenv("ENVIRONMENT", "production").lower()
    if env == "development":
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    
    # IMPORTANT: Set propagate to True to allow logs to reach the root logger
    logger.propagate = False
    
    return logger