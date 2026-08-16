from __future__ import annotations

PERMISSIONS = {
    "viewer": {"read"},
    "analyst": {"read", "deal.create", "document.upload", "assumption.create", "reconcile.run", "export.generate"},
    "reviewer": {"read", "value.review", "assumption.review", "opportunity.review", "finding.resolve", "reconcile.run", "export.generate"},
    "admin": {"*"},
}


def require(role: str, permission: str) -> None:
    granted = PERMISSIONS.get(role, set())
    if "*" not in granted and permission not in granted:
        raise PermissionError(f"Role {role!r} cannot perform {permission!r}")

