"""Static parser and validator for script-level ``CAPABILITY_META``.

The contract is deliberately a plain literal assignment so governance tooling can
inspect operator-facing scripts without importing them or triggering side effects.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


LIFECYCLES = frozenset({"active", "manual", "one_off", "deprecated"})
RISKS = frozenset({"read_only", "local_write", "external_write", "destructive"})
REQUIRED_FIELDS = frozenset(
    {"category", "lifecycle", "risk", "triggers", "owner", "project", "bridge"}
)
BRIDGE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def capability_meta_declared(tree: ast.AST) -> bool:
    """Return whether *tree* has a module-level ``CAPABILITY_META`` assignment."""
    if not isinstance(tree, ast.Module):
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CAPABILITY_META"
            for target in node.targets
        ):
            return True
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "CAPABILITY_META"
        ):
            return True
    return False


def capability_meta_from_tree(tree: ast.AST) -> dict[str, Any] | None:
    """Return a literal ``CAPABILITY_META`` assignment from *tree*, if present.

    Dynamic expressions are rejected: importing a script to compute governance
    metadata would defeat the no-side-effects contract.
    """
    if not isinstance(tree, ast.Module):
        return None
    for node in tree.body:
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "CAPABILITY_META" for target in node.targets):
                value = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "CAPABILITY_META"
        ):
            value = node.value
        if value is None:
            continue
        try:
            meta = ast.literal_eval(value)
        except (ValueError, TypeError, SyntaxError) as exc:
            raise ValueError("CAPABILITY_META must be a literal dictionary") from exc
        if not isinstance(meta, dict):
            raise ValueError("CAPABILITY_META must be a dictionary")
        return meta
    return None


def read_capability_meta(path: Path) -> dict[str, Any] | None:
    """Parse *path* and return its literal capability metadata."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError) as exc:
        raise ValueError(f"cannot parse capability metadata from {path}") from exc
    return capability_meta_from_tree(tree)


def validate_capability_meta(meta: dict[str, Any]) -> list[str]:
    """Return human-readable contract violations; an empty list is valid."""
    errors: list[str] = []
    missing = sorted(REQUIRED_FIELDS - set(meta))
    if missing:
        errors.append(f"missing fields: {', '.join(missing)}")

    for field in ("category", "owner", "project"):
        if not isinstance(meta.get(field), str) or not meta.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    if meta.get("lifecycle") not in LIFECYCLES:
        errors.append(f"lifecycle must be one of {sorted(LIFECYCLES)}")
    if meta.get("risk") not in RISKS:
        errors.append(f"risk must be one of {sorted(RISKS)}")

    triggers = meta.get("triggers")
    if not isinstance(triggers, list) or not triggers or not all(
        isinstance(trigger, str) and trigger.strip() for trigger in triggers
    ):
        errors.append("triggers must be a non-empty list of strings")

    bridge = meta.get("bridge")
    if not isinstance(bridge, dict):
        errors.append("bridge must be a dictionary")
        return errors
    if not isinstance(bridge.get("visible"), bool):
        errors.append("bridge.visible must be boolean")
    if "confirm" in bridge and not isinstance(bridge["confirm"], bool):
        errors.append("bridge.confirm must be boolean")
    for field in ("deny_args", "confirm_args"):
        args = bridge.get(field, [])
        if not isinstance(args, list) or not all(isinstance(arg, str) and arg for arg in args):
            errors.append(f"bridge.{field} must be a list of strings")
    fixed_args = bridge.get("fixed_args", [])
    if not isinstance(fixed_args, list) or not all(isinstance(arg, str) and arg for arg in fixed_args):
        errors.append("bridge.fixed_args must be a list of strings")
    subcommands = bridge.get("subcommands", {})
    if not isinstance(subcommands, dict):
        errors.append("bridge.subcommands must be a dictionary")
    else:
        for name, policy in subcommands.items():
            if not isinstance(name, str) or not isinstance(policy, dict):
                errors.append("bridge.subcommands entries must map names to dictionaries")
                continue
            if "visible" in policy and not isinstance(policy["visible"], bool):
                errors.append(f"bridge.subcommands.{name}.visible must be boolean")
            if "confirm" in policy and not isinstance(policy["confirm"], bool):
                errors.append(f"bridge.subcommands.{name}.confirm must be boolean")
            key = policy.get("key")
            if key is not None and (
                not isinstance(key, str) or BRIDGE_KEY_RE.fullmatch(key) is None
            ):
                errors.append(
                    f"bridge.subcommands.{name}.key must match {BRIDGE_KEY_RE.pattern}"
                )
            for field in ("deny_args", "confirm_args"):
                args = policy.get(field, [])
                if not isinstance(args, list) or not all(
                    isinstance(arg, str) and arg for arg in args
                ):
                    errors.append(
                        f"bridge.subcommands.{name}.{field} must be a list of strings"
                    )
            fixed = policy.get("fixed_args", [])
            if not isinstance(fixed, list) or not all(isinstance(arg, str) and arg for arg in fixed):
                errors.append(f"bridge.subcommands.{name}.fixed_args must be a list of strings")
    return errors
