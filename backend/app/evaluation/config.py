"""Evaluation paths and profile-independent configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVAL_ROOT = BACKEND_ROOT / "evals"


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    eval_root: Path = DEFAULT_EVAL_ROOT
    output_dir: Path
    random_seed: int = Field(default=42, ge=0)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        output_dir: Path | None = None,
    ) -> "EvaluationConfig":
        return cls(
            output_dir=output_dir or settings.artifacts_output_dir / "evaluation" / "runs",
            random_seed=settings.eval_random_seed,
        )
