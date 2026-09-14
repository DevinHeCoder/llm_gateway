"""
日志工具：基于 logging 模块，支持 YAML 配置文件初始化。

典型用法::

    from src.utils.logger import get_logger
    logger = get_logger("gateway.api")
    logger.info("请求处理完成")
"""
from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Optional

import yaml

from src.common.constants import LOG_DIR, PROJECT_ROOT
from src.common.exceptions import ConfigError

_DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": str(LOG_DIR / "gateway.log"),
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 5,
            "encoding": "utf-8",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"],
    },
    "loggers": {
        "uvicorn": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "httpx": {"level": "WARNING", "handlers": ["console"], "propagate": False},
    },
}

_initialized = False


def setup_logging(config_path: Optional[str] = None) -> None:
    """初始化日志配置。

    参数:
        config_path: logging.yaml 配置文件路径；为空时使用默认配置。
    """
    global _initialized

    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if config_path:
        path = Path(config_path)
        if not path.is_file():
            raise ConfigError(f"日志配置文件不存在: {path}")
        try:
            with path.open("r", encoding="utf-8") as f:
                log_cfg = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"解析日志配置失败 ({path}): {e}") from e
    else:
        log_cfg = _DEFAULT_LOGGING_CONFIG

    logging.config.dictConfig(log_cfg)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """获取命名 logger；首次调用时自动初始化默认日志配置。"""
    global _initialized
    if not _initialized:
        setup_logging()
    return logging.getLogger(name)
