# Phase 1 Report Outline

This outline maps the repository to a four-page APA-style report. The title and
references pages are excluded from the four-page body. Replace every bracketed
placeholder, verify current APA requirements, and write the final submission in
clear, professional language.

## Title page

**Cloud-Native Deployment Dependency and Priority Scheduling System**<br>
Ashish Mahajan<br>
University of the Cumberlands<br>
MSCS 532 - Algorithms and Data Structures<br>
Project Phase 1 Deliverable 1<br>
Dr. Michael Solomon<br>
Student ID: **005048542**<br>
Submission date: `[MONTH DAY, YEAR]`

## Page 1 - Application Context and Problem Definition

### Opening and context

- Define a generic cloud-native deployment as a collection of services that may
  have prerequisite relationships.
- Explain the real-world need for correct ordering without referring to a
  particular employer, vendor, or private architecture.
- Use a generic example: a database must be ready before a dependent backend.

### Scheduling problems

- Explain that an incorrect order can cause startup or availability failures.
- Explain why a circular dependency has no valid topological order.
- Describe the need for direct metadata lookup as service state changes.
- Distinguish dependency eligibility from priority-based urgency.

### Scope and thesis

- State that Phase 1 designs and implements an in-memory adjacency-list graph,
  dictionary registry, and stable binary min-heap.
- State the original design insight: the graph determines readiness, the
  registry stores state, and the priority queue determines urgency.
- Clarify that the project is a Phase 1 foundation, not a production
  deployment platform.

## Page 2 - Data Structure Design and Rationale

### Directed graph

- Describe prerequisite-to-dependent directed edges and dual adjacency lists.
- Explain Kahn's algorithm for cycle detection and topological sorting.
- Give `O(V + E)` traversal time and `O(V + E)` graph storage.
- Compare the sparse adjacency list with an `O(V^2)` adjacency matrix.

### Hash table

- Explain the `service_id` dictionary key and required metadata values.
- Give average `O(1)` lookup and update, then acknowledge theoretical `O(n)`
  worst-case behavior under severe hash collisions.
- Compare dictionary lookup with an `O(n)` list scan.
- Explain the safety/cost trade-off of deep copies.

### Binary heap

- Explain priorities 1 through 4 and the insertion counter used for stable ties.
- Give `O(log n)` enqueue/dequeue, `O(1)` peek, and `O(n)` storage.
- Compare the heap with the `O(n)` insertion cost of a fully sorted list.

## Page 3 - Python Implementation Overview

### Modular classes

- Summarize `DeploymentGraph`, `ServiceRegistry`, and
  `DeploymentPriorityQueue` responsibilities.
- Note Python 3.10+ type hints, docstrings, standard-library-only code, and
  meaningful exceptions.

### Algorithms and selected evidence

- Include concise topological-order pseudocode from `phase1_design.md`.
- Include a short heap tuple example:
  `(priority, insertion_counter, service_id)`.
- Explain automatic graph node registration and duplicate-edge rejection.
- Explain registry validation and safe copies.

### Demonstration and tests

- Summarize the seven generic demo services and readiness-aware scheduling.
- Explain that the invalid-cycle example is caught without ending the demo.
- Summarize unit tests for graph ordering, registry operations, validation,
  priority order, stable ties, and empty behavior.
- Report actual test results only after rerunning the suite for submission.

## Page 4 - Critical Evaluation, Challenges, and Future Research

### Critical evaluation and limitations

- Discuss possible stale metadata and disagreement between graph and registry.
- Discuss duplicate queued tasks and the absence of in-place priority changes.
- Explain concurrency risks in an in-memory structure without locks.
- Note that dynamic graph updates require renewed cycle validation.
- Discuss repeated traversal cost as graph size grows.

### Measured optimization path

- Explain that Phase 1 does not perform large-scale benchmarking.
- Propose large sparse/dense graph tests before optimization.
- Evaluate caching or memoizing prerequisite results and incremental cycle
  detection as hypotheses that require measurements.
- Consider lazy deletion for dynamic priority changes.
- Consider a graph database or distributed scheduler only if later scale and
  persistence requirements justify the added complexity.

### Future research

- Mention integrated readiness logic, CI/CD and Kubernetes integration, cloud
  APIs, risk scoring, and AI-assisted optimization as future research only.
- Close by connecting the three chosen structures to correctness, efficient
  metadata access, deterministic urgency, and extensibility.

## References

Do not submit these placeholders as references. Locate suitable sources through
the university library, read them, cite claims in the report, and format each
entry according to the applicable APA edition.

1. `[PEER-REVIEWED SOURCE NEEDED: DAG workflow scheduling or graph-based`
   `dependency management; outside class material; APA verification required.]`
2. `[PEER-REVIEWED SOURCE NEEDED: priority scheduling or cloud workflow`
   `optimization; outside class material; APA verification required.]`
3. `[OUTSIDE TEXTBOOK OR PEER-REVIEWED SOURCE NEEDED: graph, hashing, and heap`
   `complexity; outside class material; APA verification required.]`

Additional sources may cover hashing behavior, distributed scheduling, or
workflow scalability. Do not invent bibliographic details; verify authors,
publication venue, year, DOI or publisher information, and relevance.
