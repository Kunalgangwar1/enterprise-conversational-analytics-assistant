"""Deterministic self-access introspection with no LLM or user directory."""

import re

from pydantic import BaseModel, ConfigDict

from app.auth.models import AuthPrincipal
from app.auth.permissions import Permission
from app.auth.roles import AppRole

_OTHER_IDENTITY = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


class GroupAccessResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    display_name: str | None
    roles: tuple[AppRole, ...]
    groups: tuple[str, ...]
    effective_permissions: tuple[Permission, ...]
    capability_summaries: tuple[str, ...]


class GroupAccessService:
    def inspect_self(self, question: str, principal: AuthPrincipal) -> GroupAccessResult:
        """Return only current-principal access and reject identity-directory questions."""

        emails = _OTHER_IDENTITY.findall(question)
        if emails and (principal.email is None or any(item != principal.email for item in emails)):
            raise ValueError("Access inspection is limited to the current authenticated user")
        permissions = tuple(sorted(principal.permissions, key=str))
        return GroupAccessResult(
            display_name=principal.display_name,
            roles=principal.roles,
            groups=principal.groups,
            effective_permissions=permissions,
            capability_summaries=tuple(_capability_summary(item) for item in permissions),
        )


def _capability_summary(permission: Permission) -> str:
    return permission.value.replace(".", " ").replace("_", " ").capitalize()
