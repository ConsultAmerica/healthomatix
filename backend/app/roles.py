"""Role aliases: DB membership roles ↔ architecture patient/clinician/staff/admin."""

from __future__ import annotations

# Architecture name → membership.role values that satisfy it
ROLE_ALIASES: dict[str, frozenset[str]] = {
    "patient": frozenset({"patient"}),
    "clinician": frozenset({"provider"}),
    "staff": frozenset({"staff"}),
    "admin": frozenset({"tenant_admin"}),
    "auditor": frozenset({"auditor"}),
}

# Roles that may read a patient chart when consent allows
CLINICIAN_READ_ROLES = frozenset({"provider", "staff", "tenant_admin"})


def membership_matches(role: str, *architecture_roles: str) -> bool:
    allowed: set[str] = set()
    for name in architecture_roles:
        allowed |= ROLE_ALIASES.get(name, frozenset({name}))
    return role in allowed
