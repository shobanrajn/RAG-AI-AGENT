import os
import glob
import logging
from datetime import date, timedelta


def get_log_dir() -> str:
    log_dir = os.getenv("LOGGER_PATH", os.path.join(os.path.dirname(__file__), "logs"))
    if not os.path.isabs(log_dir):
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        log_dir = os.path.join(project_root, log_dir)
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def make_log_handler(log_path: str, fmt: str) -> logging.FileHandler:
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    return handler


def get_faq_logger() -> logging.Logger:
    today = date.today().isoformat()
    logger = logging.getLogger(f"faq_agent_{today}")
    if logger.handlers:
        return logger
    log_path = os.path.join(get_log_dir(), f"faq_log_{today}.log")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(make_log_handler(log_path, "%(asctime)s | %(levelname)s | %(message)s"))
    logger.propagate = False
    return logger


def get_token_logger() -> logging.Logger:
    today = date.today().isoformat()
    logger = logging.getLogger(f"token_usage_{today}")
    if logger.handlers:
        return logger
    log_path = os.path.join(get_log_dir(), f"faq_token_usage_{today}.log")
    logger.setLevel(logging.INFO)
    logger.addHandler(make_log_handler(log_path, "%(message)s"))
    logger.propagate = False
    return logger


def cleanup_old_logs() -> None:
    retention_days = int(os.getenv("LOG_RETENTION_DAYS"))
    cutoff = date.today() - timedelta(days=retention_days)
    log_dir = get_log_dir()
    for pattern in ("faq_log_*.log", "faq_token_usage_*.log"):
        for filepath in glob.glob(os.path.join(log_dir, pattern)):
            fname = os.path.basename(filepath)
            date_part = fname.replace("faq_token_usage_", "").replace("faq_log_", "").replace(".log", "")
            try:
                if date.fromisoformat(date_part) < cutoff:
                    os.remove(filepath)
            except ValueError:
                pass


faq_log = get_faq_logger()
token_log = get_token_logger()

__all__ = ["faq_log", "token_log", "get_log_dir", "cleanup_old_logs"]
