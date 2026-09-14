"""
自定义异常层级：所有模块异常统一继承 GatewayError，便于上层统一捕获与兜底。
"""
from typing import Optional


class GatewayError(Exception):
    """网关所有异常的基类。"""

    def __init__(self, message: str = "", *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.message = message
        self.cause = cause


# --- 配置与基础设施（P0）---
class ConfigError(GatewayError):
    """配置加载 / 解析失败（文件缺失、YAML 语法错误、环境变量未设置等）。"""


class RegistryError(GatewayError):
    """可插拔注册表操作失败（实现未注册 / 重复注册 / 类型不符 / 参数不匹配）。"""


# --- 推理客户端层（P1）---
class ModelClientError(GatewayError):
    """推理客户端调用失败（网络、超时、鉴权、解析等）。"""


class ModelNotFoundError(ModelClientError):
    """请求的模型未注册或不可用。"""


class ModelTimeoutError(ModelClientError):
    """推理请求超时。"""


# --- 限流层（P1）---
class RateLimitError(GatewayError):
    """请求触发限流，应返回 HTTP 429。"""

    def __init__(self, message: str = "Rate limit exceeded", *, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


# --- 缓存层（P1）---
class CacheError(GatewayError):
    """缓存读写失败。"""


# --- 并发控制层（P1）---
class ConcurrencyError(GatewayError):
    """并发控制失败（超时、队列满等）。"""


# --- 监控层（P2）---
class MonitorError(GatewayError):
    """监控统计失败。"""


# --- 模型管理层（P2）---
class ModelManagerError(GatewayError):
    """模型管理操作失败（加载、卸载、切换等）。"""


# --- Prompt 管理层（P2）---
class PromptManagerError(GatewayError):
    """Prompt 管理操作失败。"""


class PromptNotFoundError(PromptManagerError):
    """Prompt 模板未找到。"""


class PromptVersionError(PromptManagerError):
    """Prompt 版本操作失败。"""


# --- 网关核心层（P3）---
class GatewayError_(GatewayError):
    """网关核心编排失败。"""
    # 注意：基类已叫 GatewayError，这里用别名避免冲突
    pass


# --- API 层（P4）---
class APIError(GatewayError):
    """API 层业务错误。"""
