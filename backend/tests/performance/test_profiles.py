import pytest

from performance.profiles import PROFILES, get_profile
from performance.run import command


def test_profiles_are_bounded_and_stress_is_manual_only() -> None:
    assert set(PROFILES) == {"smoke", "baseline", "stress"}
    assert PROFILES["smoke"].users <= 2
    assert PROFILES["baseline"].users <= 10
    assert PROFILES["stress"].manual_only is True


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown performance profile"):
        get_profile("unbounded")


def test_runner_generates_headless_normalized_command() -> None:
    generated = command("smoke", "http://localhost:8000", "/tmp/perf")
    assert "--headless" in generated
    assert generated[generated.index("--users") + 1] == "2"
    assert "performance/locustfile.py" in generated
