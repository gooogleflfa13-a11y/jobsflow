"""Single-source runtime defaults for scan, scoring and push."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCORE_GATE = 3.3
PASS1_RESCUE_MARGIN = 0.35
MIN_INFORMATIVE_TEASER_CHARS = 60
PORTAL_SUBPROCESS_TIMEOUT_SECONDS = 90
DEFAULT_MAX_DEEP_FETCHES = 20

SCAN_DEPTH_PRESETS = {
    "economy": {"label_zh": "节能", "max_network_deep": 10},
    "balanced": {"label_zh": "平衡", "max_network_deep": 20},
    "coverage": {"label_zh": "广覆盖", "max_network_deep": 40},
}
RETENTION_PRESETS = {
    "loose": {"label_zh": "宽松", "final_gate": 3.0},
    "standard": {"label_zh": "标准", "final_gate": 3.3},
    "selective": {"label_zh": "精选", "final_gate": 3.5},
}

_SCAN_DEPTH_ALIASES = {
    "economy": "economy",
    "fast": "economy",
    "节能": "economy",
    "快速": "economy",
    "balanced": "balanced",
    "balance": "balanced",
    "平衡": "balanced",
    "coverage": "coverage",
    "broad": "coverage",
    "广覆盖": "coverage",
    "广泛": "coverage",
}
_RETENTION_ALIASES = {
    "loose": "loose",
    "宽松": "loose",
    "standard": "standard",
    "标准": "standard",
    "selective": "selective",
    "精选": "selective",
}


def normalize_scan_depth(value: Any) -> str:
    """Normalize a user-facing scan-depth label to a stable config key."""
    return _SCAN_DEPTH_ALIASES.get(str(value or "").strip().casefold(), "balanced")


def normalize_retention_preference(value: Any) -> str:
    """Normalize a user-facing retention label to a stable config key."""
    return _RETENTION_ALIASES.get(
        str(value or "").strip().casefold(), "standard"
    )


def parse_scan_depth(value: Any) -> str:
    """Strict parser for an explicit user command."""
    raw = str(value or "").strip().casefold()
    if raw not in _SCAN_DEPTH_ALIASES:
        raise ValueError("扫描深度必须是：节能、平衡或广覆盖")
    return _SCAN_DEPTH_ALIASES[raw]


def parse_retention_preference(value: Any) -> str:
    """Strict parser for an explicit user command."""
    raw = str(value or "").strip().casefold()
    if raw not in _RETENTION_ALIASES:
        raise ValueError("保留偏好必须是：宽松、标准或精选")
    return _RETENTION_ALIASES[raw]


def resolve_workflow_preferences(config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve old or new private config into executable workflow controls."""
    raw = config if isinstance(config, dict) else {}
    preferences = raw.get("workflow_preferences")
    if not isinstance(preferences, dict):
        preferences = {}
    scan_depth = normalize_scan_depth(preferences.get("scan_depth"))
    retention = normalize_retention_preference(
        preferences.get("retention_preference")
    )
    scan_preset = SCAN_DEPTH_PRESETS[scan_depth]
    retention_preset = RETENTION_PRESETS[retention]
    return {
        "scan_depth": scan_depth,
        "scan_depth_label": scan_preset["label_zh"],
        "max_network_deep": scan_preset["max_network_deep"],
        "retention_preference": retention,
        "retention_label": retention_preset["label_zh"],
        "final_gate": retention_preset["final_gate"],
    }


def load_workflow_preferences(repo: Path) -> dict[str, Any]:
    """Load private preferences, falling back safely for legacy workspaces."""
    root = Path(repo).expanduser().resolve()
    workspace = root if root.name == "JobSearch_2026" else root / "JobSearch_2026"
    path = workspace / "00_Profile" / "queries.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        config = {}
    return resolve_workflow_preferences(config if isinstance(config, dict) else {})


def default_retrieval_floor(final_gate: float) -> float:
    """Lower pass-1 triage floor; the final quality gate stays unchanged."""
    return round(max(1.0, float(final_gate) - PASS1_RESCUE_MARGIN), 2)
