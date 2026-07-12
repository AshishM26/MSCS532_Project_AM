# Phase 1 Design

## Problem statement

A deployment platform must understand which services depend on others, reject
dependency definitions that cannot be scheduled, store operational metadata,
and select the most important service when several are ready. The Phase 1 model
solves these concerns in memory with a directed graph, a hash table, and a
binary heap. Its scope is generic and educational: it schedules identifiers but
does not communicate with a real cloud provider or execute deployments.

## Data structure responsibilities

### Directed adjacency-list graph

`DeploymentGraph` maintains both forward adjacency (prerequisite to dependents)
and reverse adjacency (dependent to prerequisites). Keeping both views costs
`O(V + E)` space but makes both relationship queries direct. Dictionary-backed
neighbor collections preserve insertion order and provide average `O(1)` edge
membership checks. Dependency endpoints are registered automatically. A
duplicate edge is rejected with `DuplicateDependencyError`.

Kahn's algorithm provides cycle detection and topological ordering. It is
iterative, avoids recursion-depth limits, and processes every vertex and edge
once. If fewer than `V` services are processed, a cycle prevents a valid order.

### Dictionary service registry

`ServiceRegistry` maps each `service_id` to its metadata record. Python's
dictionary is appropriate because service identifiers are unique keys and the
main operations are exact lookup, insertion, update, and deletion. Required
fields are validated, priorities must be 1 through 4, and missing updates raise
`KeyError`. Deep copies on input and output protect nested stored metadata from
unintended external mutation.

### Stable binary min-heap

`DeploymentPriorityQueue` stores `(priority, insertion_counter, service_id)`
internally. Because lower numbers represent greater urgency, Python's min-heap
selects the correct task directly. The counter breaks priority ties by arrival
order instead of comparing service names. Its public result is
`(service_id, priority)` so callers do not depend on the internal counter.

## Pseudocode

### Topological ordering

```text
TOPOLOGICAL-ORDER(graph):
    in_degree = number of prerequisites for each service
    eligible = queue of all services whose in_degree is zero
    order = empty list

    while eligible is not empty:
        prerequisite = remove front of eligible
        append prerequisite to order
        for each dependent of prerequisite:
            decrement in_degree[dependent]
            if in_degree[dependent] is zero:
                append dependent to eligible

    if length(order) is not number of services:
        raise DependencyCycleError
    return order
```

### Priority queue operations

```text
ENQUEUE(service_id, priority):
    validate service_id and priority
    entry = (priority, next insertion counter, service_id)
    push entry onto min-heap

PEEK():
    if heap is empty: return None
    read heap root without removing it
    return (root.service_id, root.priority)

DEQUEUE():
    if heap is empty: return None
    remove minimum entry from heap and restore heap order
    return (entry.service_id, entry.priority)
```

## Complexity summary

| Component | Operation | Time | Space impact |
|---|---|---:|---:|
| Graph | add service or dependency | `O(1)` average | `O(1)` |
| Graph | direct dependent/prerequisite query | `O(d)` | `O(d)` copy |
| Graph | cycle detection | `O(V + E)` | `O(V)` temporary |
| Graph | topological order | `O(V + E)` | `O(V)` output/temporary |
| Registry | register/get/update/remove/contains | `O(1)` average* | `O(1)`* |
| Registry | list all records | `O(n + m)` | `O(n + m)` copies |
| Priority queue | enqueue | `O(log n)` | `O(1)` entry |
| Priority queue | peek | `O(1)` | `O(1)` |
| Priority queue | dequeue | `O(log n)` | `O(1)` |

`*` Deep-copy time and space are proportional to the affected metadata record.
`V` is services, `E` dependencies, `d` direct degree, `n` records/tasks, and
`m` nested metadata content.

## Known limitations

- State is volatile and confined to one Python process.
- The graph and registry are separate; removing registry metadata does not
  automatically modify graph nodes or edges.
- The queue allows multiple entries for the same service because duplicate-task
  policy belongs to the scheduling layer.
- Priorities are static after enqueue; cancellation and decrease-key operations
  are not included.
- No locking is provided for concurrent readers and writers.
- The model does not handle deployment retries, rollback, health checks,
  resource capacity, or cross-environment policies.

## Later optimization opportunities

Phase 2 can add serialization, a thin interface, deployment state transitions,
integration tests, and richer error reporting. Phase 3 should first benchmark
large sparse and dense synthetic graphs. Based on measurements, it can explore
bulk graph loading, cached in-degree values, lazy deletion for reprioritization,
memory-reduced metadata representations, persistence, concurrency controls, and
incremental cycle detection. Stress tests and profiler output should quantify
the trade-offs before and after each optimization.
