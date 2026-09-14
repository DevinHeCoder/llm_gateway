"""全局常量定义。"""
from pathlib import Path

# 项目根目录（src 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认配置文件路径
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"

# 环境变量前缀（用于配置覆盖）
ENV_PREFIX = "GATEWAY_"

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"

# 数据目录（SQLite 等）
DATA_DIR = PROJECT_ROOT / "data"
