"""
Performance monitoring utilities for API calls and operations
"""

import time
import logging
import functools
from typing import Dict, Any
from collections import defaultdict

logger = logging.getLogger(__name__)

# Performance metrics storage
_performance_metrics = defaultdict(list)


def monitor_performance(operation_name: str = None):
    """
    Decorator to monitor function performance and collect metrics

    Args:
        operation_name: Name of the operation for logging purposes
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Determine operation name
            op_name = operation_name or f"{func.__module__}.{func.__name__}"

            # Start timing
            start_time = time.time()
            start_memory = _get_memory_usage()

            try:
                # Execute function
                result = func(*args, **kwargs)

                # Calculate metrics
                execution_time = time.time() - start_time
                end_memory = _get_memory_usage()
                memory_delta = end_memory - start_memory

                # Store metrics
                _performance_metrics[op_name].append(
                    {
                        "execution_time": execution_time,
                        "memory_delta": memory_delta,
                        "timestamp": start_time,
                        "success": True,
                    }
                )

                # Log performance data
                logger.info(
                    f"PERF: {op_name} - {execution_time:.3f}s, "
                    f"Memory: {memory_delta:+.2f}MB"
                )

                return result

            except Exception as e:
                # Calculate metrics for failed operation
                execution_time = time.time() - start_time

                _performance_metrics[op_name].append(
                    {
                        "execution_time": execution_time,
                        "timestamp": start_time,
                        "success": False,
                        "error": str(e),
                    }
                )

                logger.error(
                    f"PERF ERROR: {op_name} - {execution_time:.3f}s, Error: {e}"
                )
                raise

        return wrapper

    return decorator


def _get_memory_usage() -> float:
    """Get current memory usage in MB"""
    try:
        import psutil

        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    except ImportError:
        # Fallback if psutil not available
        return 0.0


def get_performance_summary() -> Dict[str, Any]:
    """Get performance metrics summary"""
    summary = {}

    for op_name, metrics in _performance_metrics.items():
        if not metrics:
            continue

        successful = [m for m in metrics if m.get("success", False)]
        failed = [m for m in metrics if not m.get("success", False)]

        if successful:
            avg_time = sum(m["execution_time"] for m in successful) / len(successful)
            max_time = max(m["execution_time"] for m in successful)
            min_time = min(m["execution_time"] for m in successful)
            avg_memory = sum(m.get("memory_delta", 0) for m in successful) / len(
                successful
            )
        else:
            avg_time = max_time = min_time = avg_memory = 0

        summary[op_name] = {
            "total_calls": len(metrics),
            "successful_calls": len(successful),
            "failed_calls": len(failed),
            "success_rate": len(successful) / len(metrics) * 100 if metrics else 0,
            "avg_execution_time": avg_time,
            "max_execution_time": max_time,
            "min_execution_time": min_time,
            "avg_memory_delta": avg_memory,
        }

    return summary


def clear_performance_metrics():
    """Clear all performance metrics"""
    global _performance_metrics
    _performance_metrics.clear()
    logger.info("Performance metrics cleared")
