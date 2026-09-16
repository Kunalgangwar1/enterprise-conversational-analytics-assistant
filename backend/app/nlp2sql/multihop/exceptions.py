"""Controlled multi-hop planning, execution, and budget failures."""


class MultiHopError(Exception):
    """Base class for sanitized multi-hop failures."""


class MultiHopDisabledError(MultiHopError):
    """Raised when the rollout flag does not permit multi-hop execution."""


class MultiHopPlanningError(MultiHopError):
    """Raised for invalid or unavailable hop plans."""


class MultiHopExecutionError(MultiHopError):
    """Raised when a required validated SQL hop cannot complete."""


class MultiHopBudgetExceededError(MultiHopExecutionError):
    """Raised before execution can exceed a hop, row, or time budget."""


class MultiHopSynthesisError(MultiHopError):
    """Raised when final grounded synthesis cannot be produced."""
