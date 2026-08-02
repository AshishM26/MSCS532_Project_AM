"""Metric containers shared by Phase 3 engines and benchmarks."""

from dataclasses import asdict, dataclass


@dataclass
class EngineMetrics:
    """Count observable engine work without changing scheduling behavior."""

    readiness_requests: int = 0
    prerequisite_status_checks: int = 0
    eligible_full_scans: int = 0
    heap_rebuilds: int = 0
    heap_pushes: int = 0
    heap_pops: int = 0
    stale_heap_pops: int = 0
    maximum_heap_size: int = 0
    full_cycle_validations: int = 0
    dependent_updates: int = 0
    index_rebuilds: int = 0
    resources_processed: int = 0

    def to_dict(self) -> dict[str, int]:
        """Return a serializable snapshot of all counters."""
        return asdict(self)


@dataclass(frozen=True)
class Measurement:
    """Store one runtime and peak-allocation observation."""

    elapsed_seconds: float
    peak_memory_bytes: int

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds cannot be negative")
        if self.peak_memory_bytes < 0:
            raise ValueError("peak_memory_bytes cannot be negative")
