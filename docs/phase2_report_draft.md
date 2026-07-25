# Phase 2 Report Draft

## Title and student information

**Cloud-Native Deployment Dependency and Priority Scheduling System**<br>
Ashish Mahajan<br>
Student ID: 005048542<br>
University of the Cumberlands<br>
MSCS 532-B01 - Algorithms and Data Structures<br>
Project Phase 2 Deliverable 2 - Proof of Concept Implementation<br>
Dr. Michael Solomon<br>
Submission date: `[MONTH DAY, YEAR]`

## Partial Implementation Overview

The proof of concept implemented a coordinated deployment-readiness workflow on
top of the graph, hash table, and binary heap developed in Phase 1. The
implementation loads ten synthetic cloud-resource records and nine dependency
edges from CSV files, validates the input, determines which resources are ready,
selects the most urgent eligible resource, controls execution-state changes,
and records reproducible results. The resource names and metadata are generic,
and the program does not contact a cloud platform or execute deployment
commands.

This scope demonstrates insertion, lookup, traversal, deletion, cycle
validation, priority selection, failure handling, and recovery. These operations
connect directly to workflow-system research. Yu and Buyya (2005) identify
workflow structure, task dependencies, and scheduling as central dimensions of
workflow systems. Deelman et al. (2015) likewise describe directed acyclic
graphs (DAGs) as a practical representation of tasks and their data or control
dependencies. These findings support the decision to retain an adjacency-list
DAG as the structural foundation.

## Integration with the Phase 1 Design

Phase 1 separated three concerns: the graph determines readiness, the registry
stores state, and the priority queue determines urgency. Phase 2 preserves that
separation through `DeploymentReadinessEngine`, which coordinates the existing
public APIs instead of copying their internal storage. A resource is registered
in `ServiceRegistry` and added as a graph node. A dependency can be added only
when both endpoints are registered. The engine checks the graph after insertion
and removes the new edge if it creates a cycle, preventing a partial invalid
change.

The engine also coordinates deletion. Removing a resource deletes its incoming
and outgoing graph edges and its registry record, while removal of an
in-progress resource is rejected. This extension demonstrates deletion without
changing Phase 1 method meanings. The design remains modular: graph algorithms,
metadata access, heap behavior, and orchestration can be tested independently.

## Cloud-Resource Dataset

Two committed CSV files provide reproducible inputs. The resource file contains
ten records with identifiers, types, environment, version, status, owner,
priority, region, and criticality. The dependency file contains nine directed
edges. `notification-topic` has no prerequisites, which creates two initially
eligible resources and makes priority selection observable.

The loader uses `csv.DictReader` and validates required headers, blank values,
priority conversion and range, initial status, duplicate identifiers, duplicate
edges, unknown endpoints, and cycles. It constructs a private engine and returns
it only after all rows pass. CSV was selected for transparency and portability,
but it lacks a typed schema and transaction support; explicit validation is
therefore essential.

## Readiness and State-Transition Implementation

Readiness is calculated rather than saved as another mutable status. A pending
resource is `READY` when every prerequisite is deployed, `WAITING` when a
nonfailed prerequisite is incomplete, and `BLOCKED` when any prerequisite has
failed. Deployed, failed, and in-progress resources map directly to corresponding
readiness states. This arrangement prevents failure from being copied into every
dependent record. When a failed prerequisite is retried and deployed, affected
resources become ready through recalculation.

The permitted transitions are pending to in progress, in progress to deployed
or failed, and failed back to pending through retry. Deployed is terminal in
this phase. State-aware execution reflects the broader need for reliable
workflow management: Deelman et al. (2015) discuss runtime failure handling and
job retry as workflow reliability mechanisms. At a larger scale, Verma et al.
(2015) describe cluster-management support for monitoring, scheduling, and
fault recovery, reinforcing the importance of separating declared work from
runtime state.

Eligible resources are scanned in registry insertion order and placed into a
temporary min-heap. Lower numeric priority means greater urgency, and an
insertion counter preserves first-in, first-out order for ties. Topcuoglu et al.
(2002) demonstrate that precedence constraints and task ranking are fundamental
to effective DAG scheduling. This proof of concept uses a simpler fixed-priority
policy, but it similarly separates dependency eligibility from the choice among
eligible tasks.

## Demonstration and Testing

The demonstration loaded 10 resources and 9 dependencies. It reported an
acyclic graph and the following valid topological order: network-core,
notification-topic, identity-boundary, database-cluster, monitoring-agent,
secrets-store, backup-policy, observability-dashboard, backend-api, and
frontend-service. The initially eligible resources were network-core and
notification-topic; priority selected network-core first.

The demonstration intentionally failed secrets-store once. Backend-api became
blocked, while independent work continued. After database-cluster deployed,
backup-policy was changed from priority 4 to priority 1 before selection, and
the next rebuilt heap immediately reflected the update. Secrets-store was then
retried, deployed successfully, and backend-api became ready. The final
priority-aware deployment order was network-core, identity-boundary,
database-cluster, backup-policy, notification-topic, monitoring-agent,
observability-dashboard, secrets-store, backend-api, and frontend-service.
All 10 resources reached deployed status.

The test suite produced 50 passing tests with no failures or errors. Tests cover
the three original structures, graph deletion, cycle rollback, readiness,
transitions, deterministic ties, failure and retry, priority updates,
coordinated deletion, malformed CSV cases, committed-data integration, and
result serialization. The demo wrote 35 trace rows to CSV and a JSON summary
that records one failure, one retry, one priority update, and
`all_deployed: true`.

## Implementation Challenges and Solutions

The first challenge was preserving Phase 1 behavior while requiring stronger
integrated validation. `DeploymentGraph.add_dependency` still registers missing
nodes for compatibility, but the engine checks registry membership before
calling it. The second challenge was rejecting a cycle without leaving the new
edge behind; immediate edge removal provides rollback. The third was preventing
stale readiness and priority data. Readiness is derived from current statuses,
and the ready heap is rebuilt for every selection. This costs additional time
but keeps priority changes correct and avoids complicated heap mutation.

Failure propagation required another deliberate choice. Marking every dependent
failed would lose the distinction between the cause and its effects. The engine
instead leaves dependents pending and derives `BLOCKED`. Recovery then occurs
naturally when the prerequisite returns to pending and later reaches deployed.

## Critical Code Snippets

The central readiness decision distinguishes failure from ordinary incomplete
work:

```python
if failed:
    state = ReadinessState.BLOCKED
elif incomplete:
    state = ReadinessState.WAITING
else:
    state = ReadinessState.READY
```

Current priorities are respected by rebuilding the eligible heap:

```python
queue = DeploymentPriorityQueue()
for service_id in self.get_eligible_resources():
    resource = self._require_resource(service_id)
    queue.enqueue(service_id, resource["priority"])
return queue.dequeue()
```

Failure and retry use controlled registry transitions:

```python
self.registry.update_status(service_id, "failed")
# After validation that the resource is failed:
self.registry.update_status(service_id, "pending")
```

## Current Limitations

The proof of concept is single-process and in-memory. CSV input is reproducible
but does not provide transactions, concurrent updates, or durable state. Cycle
validation scans the full graph after each edge insertion. Eligibility scans
all resources and prerequisites, and each selection rebuilds the ready heap.
The four-level priority scale omits deadlines, resource capacity, and fairness.
Deletion has no approval or audit policy. Failures are modeled as explicit demo
events rather than probabilistic infrastructure behavior.

## Next Steps for Phase 3

Phase 3 should measure these costs before optimizing them. Synthetic sparse and
dense graphs can establish runtime and memory baselines for loading, cycle
validation, readiness scans, topological ordering, and repeated selection.
Potential experiments include cached in-degree data, incremental cycle
detection, reverse readiness indexes, lazy heap invalidation, bulk loading, and
batched trace output. The comparison should report both improvements and added
complexity. The taxonomy by Yu and Buyya (2005), scalable workflow experience
reported by Deelman et al. (2015), scheduling work by Topcuoglu et al. (2002),
and cluster-management lessons from Verma et al. (2015) provide research
directions without implying that the current small proof of concept matches
large distributed systems.

## Conclusion

Phase 2 converts the three Phase 1 data structures into a working,
state-aware proof of concept. Strict loading, cycle rollback, derived readiness,
priority selection, controlled transitions, failure recovery, coordinated
deletion, tests, and reproducible outputs demonstrate the critical operations.
The results also expose measurable inefficiencies that create a clear and
honest baseline for Phase 3 optimization.

## References

Deelman, E., Vahi, K., Juve, G., Rynge, M., Callaghan, S., Maechling, P. J.,
Mayani, R., Chen, W., Ferreira da Silva, R., Livny, M., & Wenger, K. (2015).
Pegasus, a workflow management system for science automation. *Future
Generation Computer Systems, 46*, 17–35.
https://doi.org/10.1016/j.future.2014.10.008

Topcuoglu, H., Hariri, S., & Wu, M.-Y. (2002). Performance-effective and
low-complexity task scheduling for heterogeneous computing. *IEEE Transactions
on Parallel and Distributed Systems, 13*(3), 260–274.
https://doi.org/10.1109/71.993206

Verma, A., Pedrosa, L., Korupolu, M., Oppenheimer, D., Tune, E., & Wilkes, J.
(2015). Large-scale cluster management at Google with Borg. In *Proceedings of
the Tenth European Conference on Computer Systems* (Article 18, pp. 1–17).
https://doi.org/10.1145/2741948.2741964

Yu, J., & Buyya, R. (2005). A taxonomy of scientific workflow systems for grid
computing. *ACM SIGMOD Record, 34*(3), 44–49.
https://doi.org/10.1145/1084805.1084814

## GitHub repository link

<https://github.com/AshishM26/MSCS532_Project_AM>
