import logging
import os
from datetime import datetime
from app.core.config import settings
 
def create_log_name():
    now = datetime.now()
    dt = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    return dt, timestamp
 
 
def setup_logger(name, log_file_name, level=logging.INFO):
    log_dir = os.path.dirname(log_file_name) or "."
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        fh = logging.FileHandler(log_file_name, encoding="utf-8")
        fh.setLevel(level)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger
 
 
# Module-level logger used by connections
dt, timestamp = create_log_name()
logger = setup_logger('default_logger', settings.LOGGER_PATH + f"app_{dt}.log")

