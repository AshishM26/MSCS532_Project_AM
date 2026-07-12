# Phase 1 Design

## 1. Problem statement

A deployment platform must understand which services depend on others, reject
dependency definitions that cannot be scheduled, store operational metadata,
and select the most important service when several are ready. Incorrect ordering
can cause a dependent service to start before a required capability exists,
while a circular dependency makes a complete deployment order impossible.

The Phase 1 model addresses these concerns in memory with a directed graph, a
hash table, and a binary heap. It is a generic Phase 1 implementation: it
schedules identifiers but does not contact a cloud provider or execute a real
deployment.

## 2. Application requirements

The model must:

- represent prerequisite-to-dependent relationships;
- retrieve either side of a direct dependency;
- detect circular dependencies and produce a valid topological order;
- validate and retrieve service metadata by a unique identifier;
- prevent callers from changing stored metadata accidentally;
- prioritize only eligible tasks from critical (1) to low (4); and
- resolve equal-priority ties predictably.

The design is intentionally modular, uses only the Python standard library, and
keeps persistence, external integration, and performance benchmarking outside
Phase 1.

## 3. Data-structure responsibilities

The graph determines **deployment readiness**, the registry stores **deployment
state**, and the priority queue determines **deployment urgency**. Separating
these questions prevents metadata policy or urgency from changing the logical
meaning of a dependency edge.

### Directed adjacency-list graph

`DeploymentGraph` maintains both forward adjacency (prerequisite to dependents)
and reverse adjacency (dependent to prerequisites). Dependency endpoints are
registered automatically, and `DuplicateDependencyError` rejects repeated
edges. Kahn's algorithm detects cycles and creates a topological order.

### Dictionary service registry

`ServiceRegistry` maps each `service_id` to metadata including environment,
version, status, owner, and priority. It validates required fields, rejects
invalid priorities, and raises `KeyError` for updates to unknown services. Deep
copies on input and output protect nested data from unintended mutation.

### Stable binary min-heap

`DeploymentPriorityQueue` stores `(priority, insertion_counter, service_id)`
internally. Lower numeric values represent greater urgency, so a min-heap
selects the appropriate item. The counter resolves equal-priority ties in
first-in, first-out order. Public results omit this implementation detail and
return `(service_id, priority)`.

## 4. Design rationale

Cloud-service graphs are normally sparse: each service depends on a small
subset of all other services. Forward and reverse adjacency lists therefore
store only relationships that exist while supporting both required queries.
Kahn's iterative algorithm processes every node and edge once and avoids the
recursion-depth risk of a recursive depth-first traversal.

A dictionary matches the registry's exact-key access pattern. It provides
average constant-time insertion, lookup, update, membership, and removal.
Python dictionaries also preserve insertion order, making listings predictable.
This performance is an average-case expectation; extreme hash collisions can
produce `O(n)` worst-case access. Copying metadata adds time proportional to the
record size but creates a safer public boundary.

A heap is appropriate because scheduling repeatedly needs the current minimum,
not a completely sorted collection. `heapq` provides logarithmic insertion and
removal with constant-time access to the root. The insertion counter adds stable
behavior without changing the asymptotic cost.

## 5. Alternative structures considered

### Adjacency list versus adjacency matrix

An adjacency matrix offers `O(1)` edge lookup but always consumes `O(V^2)`
space and requires scanning a row to enumerate neighbors. An adjacency list
uses `O(V + E)` space and enumerates a service's direct neighbors in `O(d)`
time. Because a sparse deployment model has far fewer edges than `V^2`, the
adjacency list is more space-efficient and traversal-friendly.

### Dictionary versus list-based lookup

A list of metadata records would use a simple representation, but locating,
updating, or removing a service by identifier would require an `O(n)` scan.
The dictionary directly represents unique identifiers and gives average
`O(1)` access. Its trade-offs are hashing overhead and theoretical `O(n)`
worst-case behavior under severe collisions.

### Heap-based queue versus fully sorted list

A sorted list provides `O(1)` access to one end but requires `O(n)` insertion
to find a position and shift elements. An unsorted list reverses the trade-off:
cheap insertion but `O(n)` selection. A heap keeps both enqueue and dequeue at
`O(log n)` and peek at `O(1)`, which better suits repeated scheduling.

## 6. Time and space complexity analysis

| Component | Operation | Time | Space impact |
|---|---|---:|---:|
| Graph | add service | `O(1)` average | `O(1)` |
| Graph | add dependency | `O(1)` average | `O(1)` |
| Graph | retrieve direct neighbors | `O(d)` | `O(d)` returned copy |
| Graph | cycle detection | `O(V + E)` | `O(V)` temporary |
| Graph | topological order | `O(V + E)` | `O(V)` output/temporary |
| Graph | complete structure | -- | `O(V + E)` |
| Registry | keyed operations | `O(1)` average, `O(n)` worst* | `O(1)`* |
| Registry | list all records | `O(n + m)` | `O(n + m)` copies |
| Registry | complete structure | -- | `O(n + m)` |
| Priority queue | enqueue | `O(log n)` | `O(1)` entry |
| Priority queue | peek | `O(1)` | `O(1)` |
| Priority queue | dequeue | `O(log n)` | `O(1)` |
| Priority queue | complete structure | -- | `O(n)` |

`*` Copying time and space are proportional to the affected metadata record.
`V` is services, `E` dependencies, `d` direct degree, `n` records or tasks, and
`m` total nested metadata content.

## 7. Pseudocode

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
    remove minimum entry and restore heap order
    return (entry.service_id, entry.priority)
```

## 8. Python implementation overview

The `src` package contains one class per module and exports the public classes
and graph exceptions from `src/__init__.py`. Type hints document public method
contracts. Validation rejects blank identifiers, incomplete records, invalid
priorities, duplicate services, and duplicate dependency edges. The demo builds
a seven-service generic graph, schedules only services whose prerequisites are
complete, and catches an intentional cycle. Standard-library `unittest` cases
verify normal behavior, edge cases, error handling, and stable heap ordering.

## 9. Challenges and limitations

- Graph state and registry state can become inconsistent because the structures
  deliberately have no integrated coordinator.
- Metadata can become stale because no external system refreshes it.
- The queue permits duplicate service tasks; duplicate policy belongs to a
  future scheduling layer.
- Priorities cannot be changed in place after enqueue.
- Dynamic edge changes require cycle detection to be run again.
- No locks protect concurrent readers and writers.
- Very large graphs may make repeated full topological traversals expensive.
- The model does not persist state or execute retries, rollback, health checks,
  capacity policies, or deployments.

## 10. Future optimization and research directions

Phase 2 can introduce an integrated readiness engine, explicit state
transitions, serialization, dynamic priority updates, and more integration
tests. Phase 3 should benchmark progressively larger sparse and dense graphs
before selecting optimizations. Candidate research topics include cached or
memoized prerequisite results, bulk graph loading, incremental cycle detection,
lazy heap deletion for reprioritization, compact metadata representations,
graph database storage, and concurrency control.

Longer-term directions may examine CI/CD and Kubernetes integration, cloud API
integration, distributed scheduling, risk scoring, and AI-assisted deployment
analysis. They are research opportunities only and are not part of this Phase 1
implementation.
