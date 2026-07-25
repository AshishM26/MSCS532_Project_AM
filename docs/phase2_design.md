# Phase 2 Proof-of-Concept Design

## 1. Phase 1 foundation

Phase 1 established three independent data structures:

- `DeploymentGraph` represents prerequisite relationships with forward and
  reverse adjacency lists.
- `ServiceRegistry` stores resource metadata and execution status in a
  dictionary.
- `DeploymentPriorityQueue` uses a stable binary min-heap to select the lowest
  numeric priority while preserving insertion order for ties.

This separation remains unchanged. The graph answers whether work is ready, the
registry stores current state, and the priority queue determines urgency among
ready resources.

## 2. Phase 2 objective

Phase 2 integrates the existing structures through
`DeploymentReadinessEngine`. The proof of concept loads generic cloud-resource
records and dependencies from CSV, derives readiness, validates transitions,
selects eligible resources, models failure and recovery, and produces
reproducible result files. It does not execute deployments or contact external
systems.

## 3. Why CSV data was selected

CSV makes the proof-of-concept inputs inspectable, reproducible, and independent
of external services. Python's `csv.DictReader` preserves the tabular metadata
model without adding dependencies. Separate resource and edge files also
maintain the Phase 1 distinction between registry records and graph
relationships. The trade-off is that CSV provides no transaction management or
schema types, so the loader must validate headers, blank values, priorities,
statuses, identifiers, duplicate rows, unknown endpoints, and cycles.

## 4. Integrated architecture

```text
Resource CSV + dependency CSV
              |
              v
     Cloud resource loader
              |
              v
 ServiceRegistry + DeploymentGraph
              |
              v
  DeploymentReadinessEngine
              |
              v
 DeploymentPriorityQueue (temporary)
              |
              v
 Execution trace CSV + summary JSON
```

The engine coordinates the structures through their public APIs. It does not
copy their internal dictionaries or heap. Resource registration writes to the
registry before adding the graph node, which prevents a graph-only record when
metadata validation fails. Dependency insertion requires registered endpoints.
If a new edge creates a cycle, the engine immediately removes that edge and
raises `DependencyCycleError`.

## 5. Readiness rules

Readiness is derived each time it is requested rather than persisted as a
status:

| Registry status and prerequisite condition | Readiness |
|---|---|
| `deployed` | `DEPLOYED` |
| `failed` | `FAILED` |
| `in_progress` | `IN_PROGRESS` |
| `pending` with a failed prerequisite | `BLOCKED` |
| `pending` with another incomplete prerequisite | `WAITING` |
| `pending` with all prerequisites deployed | `READY` |

A pending resource with no prerequisites is ready. A failed prerequisite does
not change the dependent's registry status; the dependent is blocked only as a
derived condition. After retry and successful deployment of the prerequisite,
the dependent can move from blocked or waiting to ready.

## 6. State-transition rules

The engine permits only:

```text
pending -> in_progress
in_progress -> deployed
in_progress -> failed
failed -> pending
```

`start_next_resource` performs the first transition.
`mark_deployed`, `mark_failed`, and `retry_failed` enforce the remaining
transitions. A deployed resource is terminal in Phase 2. Direct
pending-to-deployed transitions, retries of nonfailed resources, and changes
from deployed to failed are rejected.

## 7. Priority selection

`get_eligible_resources` scans registry records in insertion order and includes
only resources with derived `READY` state. `select_next_resource` rebuilds a
temporary `DeploymentPriorityQueue` from that list and current registry
priorities. The heap therefore selects the highest urgency, while its insertion
counter preserves registry order for equal priorities.

Rebuilding is intentionally simple and correct for this phase. A priority
update is visible on the next selection without stale queue entries, but
building the queue costs `O(r log r)` for `r` ready resources. Phase 3 can
compare this approach with an incremental heap or lazy invalidation.

## 8. Failure and recovery model

Only an in-progress resource can fail. A failure is stored on that resource;
dependents remain pending and derive a blocked state. `retry_failed` returns the
failed resource to pending. Its readiness is then recalculated from its own
prerequisites. This supports recovery without permanently propagating failure
through the graph.

The demonstration intentionally fails `secrets-store` once. `backend-api`
becomes blocked because one prerequisite failed. Independent resources continue
to deploy. After `secrets-store` is retried and deployed, `backend-api` becomes
ready.

## 9. Coordinated deletion

`DeploymentGraph.remove_dependency` updates forward and reverse adjacency
structures while retaining endpoint nodes. `remove_service` removes every
incoming and outgoing edge before deleting the node. The engine coordinates
graph and registry removal and rejects deletion of an in-progress resource.

Deleting a prerequisite can make former dependents ready because their edge no
longer exists. That behavior is acceptable for the current model, but a later
system would require authorization, audit history, and policy checks before
structural changes.

## 10. Loader validation

The loader constructs a private engine and returns it only after both files are
valid. It:

- requires every declared resource and dependency column;
- rejects blank required values and unnamed extra values;
- converts priority text to an integer from 1 through 4;
- requires initial status `pending`;
- rejects duplicate identifiers and dependency edges;
- rejects unknown prerequisite or dependent identifiers;
- rejects cycle-producing edges; and
- preserves additional named resource metadata.

Malformed rows are never silently skipped. An exception prevents the partially
constructed engine from becoming visible to the caller.

## 11. Complexity analysis

| Operation | Time | Notes |
|---|---:|---|
| Register resource | `O(1)` average* | Registry insert and graph-node insert |
| Insert dependency | `O(1) + O(V + E)` | Edge insert plus full cycle validation |
| Readiness for one resource | `O(p)` | `p` direct prerequisites |
| Scan all eligible resources | `O(V + E)` | All records and prerequisite checks |
| Build temporary ready heap | `O(r log r)` | `r` ready resources |
| Select after heap construction | `O(log r)` | Heap dequeue |
| Topological order | `O(V + E)` | Kahn's algorithm |
| Remove a graph resource | `O(i + o)` | Incoming degree `i`, outgoing degree `o` |
| Registry lookup/update | `O(1)` average* | Dictionary operation |

`*` Deep-copy cost is proportional to the metadata record. Dictionary
operations have a theoretical `O(n)` worst case under severe hash collisions.
The proof of concept does not hide the repeated cycle scans, readiness scans, or
heap rebuilding; these are measurable Phase 3 optimization candidates.

## 12. Testing strategy

The standard-library `unittest` suite contains 50 tests:

- 18 Phase 1 structure and registry tests, including new graph deletion cases;
- 14 readiness-engine tests;
- 13 strict loader tests; and
- 5 committed-dataset integration tests.

Tests verify forward/reverse graph consistency, cycle rollback, readiness
states, legal and illegal transitions, deterministic priority ties, failure and
retry, priority changes, coordinated deletion, malformed CSV variants,
topological correctness, and result-file serialization. Temporary directories
isolate generated test artifacts. No test depends on execution order.

## 13. Demonstration flow

The deterministic demo:

1. loads ten resources and nine edges;
2. prints lookup, traversal, cycle, and topological results;
3. shows two initially eligible resources and selects the critical one;
4. deploys the network and identity prerequisites;
5. fails `secrets-store` once and displays blocked `backend-api`;
6. deploys independent work;
7. changes `backup-policy` from priority 4 to 1 before selection;
8. retries and deploys `secrets-store`;
9. displays `backend-api` returning to ready;
10. deploys all ten resources; and
11. writes a 35-row trace and JSON summary.

## 14. Challenges and design changes

Phase 1 allowed graph edges to create missing endpoint nodes. Phase 2 still
preserves that graph behavior for compatibility, but the coordinator checks the
registry first so integrated dependencies cannot refer to unknown resources.
Cycle-safe insertion required rollback because graph insertion itself remains a
general-purpose operation. Derived readiness avoided a second mutable source of
truth. Rebuilding the heap solved stale-priority handling at the cost of
additional work. Strict CSV validation added an explicit boundary between
untrusted text input and the existing structures.

## 15. Current limitations

- State exists only for one process and is reset on each CSV load.
- There is no concurrency control or resource-capacity model.
- Priority values are fixed to four levels and do not express deadlines.
- Readiness checks and cycle validation rescan current structures.
- Trace writing is file-based and has no transaction or audit security.
- Deletion has no approval policy or historical tombstone.
- Failure is deterministic in the demo and does not model probability.
- The system coordinates identifiers but performs no deployment action.

## 16. Phase 3 optimization opportunities

Phase 3 should establish baselines with large synthetic sparse and dense graphs,
then profile cycle validation, readiness scanning, heap rebuilding, metadata
copying, and trace storage. Candidate changes include cached in-degree values,
incremental cycle detection, reverse readiness indexes, lazy heap invalidation,
bulk loading, compact record representations, and batched trace output. Each
change should be compared with the Phase 2 baseline for runtime, memory,
correctness, and implementation complexity.
