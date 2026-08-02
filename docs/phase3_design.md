# Phase 3 Optimization, Scaling, and Final Evaluation Design

## 1. Phase 1 and Phase 2 foundation

Phase 1 established three independent structures: an adjacency-list directed
graph for prerequisites, a dictionary-backed metadata registry, and a stable
binary min-heap for priorities. Phase 2 retained those structures and added
`DeploymentReadinessEngine`, strict CSV loading, execution-state transitions,
failure/retry behavior, coordinated deletion, and deterministic output. The
committed Phase 2 baseline has 50 passing tests and processes 10 generic
resources, 9 dependencies, and 35 trace events to an all-deployed result.

## 2. Phase 3 objective

Phase 3 preserves the Phase 2 engine as the comparison baseline and adds
`OptimizedDeploymentReadinessEngine`. The objective is identical observable
scheduling behavior with less repeated work at scale. The optimized engine
uses incremental prerequisite indexes, a persistent versioned heap, and a
validate-first bulk loader. Deterministic synthetic workloads, five-trial
comparisons, allocation tracing, charts, parity tests, and optimized stress
runs provide reproducible evidence.

## 3. Measured Phase 2 bottlenecks

The baseline has several candidate costs. It validates the complete graph after
every dependency insertion, recalculates each resource's direct prerequisite
states during eligibility scans, and rebuilds a heap from all ready resources
for every selection. Safe registry copies add record-size overhead. The full
benchmark confirmed that these combined costs become measured bottlenecks.

At 2,000 resources, baseline `schedule_all` median time ranged from 39.324634208
seconds for the wide-independent graph to 94.765168250 seconds for the layered
dense graph. Baseline load time also rose with edge count: 0.763360791 seconds
for the chain, 1.817780334 for layered sparse, and 5.502345541 for layered dense.
The zero-edge wide case loaded in only 0.013519542 seconds, demonstrating that
the baseline loader is not universally slow.

## 4. Baseline preservation strategy

The original `DeploymentReadinessEngine` and `load_engine_from_csv` remain
unchanged. Benchmarks call their public behavior rather than substituting an
approximation. The optimized class subclasses the baseline only to retain the
same public method contract; it owns separate derived indexes while the graph
and registry remain authoritative. Phase 1 and Phase 2 files, data, demos,
results, and documentation remain available.

## 5. Incremental readiness design

The optimized engine records registry insertion position and maintains, for
each resource, sets of incomplete and failed prerequisite IDs. Ordered
dictionary companions preserve the graph's deterministic prerequisite order in
public readiness results. A ready-membership set records pending resources with
no incomplete prerequisites.

When a resource deploys, only its direct dependents are changed. Its ID is
removed from their incomplete and failed sets, and newly ready dependents are
inserted into the heap. Failure adds the prerequisite to each direct
dependent's failed set but does not mark the dependents failed. Retry removes
only that failed marker and leaves the prerequisite incomplete until successful
deployment. This preserves the Phase 2 READY, WAITING, BLOCKED, IN_PROGRESS,
DEPLOYED, and FAILED meanings.

`rebuild_indexes()` reconstructs all derived state from the graph and registry.
`validate_internal_state()` independently recomputes expected indexes and
selection to detect drift during tests and stress validation.

## 6. Persistent heap and lazy invalidation

Each heap entry is `(priority, insertion_position, generation, service_id)`.
Lower numeric priority wins, followed by earlier registry insertion. A priority
update increments the resource generation and pushes a replacement entry when
the resource is ready. The old entry remains but is rejected when it reaches
the root because its generation or priority is stale. Each stale entry can be
popped only once.

`select_next_resource()` cleans stale roots and peeks without changing state.
`start_next_resource()` cleans, pops the valid root, removes ready membership,
and transitions the resource to in progress. Lazy invalidation avoids an O(n)
heap search but may temporarily retain stale entries. `rebuild_indexes()` is a
controlled way to compact all derived heap state if a future long-running use
case requires it.

## 7. Bulk loading

`bulk_cloud_resource_loader.py` first parses and validates every resource and
dependency record. Sets detect duplicate service IDs and edges, and every edge
endpoint is checked before graph mutation. Private graph and registry objects
are then populated, followed by one topological validation and one index build.
If validation fails, no engine is returned. The baseline loader continues to
perform one complete cycle check per edge.

At 2,000 resources the optimized loader was 22.99 times faster for the chain,
39.08 times for layered sparse, and 74.17 times for layered dense. It was slower
for the zero-edge wide graph (0.030106125 versus 0.013519542 seconds) because
building indexes has a fixed cost when there are no repeated cycle checks to
remove.

## 8. Synthetic graph profiles

The deterministic generator uses `random.Random` and stable IDs. A chain has
`E = V - 1` and ready width near one. Layered sparse graphs assign one to three
previous-layer prerequisites; layered dense graphs assign one to eight.
Wide-independent graphs have no edges and all resources initially ready. These
profiles separate narrow dependency propagation, increasing fan-in, and heap
width effects without using external or proprietary data.

## 9. Benchmark methodology

Comparable sizes are 100, 500, 1,000, and 2,000 resources for all four
profiles. Each engine and case measures load, complete scheduling, 100
eligibility queries, a controlled two-node failure/recovery sequence, and 100
deterministic priority updates. This creates 160 rows: 2 engines × 4 profiles ×
4 sizes × 5 operations. One untimed warm-up precedes five timed trials.

`time.perf_counter()` measures runtime without allocation-tracing overhead. A
separate execution uses `tracemalloc` to record the maximum traced Python
allocation for the same operation. Dataset generation, CSV output, and chart
creation are outside timed sections. The CSV stores median, mean, standard
deviation, range, peak allocation, counters, status, and a SHA-256 deployment
order hash.

## 10. Runtime measurements

At 2,000 resources, optimized `schedule_all` medians were 0.056099750 seconds
for chain, 0.063852417 for layered sparse, 0.083003708 for layered dense, and
0.040021792 for wide independent. Corresponding speedups were 838.75, 939.92,
1,141.70, and 982.58 times. One hundred eligibility queries improved by
310.24 to 1,039.24 times. These descriptive results show observed behavior in
the tested Python environment; no statistical significance test was performed.

## 11. Memory measurements

For 2,000-resource `schedule_all`, optimized peak traced allocations were
741,780 to 743,892 bytes, compared with 848,012 to 1,967,940 bytes baseline.
The reduction ranged from 12.5% to 62.2% by profile because the persistent heap
avoids allocating a complete replacement queue on every selection.

Loading has the opposite trade-off. Optimized peak load allocation was about
104% to 151% higher at 2,000 resources because incomplete, failed, order,
generation, and ready indexes are constructed. The design exchanges retained
index memory for lower repeated scheduling work.

## 12. Correctness parity

Every comparable row has `parity_match: True` and `all_deployed: True`.
Deployment hashes match between engines for each profile and size. Validation
checks exact selection order, legal transitions, complete unique coverage,
every prerequisite before its dependent, and equal final summaries. Additional
tests cover committed Phase 2 data, equal-priority ties, priority changes,
failure/retry, deletion, single-resource graphs, and all-ready graphs. The
Phase 3 demo also reproduces the original ten-resource scenario exactly.

## 13. Stress testing

Optimized-only stress runs cover chain, layered sparse, and wide independent
graphs at 5,000, 10,000, and 25,000 resources. All nine cases passed. The
largest chain used 24,999 edges and completed build plus full scheduling in
4.939772208 seconds with 52,099,648 peak traced bytes. The largest layered
sparse graph used 49,549 edges, completed in 5.817780417 seconds, and used
51,688,728 bytes. The largest wide graph completed in 4.519727834 seconds and
used 45,354,860 bytes. All indexes remained valid; no recursion, failure,
duplicate selection, or stale selection occurred.

## 14. Complexity before and after

Let `V` be resources, `E` dependencies, `p` direct prerequisites, `d` direct
dependents, `r` ready resources, and `u` uncollected stale priority entries.
Metadata safe-copy cost is additional to the table.

| Operation | Phase 2 baseline | Phase 3 optimized |
|---|---:|---:|
| One readiness query | `O(p)` | `O(1 + output)` |
| Ordered eligible list | `O(V + E)` | `O(V)` membership enumeration |
| Peek next resource | `O(V + E + r log r)` | amortized `O(1)` after stale cleanup |
| Start next resource | `O(V + E + r log r)` | amortized `O(log r)` |
| Mark deployed | `O(1)` now; later scans recompute effects | `O(d log r)` worst case |
| Ready priority update | `O(1)` now; next selection rebuilds | `O(log r)` push |
| CSV dependency loading | `O(E(V + E))` | expected `O(V + E)` |
| Authoritative storage | `O(V + E)` | `O(V + E)` |
| Derived scheduling storage | temporary `O(r)` | `O(V + E + r + u)` |

Dynamic `add_dependency` intentionally retains a complete `O(V + E)` cycle
validation and therefore is not improved.

## 15. Optimization trade-offs

The optimized design is faster because it performs more bookkeeping. Every
structural or status mutation must update derived indexes correctly. Generation
entries simplify priority changes but can increase heap size until stale roots
are encountered. Index rebuilding provides recovery and validation but costs
`O(V + E)`. Safe registry copies remain for API protection, so metadata access
still has nonzero cost. For tiny or edge-free load-only workloads, the baseline
can be faster and use less memory.

## 16. Current limitations

Both engines are in-memory and single-process. They do not provide persistence,
transactions, locks, cloud API calls, capacity constraints, deadlines,
fairness, authentication, or deployment execution. Workloads are deterministic
and synthetic, and benchmark results come from one environment. Allocation
tracing covers Python-managed allocations, not complete process resident
memory. Dynamic graph changes still use full cycle validation.

## 17. Final evaluation

Phase 3 meets its objective: behavior is preserved while repeated scheduling
work is reduced substantially on the measured workloads. The strongest result
is complete scheduling, where direct-dependent updates and a persistent heap
replace repeated whole-registry readiness scans and heap construction. The
clearest cost is higher load-time memory for derived indexes. Results therefore
support the optimization for repeated scheduling workloads, not as a universal
replacement for every small or load-only case.

## 18. Deliverable 4 integration plan

The final integration should format the validated report, select the most
readable charts and table, and retain direct links to the CSV and JSON evidence.
Possible future implementation work includes incremental dynamic topological
ordering, bounded stale-heap compaction, compact metadata representations,
durable event storage, concurrent update control, and capacity-aware scheduling.
Those additions should preserve the current engines as reproducible baselines.
