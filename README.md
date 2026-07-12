# Cloud-Native Deployment Dependency and Priority Scheduling System

**Student:** Ashish Mahajan<br>
**Course:** MSCS 532 - Algorithms and Data Structures<br>
**Assignment:** Developing and Optimizing Data Structures for Real-World Applications Using Python

## Application context

Cloud-native platforms often need to deploy services in an order constrained by
dependencies. A database, for example, must be available before an API that uses
it. At the same time, multiple services may be eligible for deployment, so the
platform needs a predictable way to select the most important task.

This project is a generic educational model of that problem. It contains no
employer-specific systems, proprietary applications, or internal architecture.

Repository URL: <https://github.com/AshishM26/MSCS532_Project_AM>

## Architecture and data structure rationale

- `DeploymentGraph` uses a directed adjacency list. An edge from `A` to `B`
  means that A is a prerequisite of B. Adjacency lists use `O(V + E)` space and
  are efficient for the sparse dependency graphs common in service platforms.
- `ServiceRegistry` uses Python dictionaries (hash tables) for direct access to
  service metadata. Values are deep-copied at the class boundary to prevent
  callers from mutating stored records unintentionally.
- `DeploymentPriorityQueue` uses `heapq`, a binary min-heap. Priorities range
  from 1 (critical) to 4 (low), so the smallest value is selected first. An
  insertion counter makes equal-priority processing deterministic.

The graph automatically registers either endpoint of a new dependency. Adding
an existing edge raises `DuplicateDependencyError`; asking for a topological
order when a cycle exists raises `DependencyCycleError`.

## Expected complexity

| Operation | Expected time | Extra/structure space |
|---|---:|---:|
| Add graph service | `O(1)` average | `O(1)` |
| Add dependency | `O(1)` average | `O(1)` |
| List direct neighbors | `O(d)` | `O(d)` returned copy |
| Cycle detection | `O(V + E)` | `O(V)` |
| Topological ordering | `O(V + E)` | `O(V)` |
| Registry lookup/update/remove | `O(1)` average | record-dependent copy |
| Registry listing | `O(n + m)` | `O(n + m)` returned copies |
| Queue enqueue/dequeue | `O(log n)` | `O(1)` per entry |
| Queue peek/size/empty check | `O(1)` | `O(1)` |

Here, `V` is the number of services, `E` the dependencies, `d` a node's direct
degree, `n` the number of records/tasks, and `m` the total nested metadata size.

## Repository structure

```text
MSCS532_Project_AM/
├── README.md
├── docs/
│   └── phase1_design.md
├── examples/
│   └── phase1_demo.py
├── src/
│   ├── __init__.py
│   ├── deployment_graph.py
│   ├── deployment_priority_queue.py
│   └── service_registry.py
├── tests/
│   ├── test_deployment_graph.py
│   ├── test_deployment_priority_queue.py
│   └── test_service_registry.py
└── requirements.txt
```

## Setup and execution

Python 3.10 or later is recommended. The project has no third-party runtime
dependencies.

```bash
git clone https://github.com/AshishM26/MSCS532_Project_AM.git
cd MSCS532_Project_AM
python3 -m venv .venv
source .venv/bin/activate
python3 examples/phase1_demo.py
```

Run all tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

## Project scope

### Phase 1 - design and foundation

Phase 1 defines the application context and implements the three foundational
data structures. It includes validation, cycle detection, deterministic
scheduling, a runnable demonstration, unit tests, pseudocode, and complexity
analysis. The implementation is deliberately in-memory and single-process.

### Phase 2 - proof of concept

Phase 2 can integrate the structures behind a small command-line or REST
interface, add persistence/serialization, model deployment completion and
failure states, expand edge-case testing, and document measured test results
and implementation challenges.

### Phase 3 - optimization and scaling

Phase 3 can generate large synthetic dependency graphs, benchmark time and
memory, compare topological-sorting strategies, profile bottlenecks, add bulk
operations, evaluate concurrency controls, and report before/after performance
with tables and graphs. These optimizations should be driven by measurements
rather than added prematurely.

## Known boundaries

This educational foundation does not execute real deployments, persist data,
coordinate multiple processes, retry failed tasks, or provide authentication.
See [the Phase 1 design](docs/phase1_design.md) for detailed rationale,
pseudocode, limitations, and future optimization opportunities.