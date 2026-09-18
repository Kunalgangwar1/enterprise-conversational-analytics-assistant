"""Bounded load profiles; stress remains an explicit manual choice."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadProfile:
    name: str
    users: int
    spawn_rate: float
    run_time: str
    description: str
    manual_only: bool = False


PROFILES = {
    "smoke": LoadProfile("smoke", 2, 1.0, "15s", "CI-safe harness verification."),
    "baseline": LoadProfile("baseline", 10, 2.0, "1m", "Modest local comparison run."),
    "stress": LoadProfile(
        "stress", 50, 5.0, "5m", "Manual local saturation exploration.", manual_only=True
    ),
}


def get_profile(name: str) -> LoadProfile:
    """Resolve an explicit profile and reject accidental unbounded runs."""

    try:
        return PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(PROFILES)
        raise ValueError(f"Unknown performance profile {name!r}; choose: {choices}") from exc
