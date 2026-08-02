"""Shared measurement, validation, aggregation, and chart helpers."""

import hashlib
import os
from pathlib import Path
import statistics
import tempfile
import time
import tracemalloc
from typing import Any, Callable

from src.deployment_graph import DeploymentGraph
from src.deployment_readiness_engine import DeploymentReadinessEngine
from src.optimized_deployment_readiness_engine import (
    OptimizedDeploymentReadinessEngine,
)
from src.service_registry import ServiceRegistry
from src.synthetic_workload_generator import SyntheticWorkload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIRECTORY = PROJECT_ROOT / "results"
BENCHMARK_CSV_PATH = RESULTS_DIRECTORY / "phase3_benchmark_results.csv"
RUNTIME_CHART_PATH = RESULTS_DIRECTORY / "phase3_runtime_comparison.png"
MEMORY_CHART_PATH = RESULTS_DIRECTORY / "phase3_memory_comparison.png"
SCALING_CHART_PATH = RESULTS_DIRECTORY / "phase3_scaling_chart.png"
STRESS_SUMMARY_PATH = RESULTS_DIRECTORY / "phase3_stress_summary.json"

COMPARISON_SIZES = (100, 500, 1000, 2000)
STRESS_SIZES = (5000, 10000, 25000)
STRESS_PROFILES = ("chain", "layered_sparse", "wide_independent")
COMPARISON_OPERATIONS = (
    "load",
    "schedule_all",
    "eligibility_queries",
    "failure_recovery",
    "priority_updates",
)
CSV_FIELDS = (
    "engine",
    "profile",
    "resource_count",
    "dependency_count",
    "operation",
    "trial_count",
    "median_time_seconds",
    "mean_time_seconds",
    "standard_deviation_seconds",
    "minimum_time_seconds",
    "maximum_time_seconds",
    "peak_memory_bytes",
    "deployment_order_hash",
    "all_deployed",
    "parity_match",
    "full_cycle_validations",
    "heap_rebuilds",
    "heap_pushes",
    "heap_pops",
    "stale_heap_pops",
    "dependent_updates",
    "status",
    "error_message",
)


def validate_trials(trials: int) -> int:
    """Return a valid positive trial count."""
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise ValueError("trials must be a positive integer")
    return trials


def selected_comparison_sizes(max_size: int | None) -> tuple[int, ...]:
    """Filter configured comparison sizes by an optional inclusive maximum."""
    if max_size is None:
        return COMPARISON_SIZES
    if not isinstance(max_size, int) or isinstance(max_size, bool):
        raise TypeError("max_size must be an integer or None")
    selected = tuple(size for size in COMPARISON_SIZES if size <= max_size)
    if not selected:
        raise ValueError("max_size must include at least size 100")
    return selected


def deployment_order_hash(order: list[str]) -> str:
    """Return a deterministic SHA-256 digest for a deployment order."""
    return hashlib.sha256("\n".join(order).encode("utf-8")).hexdigest()


def validate_deployment_order(
    order: list[str], workload: SyntheticWorkload
) -> bool:
    """Check uniqueness, coverage, and every prerequisite ordering rule."""
    if len(order) != workload.resource_count or len(set(order)) != len(order):
        return False
    position = {service_id: index for index, service_id in enumerate(order)}
    expected = {row["service_id"] for row in workload.resources}
    if set(position) != expected:
        return False
    return all(
        position[prerequisite] < position[dependent]
        for prerequisite, dependent in workload.dependencies
    )


def build_engine_from_workload(
    workload: SyntheticWorkload,
    engine_name: str,
):
    """Build an untimed fresh engine without exercising either CSV loader."""
    graph = DeploymentGraph()
    registry = ServiceRegistry()
    for row in workload.resources:
        service_id = row["service_id"]
        metadata: dict[str, Any] = {
            key: value for key, value in row.items() if key != "service_id"
        }
        metadata["priority"] = int(row["priority"])
        registry.register_service(service_id, metadata)
        graph.add_service(service_id)
    for prerequisite, dependent in workload.dependencies:
        graph.add_dependency(prerequisite, dependent)
    if engine_name == "baseline":
        return DeploymentReadinessEngine(graph, registry)
    if engine_name == "optimized":
        return OptimizedDeploymentReadinessEngine(graph, registry)
    raise ValueError(f"unknown engine: {engine_name}")


def measure_call(function: Callable[[], Any]) -> tuple[float, int, Any]:
    """Measure elapsed time and peak traced Python allocation for one call."""
    tracemalloc.start()
    start = time.perf_counter()
    try:
        result = function()
    finally:
        elapsed = time.perf_counter() - start
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return elapsed, peak_memory, result


def time_call(function: Callable[[], Any]) -> tuple[float, Any]:
    """Measure runtime without allocation-tracing instrumentation overhead."""
    start = time.perf_counter()
    result = function()
    return time.perf_counter() - start, result


def peak_memory_call(function: Callable[[], Any]) -> tuple[int, Any]:
    """Measure peak traced Python allocation in a separate execution."""
    tracemalloc.start()
    try:
        result = function()
    finally:
        _, peak_memory = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return peak_memory, result


def aggregate_measurements(
    times: list[float], peak_memories: list[int]
) -> dict[str, float | int]:
    """Summarize repeated measurements with descriptive statistics."""
    if not times or len(times) != len(peak_memories):
        raise ValueError("times and peak_memories must be nonempty and aligned")
    standard_deviation = statistics.stdev(times) if len(times) > 1 else 0.0
    return {
        "median_time_seconds": statistics.median(times),
        "mean_time_seconds": statistics.mean(times),
        "standard_deviation_seconds": standard_deviation,
        "minimum_time_seconds": min(times),
        "maximum_time_seconds": max(times),
        "peak_memory_bytes": max(peak_memories),
    }


def _chart_rows(rows: list[dict[str, Any]], operation: str):
    return [
        row
        for row in rows
        if row["operation"] == operation and row["status"] == "completed"
    ]


def _pyplot():
    cache = Path(tempfile.gettempdir()) / "mscs532-matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    return plt


def create_runtime_chart(
    rows: list[dict[str, Any]], output_path: Path = RUNTIME_CHART_PATH
) -> Path:
    """Plot baseline and optimized schedule runtime by graph profile."""
    plt = _pyplot()
    profiles = ("chain", "layered_sparse", "layered_dense", "wide_independent")
    figure, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    for axis, profile in zip(axes.flat, profiles):
        for engine in ("baseline", "optimized"):
            selected = sorted(
                (
                    row
                    for row in _chart_rows(rows, "schedule_all")
                    if row["profile"] == profile and row["engine"] == engine
                ),
                key=lambda row: int(row["resource_count"]),
            )
            axis.plot(
                [int(row["resource_count"]) for row in selected],
                [float(row["median_time_seconds"]) for row in selected],
                marker="o",
                label=engine,
            )
        axis.set_title(profile.replace("_", " ").title())
        axis.set_xlabel("Resources")
        axis.set_ylabel("Median seconds")
        axis.grid(alpha=0.25)
        axis.legend()
    figure.suptitle("Schedule-All Runtime: Baseline vs Optimized")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return output_path


def create_memory_chart(
    rows: list[dict[str, Any]], output_path: Path = MEMORY_CHART_PATH
) -> Path:
    """Plot peak traced schedule allocation by graph profile."""
    plt = _pyplot()
    profiles = ("chain", "layered_sparse", "layered_dense", "wide_independent")
    figure, axes = plt.subplots(2, 2, figsize=(11, 8), sharex=True)
    for axis, profile in zip(axes.flat, profiles):
        for engine in ("baseline", "optimized"):
            selected = sorted(
                (
                    row
                    for row in _chart_rows(rows, "schedule_all")
                    if row["profile"] == profile and row["engine"] == engine
                ),
                key=lambda row: int(row["resource_count"]),
            )
            axis.plot(
                [int(row["resource_count"]) for row in selected],
                [float(row["peak_memory_bytes"]) / (1024 * 1024)
                 for row in selected],
                marker="o",
                label=engine,
            )
        axis.set_title(profile.replace("_", " ").title())
        axis.set_xlabel("Resources")
        axis.set_ylabel("Peak traced MiB")
        axis.grid(alpha=0.25)
        axis.legend()
    figure.suptitle("Schedule-All Peak Python Allocation")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return output_path


def create_scaling_chart(
    stress_cases: list[dict[str, Any]],
    output_path: Path = SCALING_CHART_PATH,
) -> Path:
    """Plot optimized build-and-schedule stress growth by profile."""
    plt = _pyplot()
    figure, axis = plt.subplots(figsize=(9, 6))
    for profile in STRESS_PROFILES:
        selected = sorted(
            (
                case for case in stress_cases if case["profile"] == profile
            ),
            key=lambda case: int(case["resource_count"]),
        )
        axis.plot(
            [int(case["resource_count"]) for case in selected],
            [float(case["runtime_seconds"]) for case in selected],
            marker="o",
            label=profile.replace("_", " "),
        )
    axis.set_title("Optimized Build-and-Schedule Stress Scaling")
    axis.set_xlabel("Resources")
    axis.set_ylabel("Seconds")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=160)
    plt.close(figure)
    return output_path
