"""
API 客户端示例：通过 HTTP 调用 Gateway API。

先启动服务:
    uvicorn src.api.main:app --host 0.0.0.0 --port 9000

再运行:
    python examples/api_client_demo.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

BASE_URL = "http://localhost:9000"


def test_health():
    """测试健康检查端点。"""
    print("=" * 60)
    print("1. 健康检查")
    print("=" * 60)
    resp = httpx.get(f"{BASE_URL}/health", timeout=10)
    print(f"  状态码: {resp.status_code}")
    print(f"  响应: {json.dumps(resp.json(), indent=2, ensure_ascii=False)}")


def test_chat_completion():
    """测试聊天补全端点。"""
    print("\n" + "=" * 60)
    print("2. 聊天补全（非流式）")
    print("=" * 60)
    payload = {
        "model": "mock-model",
        "messages": [
            {"role": "system", "content": "你是一个 helpful 的助手。"},
            {"role": "user", "content": "你好，请介绍一下 LLM Gateway。"},
        ],
        "temperature": 0.7,
        "max_tokens": 512,
        "user": "demo_user",
    }
    resp = httpx.post(f"{BASE_URL}/v1/chat/completions", json=payload, timeout=30)
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  模型: {data['model']}")
        print(f"  响应: {data['choices'][0]['message']['content'][:200]}...")
        print(f"  Token 用量: {data['usage']}")
        print(f"  网关统计: {data.get('gateway', {})}")
    else:
        print(f"  错误: {resp.text}")


def test_stream_chat():
    """测试流式聊天补全。"""
    print("\n" + "=" * 60)
    print("3. 聊天补全（流式 SSE）")
    print("=" * 60)
    payload = {
        "model": "mock-model",
        "messages": [{"role": "user", "content": "写一首短诗。"}],
        "stream": True,
        "user": "demo_user",
    }
    with httpx.stream("POST", f"{BASE_URL}/v1/chat/completions", json=payload, timeout=30) as resp:
        print(f"  状态码: {resp.status_code}")
        print("  流式响应:")
        full_content = ""
        for line in resp.iter_lines():
            if line and line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_content += content
                        print(f"    {content}", end="", flush=True)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        print(f"\n  完整内容长度: {len(full_content)} 字符")


def test_system_info():
    """测试系统信息端点。"""
    print("\n" + "=" * 60)
    print("4. 系统信息")
    print("=" * 60)
    resp = httpx.get(f"{BASE_URL}/system/info", timeout=10)
    print(f"  状态码: {resp.status_code}")
    data = resp.json()
    print(f"  应用: {data['app']} v{data['version']}")
    print(f"  模型提供商: {data['model_provider']}")
    print(f"  限流器: {data['rate_limiter_provider']}")
    print(f"  缓存: {data['cache_provider']}")
    print(f"  并发控制: {data['concurrency_provider']}")
    print(f"  监控: {data['monitor_provider']}")


def test_metrics():
    """测试监控指标端点。"""
    print("\n" + "=" * 60)
    print("5. 监控指标")
    print("=" * 60)
    resp = httpx.get(f"{BASE_URL}/metrics/summary", timeout=10)
    print(f"  状态码: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  总请求数: {data['total_requests']}")
        print(f"  成功数: {data['success_count']}")
        print(f"  错误数: {data['error_count']}")
        print(f"  缓存命中率: {data['cache_hit_rate']:.2%}")
        print(f"  平均延迟: {data['avg_latency_ms']:.2f} ms")
        print(f"  P95 延迟: {data['p95_latency_ms']:.2f} ms")


def main():
    print("LLM Gateway API 客户端示例")
    print(f"服务地址: {BASE_URL}")
    print()

    try:
        test_health()
        test_chat_completion()
        test_stream_chat()
        test_system_info()
        test_metrics()
    except httpx.ConnectError:
        print(f"\n错误: 无法连接到 {BASE_URL}")
        print("请先启动服务: uvicorn src.api.main:app --host 0.0.0.0 --port 9000")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
