"""
基础使用示例：直接使用 Gateway 核心类，不通过 HTTP API。

运行:
    python examples/basic_usage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.cache import build_cache
from src.concurrency import build_concurrency_controller
from src.gateway import Gateway, GatewayRequest
from src.model_client import ChatMessage, build_model_client
from src.rate_limiter import build_rate_limiter
from src.utils.config_loader import load_config
from src.utils.logger import get_logger

logger = get_logger("examples.basic_usage")


def main():
    # 加载配置
    config = load_config()

    # 组装各层组件（使用 Mock 客户端，无需真实 vLLM 服务）
    model_config = dict(config.get("model", {}))
    model_config["provider"] = "mock"  # 强制使用 Mock
    model_client = build_model_client(model_config)

    rate_limiter = build_rate_limiter(config.get("rate_limit", {}))
    cache_config = dict(config.get("cache", {}))
    cache_config["provider"] = "in_memory"  # 强制使用内存缓存
    cache = build_cache(cache_config)
    concurrency = build_concurrency_controller(config.get("concurrency", {}))

    # 创建 Gateway
    gateway = Gateway(
        model_client=model_client,
        rate_limiter=rate_limiter,
        cache=cache,
        concurrency=concurrency,
        config=config.get("gateway", {}),
    )

    # 构造请求
    request = GatewayRequest(
        messages=[
            ChatMessage(role="system", content="你是一个 helpful 的助手。"),
            ChatMessage(role="user", content="你好，请介绍一下你自己。"),
        ],
        model="mock-model",
        temperature=0.7,
        max_tokens=512,
        user="demo_user",
    )

    # 发送请求
    print("=" * 60)
    print("发送请求...")
    print("=" * 60)
    result = gateway.process(request)

    print(f"\n响应内容:\n{result.response.content}")
    print(f"\n统计信息:")
    print(f"  总耗时: {result.latency_ms:.2f} ms")
    print(f"  推理耗时: {result.inference_latency_ms:.2f} ms")
    print(f"  缓存耗时: {result.cache_latency_ms:.2f} ms")
    print(f"  来自缓存: {result.from_cache}")
    print(f"  Prompt tokens: {result.response.usage.prompt_tokens}")
    print(f"  Completion tokens: {result.response.usage.completion_tokens}")

    # 第二次请求（相同内容，测试缓存）
    print("\n" + "=" * 60)
    print("发送相同请求（测试缓存）...")
    print("=" * 60)
    result2 = gateway.process(request)
    print(f"  来自缓存: {result2.from_cache}")
    print(f"  总耗时: {result2.latency_ms:.2f} ms")

    # 网关统计
    print("\n" + "=" * 60)
    print("网关统计:")
    print("=" * 60)
    stats = gateway.stats
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 清理
    gateway.close()
    print("\n完成！")


if __name__ == "__main__":
    main()
