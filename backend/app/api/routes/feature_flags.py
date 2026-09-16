"""Public API endpoints for safe feature flag subsets."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_authenticated
from app.core.feature_flags import ToolFeatureFlags, UIFeatureFlags, get_feature_flags

router = APIRouter(tags=["feature-flags"], dependencies=[Depends(require_authenticated)])


@router.get("/ui-feature-flags", response_model=UIFeatureFlags)
def read_ui_feature_flags() -> UIFeatureFlags:
    """Return frontend-safe UI feature visibility settings."""
    return get_feature_flags().ui


@router.get("/tool-flags", response_model=ToolFeatureFlags)
def read_tool_feature_flags() -> ToolFeatureFlags:
    """Return frontend-safe specialist tool availability settings."""
    return get_feature_flags().tools
