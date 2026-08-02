# Cloud-Native Deployment Dependency and Priority Scheduling System

**Student:** Ashish Mahajan (005048542)<br>
**Course:** MSCS 532-B01 - Algorithms and Data Structures<br>
**Project:** Developing and Optimizing Data Structures for Real-World
Applications Using Python

Repository: <https://github.com/AshishM26/MSCS532_Project_AM>

## Project context

The project models generic cloud-resource dependencies and priority-aware
scheduling. It contains only synthetic data and does not include proprietary
systems, credentials, cloud APIs, or deployment commands.

The architecture separates three responsibilities:

- `DeploymentGraph` determines **readiness** from prerequisite relationships.
- `ServiceRegistry` stores resource metadata and execution **state**.
- `DeploymentPriorityQueue` determines **urgency** among ready resources.
- `DeploymentReadinessEngine` coordinates those structures without duplicating
  their internal storage.

## Phase 1 - foundational structures

Phase 1 implemented:

- forward and reverse adjacency lists;
- Kahn cycle detection and deterministic topological ordering;
- dictionary-based metadata registration, lookup, update, and removal;
- safe metadata copies;
- a stable `heapq` priority queue;
- a generic seven-service demonstration; and
- focused unit tests and design documentation.

Run the original demonstration:

```bash
python3 examples/phase1_demo.py
```

Phase 1 documentation:

- [Phase 1 submitted report](docs/MSCS-532-B01_Project_1_AM.pdf)
- [Phase 1 design](docs/phase1_design.md)
- [Phase 1 report outline](docs/phase1_report_outline.md)

## Phase 2 - proof of concept

Phase 2 extends the existing foundation with:

- strict cloud-resource and dependency CSV loading;
- graph edge and resource deletion;
- an integrated readiness engine;
- derived ready, waiting, blocked, active, deployed, and failed states;
- controlled execution-state transitions;
- selection of only ready resources;
- current-priority selection with deterministic ties;
- intentional failure, blocked dependents, retry, and recovery;
- priority updates before selection;
- coordinated graph and registry deletion;
- expanded unit and integration tests; and
- reproducible trace CSV and summary JSON output.

Run the Phase 2 proof of concept:

```bash
python3 examples/phase2_poc_demo.py
```

The committed run loads 10 resources and 9 dependencies. It begins with
`network-core` and `notification-topic` eligible, intentionally fails
`secrets-store` once, displays `backend-api` as blocked, deploys independent
work, updates `backup-policy` from priority 4 to 1, retries the failed resource,
and ultimately deploys all 10 resources.

The valid topological order is:

```text
network-core -> notification-topic -> identity-boundary -> database-cluster
-> monitoring-agent -> secrets-store -> backup-policy
-> observability-dashboard -> backend-api -> frontend-service
```

The priority-aware successful deployment order is:

```text
network-core -> identity-boundary -> database-cluster -> backup-policy
-> notification-topic -> monitoring-agent -> observability-dashboard
-> secrets-store -> backend-api -> frontend-service
```

Phase 2 documentation:

- [Phase 2 design](docs/phase2_design.md)
- [Phase 2 report draft](docs/phase2_report_draft.md)

## Phase 3 - optimization, scaling, and final evaluation

Phase 3 preserves `DeploymentReadinessEngine` as the Phase 2 baseline and adds
`OptimizedDeploymentReadinessEngine` with compatible scheduling behavior. It
addresses measured baseline costs from repeated prerequisite checks,
whole-registry eligibility scans, per-selection heap reconstruction, and
per-edge cycle validation during CSV loading.

The optimized architecture adds:

- cached incomplete and failed prerequisite indexes;
- ready-resource membership updated through direct dependents;
- one persistent heap with insertion-order ties and generation-based lazy
  invalidation;
- explicit metric counters, index rebuilding, and internal-state validation;
- validate-first bulk CSV loading with one final cycle validation;
- deterministic chain, layered-sparse, layered-dense, and wide-independent
  workload generation; and
- behavioral parity, benchmark-contract, and stress-contract tests.

The full comparison uses 100, 500, 1,000, and 2,000 resources, five trials,
five operations, four profiles, and both engines. Its **160 unique rows** all
report completed status, exact deployment-order parity, and successful complete
deployment. At 2,000 resources, median `schedule_all` time was:

| Profile | Baseline (s) | Optimized (s) | Observed speedup |
|---|---:|---:|---:|
| Chain | 47.053514 | 0.056100 | 838.75× |
| Layered sparse | 60.016214 | 0.063852 | 939.92× |
| Layered dense | 94.765168 | 0.083004 | 1,141.70× |
| Wide independent | 39.324634 | 0.040022 | 982.58× |

Peak traced allocation during complete scheduling was 12.5% to 62.2% lower
optimized at 2,000 resources. Loading showed the main trade-off: derived-index
construction used about 104% to 151% more peak traced allocation. Edge-bearing
datasets loaded 22.99× to 74.17× faster, while the zero-edge wide dataset loaded
slower optimized (0.030106125 versus 0.013519542 seconds). These are descriptive
measurements from the tested Python environment; no statistical significance
test was performed.

Optimized-only stress evaluation covers 5,000, 10,000, and 25,000 resources on
chain, layered-sparse, and wide-independent graphs. All nine cases passed. The
largest layered-sparse case used 49,549 dependencies, completed engine build and
full scheduling in 5.817780417 seconds, and recorded 51,688,728 peak traced
bytes. No failure, duplicate selection, recursion error, stale selection, or
index inconsistency occurred.

Run the behavioral parity demonstration:

```bash
python3 examples/phase3_optimization_demo.py
```

Run a quick comparison, the complete five-trial comparison, or optimized stress
evaluation:

```bash
python3 benchmarks/benchmark_phase3.py --trials 2 --max-size 500
python3 benchmarks/benchmark_phase3.py
python3 benchmarks/benchmark_phase3.py --stress-only
```

Phase 3 documentation:

- [Phase 3 design and measured analysis](docs/phase3_design.md)
- [Phase 3 report draft](docs/phase3_report_draft.md)

## Complexity summary

| Operation | Phase 2 baseline | Phase 3 optimized |
|---|---:|---:|
| Registry search/update | `O(1)` average* | `O(1)` average* |
| Dynamic dependency insertion | `O(V + E)` | `O(V + E)` |
| One-resource readiness | `O(p)` | `O(1 + output)` |
| Ordered eligible list | `O(V + E)` | `O(V)` membership scan |
| Peek next resource | `O(V + E + r log r)` | amortized `O(1)` |
| Start next resource | `O(V + E + r log r)` | amortized `O(log r)` |
| Mark deployed | `O(1)` with deferred effects | `O(d log r)` worst case |
| CSV dependency loading | `O(E(V + E))` | expected `O(V + E)` |
| Topological ordering | `O(V + E)` | `O(V + E)` |
| Graph resource removal | `O(in-degree + out-degree)` | same plus index updates |

`V` is resources, `E` dependencies, `p` direct prerequisites, `d` direct
dependents, and `r` ready resources. `*` Metadata-copy cost depends on record
size. Phase 3 retains up to `O(V + E + r + u)` derived scheduling storage, where
`u` is uncollected stale heap entries.

## Repository structure

```text
MSCS532_Project_AM/
├── README.md
├── requirements.txt
├── benchmarks/
│   ├── __init__.py
│   ├── benchmark_helpers.py
│   └── benchmark_phase3.py
├── data/
│   ├── phase2_cloud_resources.csv
│   └── phase2_dependencies.csv
├── docs/
│   ├── MSCS-532-B01_Project_1_AM.pdf
│   ├── phase1_design.md
│   ├── phase1_report_outline.md
│   ├── phase2_design.md
│   ├── phase2_report_draft.md
│   ├── phase3_design.md
│   └── phase3_report_draft.md
├── examples/
│   ├── phase1_demo.py
│   ├── phase2_poc_demo.py
│   └── phase3_optimization_demo.py
├── results/
│   ├── phase2_execution_trace.csv
│   ├── phase2_summary.json
│   ├── phase3_benchmark_results.csv
│   ├── phase3_memory_comparison.png
│   ├── phase3_optimization_summary.json
│   ├── phase3_runtime_comparison.png
│   ├── phase3_scaling_chart.png
│   └── phase3_stress_summary.json
├── src/
│   ├── __init__.py
│   ├── bulk_cloud_resource_loader.py
│   ├── cloud_resource_loader.py
│   ├── deployment_graph.py
│   ├── deployment_priority_queue.py
│   ├── deployment_readiness_engine.py
│   ├── optimized_deployment_readiness_engine.py
│   ├── phase3_metrics.py
│   ├── service_registry.py
│   └── synthetic_workload_generator.py
└── tests/
    ├── test_bulk_cloud_resource_loader.py
    ├── test_cloud_resource_loader.py
    ├── test_deployment_graph.py
    ├── test_deployment_priority_queue.py
    ├── test_deployment_readiness_engine.py
    ├── test_optimized_deployment_readiness_engine.py
    ├── test_phase2_integration.py
    ├── test_phase3_benchmark_contract.py
    ├── test_phase3_parity.py
    ├── test_phase3_stress_contract.py
    ├── test_service_registry.py
    └── test_synthetic_workload_generator.py
```

## Setup and testing

Python 3.11 or later is recommended. Runtime structures use the standard
library; Matplotlib is the only chart dependency.

```bash
git clone https://github.com/AshishM26/MSCS532_Project_AM.git
cd MSCS532_Project_AM
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 examples/phase1_demo.py
python3 examples/phase2_poc_demo.py
python3 examples/phase3_optimization_demo.py
python3 -m unittest discover -s tests -v
```

The verified Phase 3 suite contains **114 passing tests**, including all 50
Phase 2 baseline tests. Unit-test runtime is not a performance benchmark.

## Generated results

Running the Phase 2 demo deterministically rewrites:

- [phase2_execution_trace.csv](results/phase2_execution_trace.csv): 35
  state-selection and transition events.
- [phase2_summary.json](results/phase2_summary.json): input counts, initial
  eligibility, topological and deployment orders, failure/retry counts, priority
  updates, final state counts, and the blocked example.

Phase 3 evidence includes:

- [phase3_benchmark_results.csv](results/phase3_benchmark_results.csv): 160
  comparable runtime, allocation, counter, hash, and parity rows;
- [runtime comparison](results/phase3_runtime_comparison.png) and [memory
  comparison](results/phase3_memory_comparison.png): four-profile schedule
  charts;
- [optimized scaling chart](results/phase3_scaling_chart.png): 5,000 through
  25,000-resource stress growth;
- [phase3_stress_summary.json](results/phase3_stress_summary.json): nine stress
  cases with environment, graph, runtime, memory, and correctness evidence; and
- [phase3_optimization_summary.json](results/phase3_optimization_summary.json):
  committed-data behavior and counter parity.

## Known boundaries

- State is in memory and single-process.
- CSV files provide reproducibility but not transactions.
- The demo models one explicit failure rather than probabilistic failures.
- Ready resources are rescanned and the heap is rebuilt on every selection.
- No concurrency, resource capacity, deadline, authentication, or deployment
  execution is included.
- Structural deletion has no approval or audit-history layer.
- Optimized indexes increase retained and load-time memory.
- Lazy invalidation can retain stale heap entries until cleanup or rebuilding.
- Dynamic dependency insertion still performs full graph cycle validation.
- `tracemalloc` does not measure complete process resident memory.
- Results are descriptive measurements from one Python environment.

## Deliverable 4 direction

The next integration step is to format the validated report and select the most
readable committed charts and table. Later implementation work can evaluate
incremental dynamic topological ordering, bounded stale-heap compaction, compact
metadata, durable event storage, transactional updates, concurrency control,
and capacity-aware scheduling while retaining both current engines as baselines.
