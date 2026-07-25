"""Run the deterministic Phase 2 cloud-resource proof of concept."""

import csv
import json
from pathlib import Path
import sys
from typing import Any

# Allow this file to be run directly from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src import DeploymentReadinessEngine, ReadinessState
from src import load_engine_from_csv


TRACE_COLUMNS = [
    "step",
    "service_id",
    "priority",
    "action",
    "previous_status",
    "new_status",
    "readiness_before",
    "outcome",
    "details",
]


def _record(
    trace: list[dict[str, object]],
    service_id: str,
    priority: int,
    action: str,
    previous_status: str,
    new_status: str,
    readiness_before: ReadinessState,
    outcome: str,
    details: str,
) -> None:
    """Append one numbered execution event."""
    trace.append(
        {
            "step": len(trace) + 1,
            "service_id": service_id,
            "priority": priority,
            "action": action,
            "previous_status": previous_status,
            "new_status": new_status,
            "readiness_before": readiness_before.value,
            "outcome": outcome,
            "details": details,
        }
    )


def _select_and_start(
    engine: DeploymentReadinessEngine,
    trace: list[dict[str, object]],
) -> tuple[str, int]:
    """Select and start the current highest-priority eligible resource."""
    selected = engine.select_next_resource()
    if selected is None:
        raise RuntimeError("no eligible resource is available")
    service_id, priority = selected
    readiness = engine.get_readiness(service_id).state
    resource = engine.get_resource(service_id)
    assert resource is not None
    previous_status = resource["status"]

    _record(
        trace,
        service_id,
        priority,
        "selected",
        previous_status,
        previous_status,
        readiness,
        "selected",
        "Highest-priority eligible resource selected.",
    )
    started = engine.start_next_resource()
    if started != selected:
        raise RuntimeError("selection changed unexpectedly before start")
    _record(
        trace,
        service_id,
        priority,
        "started",
        previous_status,
        "in_progress",
        readiness,
        "success",
        "Valid pending-to-in_progress transition.",
    )
    return selected


def _deploy_next(
    engine: DeploymentReadinessEngine,
    trace: list[dict[str, object]],
    deployment_order: list[str],
) -> str:
    """Start and successfully deploy the next eligible resource."""
    service_id, priority = _select_and_start(engine, trace)
    readiness = engine.get_readiness(service_id).state
    engine.mark_deployed(service_id)
    _record(
        trace,
        service_id,
        priority,
        "deployed",
        "in_progress",
        "deployed",
        readiness,
        "success",
        "Valid in_progress-to-deployed transition.",
    )
    deployment_order.append(service_id)
    return service_id


def _write_results(
    trace: list[dict[str, object]],
    summary: dict[str, Any],
    results_directory: Path,
) -> tuple[Path, Path]:
    """Write deterministic CSV and JSON result artifacts."""
    results_directory.mkdir(parents=True, exist_ok=True)
    trace_path = results_directory / "phase2_execution_trace.csv"
    summary_path = results_directory / "phase2_summary.json"

    with trace_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_COLUMNS)
        writer.writeheader()
        writer.writerows(trace)
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return trace_path, summary_path


def run_phase2_simulation(
    resources_path: str | Path = PROJECT_ROOT
    / "data"
    / "phase2_cloud_resources.csv",
    dependencies_path: str | Path = PROJECT_ROOT
    / "data"
    / "phase2_dependencies.csv",
    results_directory: str | Path = PROJECT_ROOT / "results",
    *,
    verbose: bool = True,
) -> dict[str, Any]:
    """Execute the complete failure, recovery, and deployment scenario."""
    engine = load_engine_from_csv(resources_path, dependencies_path)
    trace: list[dict[str, object]] = []
    deployment_order: list[str] = []
    initial_eligible = engine.get_eligible_resources()
    topological_order = engine.topological_order()
    starting_summary = engine.summary()

    database = engine.get_resource("database-cluster")
    assert database is not None
    initial_selection = engine.select_next_resource()

    if verbose:
        print(f"Loaded resources: {starting_summary['resource_count']}")
        print(f"Loaded dependencies: {starting_summary['dependency_count']}")
        print(
            "database-cluster metadata: "
            f"type={database['resource_type']}, region={database['region']}, "
            f"priority={database['priority']}, status={database['status']}"
        )
        print(
            "backend-api prerequisites: "
            f"{engine.graph.get_prerequisites('backend-api')}"
        )
        print(
            "network-core dependents: "
            f"{engine.graph.get_dependents('network-core')}"
        )
        print(f"Graph contains a cycle: {engine.graph.has_cycle()}")
        print("Topological order: " + " -> ".join(topological_order))
        print(f"Initially eligible: {initial_eligible}")
        print(f"Initial priority selection: {initial_selection}")

    for expected in ("network-core", "identity-boundary"):
        deployed = _deploy_next(engine, trace, deployment_order)
        if deployed != expected:
            raise RuntimeError(f"expected {expected}, selected {deployed}")

    failed_service, failed_priority = _select_and_start(engine, trace)
    if failed_service != "secrets-store":
        raise RuntimeError(
            f"expected secrets-store failure, selected {failed_service}"
        )
    failed_readiness = engine.get_readiness(failed_service).state
    engine.mark_failed(failed_service)
    _record(
        trace,
        failed_service,
        failed_priority,
        "failed",
        "in_progress",
        "failed",
        failed_readiness,
        "intentional_failure",
        "Synthetic one-time failure used to demonstrate recovery.",
    )

    blocked = engine.get_readiness("backend-api")
    blocked_example = {
        "service_id": blocked.service_id,
        "state": blocked.state.value,
        "incomplete_prerequisites": list(blocked.incomplete_prerequisites),
        "failed_prerequisites": list(blocked.failed_prerequisites),
    }
    if verbose:
        print(
            "Intentional failure: secrets-store -> failed; "
            f"backend-api -> {blocked.state.value}"
        )

    deployed = _deploy_next(engine, trace, deployment_order)
    if deployed != "database-cluster":
        raise RuntimeError(f"expected database-cluster, selected {deployed}")

    backup = engine.get_resource("backup-policy")
    assert backup is not None
    old_priority = backup["priority"]
    readiness = engine.get_readiness("backup-policy").state
    engine.update_priority("backup-policy", 1)
    _record(
        trace,
        "backup-policy",
        1,
        "priority_updated",
        "pending",
        "pending",
        readiness,
        "success",
        f"Priority changed from {old_priority} to 1 before selection.",
    )
    priority_updates = [
        {
            "service_id": "backup-policy",
            "previous_priority": old_priority,
            "new_priority": 1,
        }
    ]
    if verbose:
        print("Priority update: backup-policy 4 -> 1")

    independent_order = [
        "backup-policy",
        "notification-topic",
        "monitoring-agent",
        "observability-dashboard",
    ]
    for expected in independent_order:
        deployed = _deploy_next(engine, trace, deployment_order)
        if deployed != expected:
            raise RuntimeError(f"expected {expected}, selected {deployed}")

    retry_readiness = engine.get_readiness("secrets-store").state
    retry_resource = engine.get_resource("secrets-store")
    assert retry_resource is not None
    engine.retry_failed("secrets-store")
    _record(
        trace,
        "secrets-store",
        retry_resource["priority"],
        "retried",
        "failed",
        "pending",
        retry_readiness,
        "success",
        "Failed resource returned to pending for another attempt.",
    )
    if verbose:
        print("Recovery: secrets-store retried and returned to pending")

    for expected in ("secrets-store", "backend-api", "frontend-service"):
        deployed = _deploy_next(engine, trace, deployment_order)
        if deployed != expected:
            raise RuntimeError(f"expected {expected}, selected {deployed}")
        if expected == "secrets-store" and verbose:
            state = engine.get_readiness("backend-api").state.value
            print(f"After recovery: backend-api -> {state}")

    final_engine_summary = engine.summary()
    final_status_counts = {
        status: count
        for status, count in final_engine_summary["status_counts"].items()
        if count
    }
    summary = {
        "resource_count": final_engine_summary["resource_count"],
        "dependency_count": final_engine_summary["dependency_count"],
        "initial_eligible_resources": initial_eligible,
        "topological_order": topological_order,
        "deployment_order": deployment_order,
        "failure_count": 1,
        "retry_count": 1,
        "priority_updates": priority_updates,
        "all_deployed": engine.all_deployed(),
        "final_status_counts": final_status_counts,
        "blocked_example": blocked_example,
        "trace_row_count": len(trace),
        "test_command": "python3 -m unittest discover -s tests -v",
    }
    trace_path, summary_path = _write_results(
        trace,
        summary,
        Path(results_directory),
    )

    if verbose:
        print("Deployment order: " + " -> ".join(deployment_order))
        print(f"All resources deployed: {summary['all_deployed']}")
        print(f"Trace rows written: {len(trace)} -> {trace_path}")
        print(f"Summary written: {summary_path}")
    return summary


def main() -> None:
    """Run the committed-data Phase 2 demonstration."""
    run_phase2_simulation()


if __name__ == "__main__":
    main()
