"""Demonstrate the Phase 1 deployment scheduling data structures."""

from pathlib import Path
import sys

# Allow this file to be run directly from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import DependencyCycleError, DeploymentGraph, DeploymentPriorityQueue
from src import ServiceRegistry


SERVICES = {
    "network-foundation": ("1.0.0", "platform", 1),
    "secrets-service": ("2.1.0", "security", 1),
    "database-service": ("15.4", "data", 2),
    "backend-api": ("3.2.0", "application", 2),
    "frontend-service": ("4.0.1", "application", 3),
    "monitoring-agent": ("1.8.2", "operations", 3),
    "observability-dashboard": ("2.4.0", "operations", 4),
}


def build_example() -> tuple[ServiceRegistry, DeploymentGraph]:
    """Build and return a generic registry and acyclic dependency graph."""
    registry = ServiceRegistry()
    graph = DeploymentGraph()

    for service_id, (version, owner, priority) in SERVICES.items():
        registry.register_service(
            service_id,
            {
                "environment": "staging",
                "version": version,
                "status": "pending",
                "owner": owner,
                "priority": priority,
            },
        )
        graph.add_service(service_id)

    dependencies = [
        ("network-foundation", "secrets-service"),
        ("network-foundation", "database-service"),
        ("secrets-service", "backend-api"),
        ("database-service", "backend-api"),
        ("backend-api", "frontend-service"),
        ("network-foundation", "monitoring-agent"),
        ("monitoring-agent", "observability-dashboard"),
    ]
    for prerequisite, dependent in dependencies:
        graph.add_dependency(prerequisite, dependent)
    return registry, graph


def schedule_eligible_tasks(
    registry: ServiceRegistry, graph: DeploymentGraph
) -> list[str]:
    """Simulate deployments while only queueing dependency-eligible tasks."""
    queue = DeploymentPriorityQueue()
    completed: set[str] = set()
    queued: set[str] = set()
    deployment_order: list[str] = []

    while len(completed) < len(registry.list_services()):
        for service in registry.list_services():
            service_id = service["service_id"]
            prerequisites = set(graph.get_prerequisites(service_id))
            if (
                service_id not in completed
                and service_id not in queued
                and prerequisites <= completed
            ):
                queue.enqueue(service_id, service["priority"])
                queued.add(service_id)
                print(f"  eligible: {service_id} (priority {service['priority']})")

        task = queue.dequeue()
        if task is None:
            raise DependencyCycleError("no eligible task remains; graph has a cycle")
        service_id, priority = task
        queued.remove(service_id)
        completed.add(service_id)
        deployment_order.append(service_id)
        registry.update_status(service_id, "deployed")
        print(f"  selected: {service_id} (priority {priority})")

    return deployment_order


def demonstrate_cycle_handling() -> None:
    """Show a cyclic input being rejected without ending the demo."""
    cyclic = DeploymentGraph()
    cyclic.add_dependency("service-a", "service-b")
    cyclic.add_dependency("service-b", "service-c")
    cyclic.add_dependency("service-c", "service-a")
    print(f"Cycle detected in invalid example: {cyclic.has_cycle()}")
    try:
        cyclic.topological_order()
    except DependencyCycleError as error:
        print(f"Invalid example handled safely: {error}")


def demonstrate_priority_ordering() -> None:
    """Show urgency ordering and deterministic equal-priority behavior."""
    queue = DeploymentPriorityQueue()
    queue.enqueue("frontend-service", 3)
    queue.enqueue("database-service", 2)
    queue.enqueue("backend-api", 2)
    queue.enqueue("network-foundation", 1)

    print("Standalone priority queue order:")
    while not queue.is_empty():
        print(f"  {queue.dequeue()}")
    print("  Equal-priority services retained insertion order: database then backend.")


def main() -> None:
    """Run the complete Phase 1 demonstration."""
    registry, graph = build_example()
    print(f"Registered {len(registry.list_services())} generic services.")
    print(f"Metadata lookup: {registry.get_service('database-service')}")
    registry.update_status("database-service", "validated")
    updated = registry.get_service("database-service")
    status = updated["status"] if updated else None
    print(f"Status update: database-service -> {status}")
    registry.update_status("database-service", "pending")
    print(
        "backend-api prerequisites: "
        f"{graph.get_prerequisites('backend-api')}"
    )
    print(
        "network-foundation dependents: "
        f"{graph.get_dependents('network-foundation')}"
    )
    print(f"Valid graph contains a cycle: {graph.has_cycle()}")
    print("Topological deployment order:")
    print("  " + " -> ".join(graph.topological_order()))
    print("\nPriority scheduling among currently eligible tasks:")
    selected = schedule_eligible_tasks(registry, graph)
    print("Priority-aware valid order:")
    print("  " + " -> ".join(selected))
    print()
    demonstrate_priority_ordering()
    print()
    demonstrate_cycle_handling()


if __name__ == "__main__":
    main()
