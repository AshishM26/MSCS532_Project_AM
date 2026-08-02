"""Demonstrate Phase 2/Phase 3 behavioral parity on committed data."""

import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import DeploymentReadinessEngine, OptimizedDeploymentReadinessEngine
from src import load_engine_from_csv, load_optimized_engine_from_csv


RESOURCES = PROJECT_ROOT / "data" / "phase2_cloud_resources.csv"
DEPENDENCIES = PROJECT_ROOT / "data" / "phase2_dependencies.csv"
SUMMARY_PATH = PROJECT_ROOT / "results" / "phase3_optimization_summary.json"


def _deploy_expected(engine, expected: str, order: list[str]) -> None:
    """Start and deploy one expected resource."""
    selected = engine.start_next_resource()
    if selected is None or selected[0] != expected:
        raise RuntimeError(f"expected {expected}, selected {selected}")
    engine.mark_deployed(expected)
    order.append(expected)


def _run_scenario(engine) -> dict[str, Any]:
    """Run the Phase 2 failure, retry, priority, and deployment sequence."""
    order: list[str] = []
    initial_summary = engine.summary()
    initial_eligible = engine.get_eligible_resources()
    first_selection = engine.select_next_resource()

    for expected in ("network-core", "identity-boundary"):
        _deploy_expected(engine, expected, order)

    failed = engine.start_next_resource()
    if failed is None or failed[0] != "secrets-store":
        raise RuntimeError(f"expected secrets-store, selected {failed}")
    engine.mark_failed("secrets-store")
    blocked = engine.get_readiness("backend-api")

    _deploy_expected(engine, "database-cluster", order)
    engine.update_priority("backup-policy", 1)
    for expected in (
        "backup-policy",
        "notification-topic",
        "monitoring-agent",
        "observability-dashboard",
    ):
        _deploy_expected(engine, expected, order)

    engine.retry_failed("secrets-store")
    waiting_after_retry = engine.get_readiness("backend-api").state.value
    _deploy_expected(engine, "secrets-store", order)
    ready_after_recovery = engine.get_readiness("backend-api").state.value
    for expected in ("backend-api", "frontend-service"):
        _deploy_expected(engine, expected, order)

    return {
        "initial_summary": initial_summary,
        "initial_eligible_resources": initial_eligible,
        "first_selection": list(first_selection) if first_selection else None,
        "blocked_state": blocked.state.value,
        "blocked_incomplete": list(blocked.incomplete_prerequisites),
        "blocked_failed": list(blocked.failed_prerequisites),
        "waiting_after_retry": waiting_after_retry,
        "ready_after_recovery": ready_after_recovery,
        "deployment_order": order,
        "final_summary": engine.summary(),
    }


def run_phase3_demo(*, verbose: bool = True) -> dict[str, Any]:
    """Compare both engines and write a reproducible parity summary."""
    baseline = load_engine_from_csv(RESOURCES, DEPENDENCIES)
    optimized = load_optimized_engine_from_csv(RESOURCES, DEPENDENCIES)
    baseline_result = _run_scenario(baseline)
    optimized_result = _run_scenario(optimized)

    parity_checks = {
        "initial_summary": (
            baseline_result["initial_summary"]
            == optimized_result["initial_summary"]
        ),
        "initial_eligible_resources": (
            baseline_result["initial_eligible_resources"]
            == optimized_result["initial_eligible_resources"]
        ),
        "first_selection": (
            baseline_result["first_selection"]
            == optimized_result["first_selection"]
        ),
        "failure_and_retry": all(
            baseline_result[key] == optimized_result[key]
            for key in (
                "blocked_state",
                "blocked_incomplete",
                "blocked_failed",
                "waiting_after_retry",
                "ready_after_recovery",
            )
        ),
        "deployment_order": (
            baseline_result["deployment_order"]
            == optimized_result["deployment_order"]
        ),
        "final_summary": (
            baseline_result["final_summary"]
            == optimized_result["final_summary"]
        ),
    }
    if not all(parity_checks.values()):
        raise RuntimeError(f"Phase 3 parity check failed: {parity_checks}")

    dependency_count = baseline_result["initial_summary"]["dependency_count"]
    baseline_counters = {
        "calculated_cycle_validations_during_load": dependency_count,
        "calculated_heap_rebuilds_during_scenario": 11,
        "resources_processed": 10,
    }
    optimized_counters = optimized.metrics.to_dict()
    summary = {
        "dataset": {
            "resource_count": 10,
            "dependency_count": dependency_count,
        },
        "parity_checks": parity_checks,
        "all_parity_checks_passed": all(parity_checks.values()),
        "failure_count_per_engine": 1,
        "retry_count_per_engine": 1,
        "priority_update_count_per_engine": 1,
        "deployment_order": baseline_result["deployment_order"],
        "all_deployed": baseline_result["final_summary"]["all_deployed"],
        "baseline_counters": baseline_counters,
        "optimized_counters": optimized_counters,
        "performance_claim": (
            "The small demo validates behavior only; benchmark artifacts "
            "provide the performance evidence."
        ),
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SUMMARY_PATH.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")

    if verbose:
        print("Phase 3 optimization parity demo")
        print("Resources: 10; dependencies: 9")
        print(
            "Initially eligible: "
            + ", ".join(baseline_result["initial_eligible_resources"])
        )
        print(f"First selection: {baseline_result['first_selection']}")
        print(
            "Failure/retry parity: "
            f"blocked={baseline_result['blocked_state']}, "
            f"after_retry={baseline_result['waiting_after_retry']}, "
            f"after_recovery={baseline_result['ready_after_recovery']}"
        )
        print(
            "Deployment order parity: "
            + " -> ".join(baseline_result["deployment_order"])
        )
        print(f"Baseline counters: {baseline_counters}")
        print(f"Optimized counters: {optimized_counters}")
        print("All behavioral parity checks passed: True")
        print(summary["performance_claim"])
        print(f"Summary written: {SUMMARY_PATH}")
    return summary


def main() -> None:
    """Run the committed-data Phase 3 demonstration."""
    run_phase3_demo()


if __name__ == "__main__":
    main()
