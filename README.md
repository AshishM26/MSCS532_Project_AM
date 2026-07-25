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

## Complexity summary

| Operation | Expected time |
|---|---:|
| Registry search/update | `O(1)` average* |
| Graph resource registration | `O(1)` average |
| Dependency insertion and cycle validation | `O(V + E)` |
| One-resource readiness | `O(p)` |
| Eligible-resource scan | `O(V + E)` |
| Temporary ready-heap construction | `O(r log r)` |
| Selection after heap construction | `O(log r)` |
| Topological ordering | `O(V + E)` |
| Graph resource removal | `O(in-degree + out-degree)` |

`V` is resources, `E` dependencies, `p` direct prerequisites, and `r` ready
resources. `*` Metadata-copy cost depends on record size. The temporary heap is
rebuilt for each selection; this is a correctness-first Phase 2 trade-off, not
an optimized claim.

## Repository structure

```text
MSCS532_Project_AM/
├── README.md
├── requirements.txt
├── data/
│   ├── phase2_cloud_resources.csv
│   └── phase2_dependencies.csv
├── docs/
│   ├── phase1_design.md
│   ├── phase1_report_outline.md
│   ├── phase2_design.md
│   └── phase2_report_draft.md
├── examples/
│   ├── phase1_demo.py
│   └── phase2_poc_demo.py
├── results/
│   ├── phase2_execution_trace.csv
│   └── phase2_summary.json
├── src/
│   ├── __init__.py
│   ├── cloud_resource_loader.py
│   ├── deployment_graph.py
│   ├── deployment_priority_queue.py
│   ├── deployment_readiness_engine.py
│   └── service_registry.py
└── tests/
    ├── test_cloud_resource_loader.py
    ├── test_deployment_graph.py
    ├── test_deployment_priority_queue.py
    ├── test_deployment_readiness_engine.py
    ├── test_phase2_integration.py
    └── test_service_registry.py
```

## Setup and testing

Python 3.11 or later is recommended. The project uses only the Python standard
library.

```bash
git clone https://github.com/AshishM26/MSCS532_Project_AM.git
cd MSCS532_Project_AM
python3 -m venv .venv
source .venv/bin/activate
python3 examples/phase1_demo.py
python3 examples/phase2_poc_demo.py
python3 -m unittest discover -s tests -v
```

The verified Phase 2 suite contains **50 passing tests**. The tests focus on
correctness and integration; the short local runtime is not a performance
benchmark.

## Generated results

Running the Phase 2 demo deterministically rewrites:

- [phase2_execution_trace.csv](results/phase2_execution_trace.csv): 35
  state-selection and transition events.
- [phase2_summary.json](results/phase2_summary.json): input counts, initial
  eligibility, topological and deployment orders, failure/retry counts, priority
  updates, final state counts, and the blocked example.

## Known boundaries

- State is in memory and single-process.
- CSV files provide reproducibility but not transactions.
- The demo models one explicit failure rather than probabilistic failures.
- Ready resources are rescanned and the heap is rebuilt on every selection.
- No concurrency, resource capacity, deadline, authentication, or deployment
  execution is included.
- Structural deletion has no approval or audit-history layer.

## Phase 3 direction

Phase 3 should benchmark progressively larger sparse and dense synthetic graphs
before changing the implementation. Candidate experiments include incremental
cycle detection, cached in-degree/readiness values, lazy heap invalidation, bulk
loading, compact metadata, and batched result writing. Performance and memory
results should be compared with this committed Phase 2 baseline.
