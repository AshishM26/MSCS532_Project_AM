"""Run reproducible Phase 2 baseline versus Phase 3 optimization benchmarks."""

import argparse
import csv
import json
from pathlib import Path
import platform
import sys
import tempfile
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.benchmark_helpers import (
    BENCHMARK_CSV_PATH,
    COMPARISON_OPERATIONS,
    CSV_FIELDS,
    RESULTS_DIRECTORY,
    STRESS_PROFILES,
    STRESS_SIZES,
    STRESS_SUMMARY_PATH,
    aggregate_measurements,
    build_engine_from_workload,
    create_memory_chart,
    create_runtime_chart,
    create_scaling_chart,
    deployment_order_hash,
    measure_call,
    peak_memory_call,
    selected_comparison_sizes,
    time_call,
    validate_deployment_order,
    validate_trials,
)
from src import ReadinessState
from src.bulk_cloud_resource_loader import load_optimized_engine_from_csv
from src.cloud_resource_loader import load_engine_from_csv
from src.synthetic_workload_generator import (
    WORKLOAD_PROFILES,
    SyntheticWorkload,
    generate_workload,
    write_workload_csv,
)


EngineFactory = Callable[[], Any]


def _deploy_all(engine, resource_count: int) -> list[str]:
    """Deploy an expected number of resources without an O(V) loop guard."""
    order: list[str] = []
    for _ in range(resource_count):
        selected = engine.start_next_resource()
        if selected is None:
            raise RuntimeError("scheduler stalled before complete deployment")
        service_id, _ = selected
        if service_id in order:
            raise RuntimeError(f"resource selected twice: {service_id}")
        engine.mark_deployed(service_id)
        order.append(service_id)
    if engine.start_next_resource() is not None or not engine.all_deployed():
        raise RuntimeError("scheduler did not reach a clean deployed state")
    return order


def _metrics(engine_name: str, engine, operation: str, workload) -> dict[str, int]:
    """Return measured optimized or explicitly calculated baseline counters."""
    if engine_name == "optimized":
        return engine.metrics.to_dict()
    heap_rebuilds = {
        "schedule_all": workload.resource_count + 1,
        "failure_recovery": 2,
        "priority_updates": 1,
    }.get(operation, 0)
    return {
        "full_cycle_validations": (
            workload.dependency_count if operation == "load" else 0
        ),
        "heap_rebuilds": heap_rebuilds,
        "heap_pushes": 0,
        "heap_pops": 0,
        "stale_heap_pops": 0,
        "dependent_updates": 0,
    }


def _operation_factory(
    engine_name: str,
    operation: str,
    workload: SyntheticWorkload,
    resource_path: Path,
    dependency_path: Path,
) -> Callable[[], tuple[Any, Any]]:
    """Create one measured operation returning its engine and parity value."""
    if operation == "load":
        loader = (
            load_engine_from_csv
            if engine_name == "baseline"
            else load_optimized_engine_from_csv
        )

        def load_operation():
            engine = loader(resource_path, dependency_path)
            return engine, None

        return load_operation

    def fresh_engine():
        return build_engine_from_workload(workload, engine_name)

    if operation == "schedule_all":
        engine = fresh_engine()

        def schedule_operation():
            order = _deploy_all(engine, workload.resource_count)
            return engine, tuple(order)

        return schedule_operation

    if operation == "eligibility_queries":
        engine = fresh_engine()

        def eligibility_operation():
            signature = None
            for _ in range(100):
                signature = tuple(engine.get_eligible_resources())
            return engine, signature

        return eligibility_operation

    if operation == "priority_updates":
        engine = fresh_engine()
        ready = engine.get_eligible_resources()
        if not ready:
            raise RuntimeError("priority benchmark requires a ready resource")

        def priority_operation():
            for index in range(100):
                service_id = ready[index % len(ready)]
                engine.update_priority(service_id, index % 4 + 1)
            return engine, engine.select_next_resource()

        return priority_operation

    if operation == "failure_recovery":
        controlled = generate_workload(2, "chain", seed=2532)
        engine = build_engine_from_workload(controlled, engine_name)
        prerequisite, dependent = controlled.dependencies[0]

        def recovery_operation():
            selected = engine.start_next_resource()
            if selected is None or selected[0] != prerequisite:
                raise RuntimeError("controlled prerequisite was not selected")
            engine.mark_failed(prerequisite)
            blocked = engine.get_readiness(dependent).state
            engine.retry_failed(prerequisite)
            waiting = engine.get_readiness(dependent).state
            selected = engine.start_next_resource()
            if selected is None or selected[0] != prerequisite:
                raise RuntimeError("retried prerequisite was not selected")
            engine.mark_deployed(prerequisite)
            ready = engine.get_readiness(dependent).state
            signature = (blocked.value, waiting.value, ready.value)
            expected = (
                ReadinessState.BLOCKED.value,
                ReadinessState.WAITING.value,
                ReadinessState.READY.value,
            )
            if signature != expected:
                raise RuntimeError(f"failure recovery mismatch: {signature}")
            return engine, signature

        return recovery_operation
    raise ValueError(f"unknown operation: {operation}")


def _measure_operation(
    engine_name: str,
    operation: str,
    workload: SyntheticWorkload,
    resource_path: Path,
    dependency_path: Path,
    trials: int,
) -> tuple[dict[str, Any], Any]:
    """Warm up, measure trials, and return statistics plus parity signature."""
    warmup = _operation_factory(
        engine_name, operation, workload, resource_path, dependency_path
    )
    warmup()
    times: list[float] = []
    signatures: list[Any] = []
    latest_engine = None
    for _ in range(trials):
        operation_call = _operation_factory(
            engine_name,
            operation,
            workload,
            resource_path,
            dependency_path,
        )
        elapsed, result = time_call(operation_call)
        latest_engine, signature = result
        if operation == "load":
            signature = (
                len(latest_engine.registry.list_services()),
                sum(
                    len(latest_engine.graph.get_dependents(row["service_id"]))
                    for row in workload.resources
                ),
                tuple(latest_engine.get_eligible_resources()),
                latest_engine.select_next_resource(),
            )
        times.append(elapsed)
        signatures.append(signature)
    memory_call = _operation_factory(
        engine_name,
        operation,
        workload,
        resource_path,
        dependency_path,
    )
    peak, memory_result = peak_memory_call(memory_call)
    latest_engine, memory_signature = memory_result
    if operation == "load":
        memory_signature = (
            len(latest_engine.registry.list_services()),
            sum(
                len(latest_engine.graph.get_dependents(row["service_id"]))
                for row in workload.resources
            ),
            tuple(latest_engine.get_eligible_resources()),
            latest_engine.select_next_resource(),
        )
    if memory_signature != signatures[0]:
        raise RuntimeError("memory trial produced a different result")
    if any(signature != signatures[0] for signature in signatures[1:]):
        raise RuntimeError("nondeterministic result across benchmark trials")
    assert latest_engine is not None
    values = aggregate_measurements(times, [peak] * len(times))
    values.update(_metrics(engine_name, latest_engine, operation, workload))
    return values, signatures[0]


def _case_deployment_validation(
    workload: SyntheticWorkload,
) -> tuple[str, bool]:
    """Validate exact deployment-order parity once per comparable case."""
    baseline = build_engine_from_workload(workload, "baseline")
    optimized = build_engine_from_workload(workload, "optimized")
    baseline_order = _deploy_all(baseline, workload.resource_count)
    optimized_order = _deploy_all(optimized, workload.resource_count)
    parity = baseline_order == optimized_order
    if not parity or not validate_deployment_order(baseline_order, workload):
        raise RuntimeError("deployment-order parity validation failed")
    if baseline.summary() != optimized.summary():
        raise RuntimeError("final summary parity validation failed")
    return deployment_order_hash(baseline_order), True


def run_comparison_benchmarks(
    trials: int = 5,
    max_size: int | None = None,
) -> list[dict[str, Any]]:
    """Run the complete comparable matrix and write its CSV and charts."""
    validate_trials(trials)
    sizes = selected_comparison_sizes(max_size)
    rows: list[dict[str, Any]] = []
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        for profile in WORKLOAD_PROFILES:
            for size in sizes:
                workload = generate_workload(size, profile, seed=532 + size)
                resource_path, dependency_path = write_workload_csv(
                    workload,
                    root / f"{profile}-{size}-resources.csv",
                    root / f"{profile}-{size}-dependencies.csv",
                )
                order_hash, all_deployed = _case_deployment_validation(workload)
                for operation in COMPARISON_OPERATIONS:
                    results: dict[str, tuple[dict[str, Any], Any]] = {}
                    for engine_name in ("baseline", "optimized"):
                        results[engine_name] = _measure_operation(
                            engine_name,
                            operation,
                            workload,
                            resource_path,
                            dependency_path,
                            trials,
                        )
                    parity = results["baseline"][1] == results["optimized"][1]
                    if not parity:
                        raise RuntimeError(
                            f"parity failed for {profile}/{size}/{operation}"
                        )
                    for engine_name in ("baseline", "optimized"):
                        measurements = results[engine_name][0]
                        rows.append(
                            {
                                "engine": engine_name,
                                "profile": profile,
                                "resource_count": size,
                                "dependency_count": workload.dependency_count,
                                "operation": operation,
                                "trial_count": trials,
                                "median_time_seconds": (
                                    f"{measurements['median_time_seconds']:.9f}"
                                ),
                                "mean_time_seconds": (
                                    f"{measurements['mean_time_seconds']:.9f}"
                                ),
                                "standard_deviation_seconds": (
                                    f"{measurements['standard_deviation_seconds']:.9f}"
                                ),
                                "minimum_time_seconds": (
                                    f"{measurements['minimum_time_seconds']:.9f}"
                                ),
                                "maximum_time_seconds": (
                                    f"{measurements['maximum_time_seconds']:.9f}"
                                ),
                                "peak_memory_bytes": measurements[
                                    "peak_memory_bytes"
                                ],
                                "deployment_order_hash": order_hash,
                                "all_deployed": all_deployed,
                                "parity_match": parity,
                                "full_cycle_validations": measurements[
                                    "full_cycle_validations"
                                ],
                                "heap_rebuilds": measurements["heap_rebuilds"],
                                "heap_pushes": measurements["heap_pushes"],
                                "heap_pops": measurements["heap_pops"],
                                "stale_heap_pops": measurements[
                                    "stale_heap_pops"
                                ],
                                "dependent_updates": measurements[
                                    "dependent_updates"
                                ],
                                "status": "completed",
                                "error_message": "",
                            }
                        )
                print(f"completed comparison: {profile}, {size} resources")

    with BENCHMARK_CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    create_runtime_chart(rows)
    create_memory_chart(rows)
    return rows


def run_stress_benchmarks() -> dict[str, Any]:
    """Run optimized build-and-schedule stress validation through 25,000."""
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    RESULTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for profile in STRESS_PROFILES:
        for size in STRESS_SIZES:
            workload = generate_workload(size, profile, seed=1532 + size)

            def stress_operation():
                engine = build_engine_from_workload(workload, "optimized")
                order = _deploy_all(engine, workload.resource_count)
                return engine, order

            try:
                elapsed, peak, result = measure_call(stress_operation)
                engine, order = result
                correct = (
                    validate_deployment_order(order, workload)
                    and engine.all_deployed()
                    and engine.validate_internal_state()
                    and len(set(order)) == size
                )
                if not correct:
                    raise RuntimeError("stress correctness validation failed")
                case = {
                    "profile": profile,
                    "resource_count": size,
                    "dependency_count": workload.dependency_count,
                    "runtime_seconds": round(elapsed, 9),
                    "peak_memory_bytes": peak,
                    "all_deployed": True,
                    "correctness_passed": True,
                    "deployment_order_hash": deployment_order_hash(order),
                    "maximum_heap_size": engine.metrics.maximum_heap_size,
                    "stale_heap_pops": engine.metrics.stale_heap_pops,
                    "index_rebuilds": engine.metrics.index_rebuilds,
                }
                cases.append(case)
                print(f"completed stress: {profile}, {size} resources")
            except (RuntimeError, ValueError, KeyError) as error:
                failures.append(
                    {
                        "profile": profile,
                        "resource_count": size,
                        "error": str(error),
                    }
                )
                raise

    summary = {
        "python_version": platform.python_version(),
        "platform": (
            f"{platform.system()} {platform.release()} "
            f"({platform.machine()})"
        ),
        "tested_sizes": list(STRESS_SIZES),
        "graph_profiles": list(STRESS_PROFILES),
        "measurement": "optimized engine construction and complete scheduling",
        "memory_definition": "maximum traced Python allocation per case",
        "cases": cases,
        "failures": failures,
        "all_cases_passed": not failures and len(cases) == 9,
    }
    with STRESS_SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    create_scaling_chart(cases)
    return summary


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line benchmark controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--max-size", type=int)
    parser.add_argument("--stress-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        validate_trials(arguments.trials)
        if not arguments.stress_only:
            selected_comparison_sizes(arguments.max_size)
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    return arguments


def main(argv: list[str] | None = None) -> None:
    """Run the selected comparable or optimized stress benchmark mode."""
    arguments = parse_arguments(argv)
    if arguments.stress_only:
        summary = run_stress_benchmarks()
        print(
            f"Stress cases: {len(summary['cases'])}; "
            f"all passed: {summary['all_cases_passed']}"
        )
        print(f"Stress summary: {STRESS_SUMMARY_PATH}")
    else:
        rows = run_comparison_benchmarks(
            trials=arguments.trials,
            max_size=arguments.max_size,
        )
        print(f"Comparable benchmark rows: {len(rows)}")
        print(f"Benchmark CSV: {BENCHMARK_CSV_PATH}")


if __name__ == "__main__":
    main()
