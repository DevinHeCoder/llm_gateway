"""
A/B 测试管理器：Prompt 版本的 A/B 实验流量分配与指标对比。

支持按 user_id hash 稳定分流（同一用户始终命中同一版本），
按百分比分配流量，并基于监控指标进行版本对比。
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("gateway.prompt_manager.ab_testing")


@dataclass
class ABTestVariant:
    """A/B 测试变体。

    属性:
        name: 变体名称（如 "A", "B", "control"）
        prompt_name: 关联的 Prompt 模板名称
        prompt_version: 关联的 Prompt 版本号
        traffic_percent: 流量百分比（0-100）
        description: 变体描述
    """

    name: str
    prompt_name: str
    prompt_version: str
    traffic_percent: float = 50.0
    description: str = ""


@dataclass
class ABTest:
    """A/B 测试实验。

    属性:
        id: 实验 ID
        name: 实验名称
        description: 实验描述
        variants: 变体列表
        status: 实验状态（running / paused / completed）
        created_at: 创建时间戳
        started_at: 开始时间戳
        ended_at: 结束时间戳
        metrics: 实验指标（按变体分组）
    """

    id: str
    name: str
    description: str = ""
    variants: List[ABTestVariant] = field(default_factory=list)
    status: str = "running"  # running / paused / completed
    created_at: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class ABTestResult:
    """A/B 测试结果对比。

    属性:
        test_id: 实验 ID
        test_name: 实验名称
        status: 实验状态
        variant_results: 各变体的指标结果
        winner: 胜出变体（如果有）
        confidence: 置信度（0-1）
    """

    test_id: str
    test_name: str
    status: str
    variant_results: Dict[str, Dict[str, Any]]
    winner: Optional[str] = None
    confidence: float = 0.0


class ABTestManager:
    """A/B 测试管理器。

    负责实验的创建、管理、流量分配和指标对比。
    流量分配基于 user_id 的 hash 值，保证同一用户始终命中同一变体。
    """

    def __init__(self) -> None:
        self._tests: Dict[str, ABTest] = {}
        self._lock = threading.Lock()
        logger.info("ABTestManager 初始化")

    # ---------------- 实验管理 ----------------

    def create_test(
        self,
        name: str,
        variants: List[ABTestVariant],
        description: str = "",
        test_id: Optional[str] = None,
    ) -> ABTest:
        """创建新的 A/B 测试实验。

        参数:
            name: 实验名称
            variants: 变体列表（流量百分比之和应为 100）
            description: 实验描述
            test_id: 实验 ID，为空时自动生成

        返回:
            创建的 ABTest 对象
        """
        # 校验流量百分比
        total_percent = sum(v.traffic_percent for v in variants)
        if abs(total_percent - 100.0) > 0.01:
            raise ValueError(
                f"变体流量百分比之和应为 100，当前为 {total_percent:.1f}"
            )

        if test_id is None:
            test_id = f"abtest_{int(time.time() * 1000)}"

        now = time.time()
        test = ABTest(
            id=test_id,
            name=name,
            description=description,
            variants=variants,
            status="running",
            created_at=now,
            started_at=now,
            metrics={v.name: {"requests": 0, "latency_ms": [], "tokens": 0, "errors": 0} for v in variants},
        )

        with self._lock:
            self._tests[test_id] = test

        logger.info("创建 A/B 测试: %s (%s), %d 个变体", name, test_id, len(variants))
        return test

    def get_test(self, test_id: str) -> Optional[ABTest]:
        """获取实验信息。"""
        with self._lock:
            return self._tests.get(test_id)

    def list_tests(self, status: Optional[str] = None) -> List[ABTest]:
        """列出所有实验。"""
        with self._lock:
            tests = list(self._tests.values())
            if status:
                tests = [t for t in tests if t.status == status]
            return sorted(tests, key=lambda t: t.created_at, reverse=True)

    def pause_test(self, test_id: str) -> bool:
        """暂停实验。"""
        with self._lock:
            test = self._tests.get(test_id)
            if test is None:
                return False
            test.status = "paused"
        logger.info("暂停 A/B 测试: %s", test_id)
        return True

    def resume_test(self, test_id: str) -> bool:
        """恢复实验。"""
        with self._lock:
            test = self._tests.get(test_id)
            if test is None:
                return False
            test.status = "running"
        logger.info("恢复 A/B 测试: %s", test_id)
        return True

    def complete_test(self, test_id: str) -> bool:
        """完成实验。"""
        with self._lock:
            test = self._tests.get(test_id)
            if test is None:
                return False
            test.status = "completed"
            test.ended_at = time.time()
        logger.info("完成 A/B 测试: %s", test_id)
        return True

    def delete_test(self, test_id: str) -> bool:
        """删除实验。"""
        with self._lock:
            if test_id in self._tests:
                del self._tests[test_id]
                logger.info("删除 A/B 测试: %s", test_id)
                return True
            return False

    # ---------------- 流量分配 ----------------

    def assign_variant(self, test_id: str, user_id: str) -> Optional[ABTestVariant]:
        """为用户分配实验变体。

        基于 user_id 的 hash 值稳定分配，同一用户始终命中同一变体。

        参数:
            test_id: 实验 ID
            user_id: 用户标识

        返回:
            分配的变体，实验不存在或已暂停时返回 None
        """
        with self._lock:
            test = self._tests.get(test_id)
            if test is None or test.status != "running":
                return None

            # 计算用户 hash 值（0-100）
            hash_val = int(hashlib.md5(f"{test_id}:{user_id}".encode()).hexdigest(), 16) % 10000 / 100.0

            # 按流量百分比分配
            cumulative = 0.0
            for variant in test.variants:
                cumulative += variant.traffic_percent
                if hash_val < cumulative:
                    return variant

            # 边界情况：返回最后一个变体
            return test.variants[-1] if test.variants else None

    def get_variant_for_prompt(self, prompt_name: str, user_id: str) -> Optional[Tuple[ABTest, ABTestVariant]]:
        """获取指定 Prompt 正在运行的实验变体。

        参数:
            prompt_name: Prompt 模板名称
            user_id: 用户标识

        返回:
            (实验, 变体) 元组，没有运行中的实验时返回 None
        """
        with self._lock:
            for test in self._tests.values():
                if test.status != "running":
                    continue
                for variant in test.variants:
                    if variant.prompt_name == prompt_name:
                        assigned = self.assign_variant(test.id, user_id)
                        if assigned is not None:
                            return test, assigned
        return None

    # ---------------- 指标记录与对比 ----------------

    def record_metric(
        self,
        test_id: str,
        variant_name: str,
        *,
        latency_ms: float = 0.0,
        tokens: int = 0,
        error: bool = False,
    ) -> None:
        """记录实验指标。

        参数:
            test_id: 实验 ID
            variant_name: 变体名称
            latency_ms: 请求延迟（毫秒）
            tokens: 生成 token 数
            error: 是否出错
        """
        with self._lock:
            test = self._tests.get(test_id)
            if test is None:
                return
            if variant_name not in test.metrics:
                test.metrics[variant_name] = {"requests": 0, "latency_ms": [], "tokens": 0, "errors": 0}

            metrics = test.metrics[variant_name]
            metrics["requests"] += 1
            if latency_ms > 0:
                metrics["latency_ms"].append(latency_ms)
            metrics["tokens"] += tokens
            if error:
                metrics["errors"] += 1

    def get_test_result(self, test_id: str) -> Optional[ABTestResult]:
        """获取实验结果对比。

        计算各变体的平均延迟、token 数、错误率，并简单判断胜出变体。

        参数:
            test_id: 实验 ID

        返回:
            ABTestResult 结果对象
        """
        with self._lock:
            test = self._tests.get(test_id)
            if test is None:
                return None

            variant_results: Dict[str, Dict[str, Any]] = {}
            for variant in test.variants:
                metrics = test.metrics.get(variant.name, {})
                requests = metrics.get("requests", 0)
                latencies = metrics.get("latency_ms", [])
                errors = metrics.get("errors", 0)
                total_tokens = metrics.get("tokens", 0)

                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                error_rate = errors / requests if requests > 0 else 0
                avg_tokens = total_tokens / requests if requests > 0 else 0

                variant_results[variant.name] = {
                    "prompt_name": variant.prompt_name,
                    "prompt_version": variant.prompt_version,
                    "traffic_percent": variant.traffic_percent,
                    "requests": requests,
                    "avg_latency_ms": round(avg_latency, 2),
                    "avg_tokens": round(avg_tokens, 2),
                    "total_tokens": total_tokens,
                    "errors": errors,
                    "error_rate": round(error_rate, 4),
                }

            # 简单判断胜出变体：错误率低且延迟低的胜出
            winner = None
            confidence = 0.0
            if len(variant_results) >= 2:
                # 按错误率升序、延迟升序排序
                sorted_variants = sorted(
                    variant_results.items(),
                    key=lambda x: (x[1]["error_rate"], x[1]["avg_latency_ms"]),
                )
                best = sorted_variants[0]
                second = sorted_variants[1]
                # 简单置信度：基于请求量和指标差异
                min_requests = min(best[1]["requests"], second[1]["requests"])
                if min_requests >= 10:
                    confidence = min(0.95, 0.5 + min_requests / 100.0)
                    winner = best[0]

            return ABTestResult(
                test_id=test.id,
                test_name=test.name,
                status=test.status,
                variant_results=variant_results,
                winner=winner,
                confidence=round(confidence, 4),
            )
