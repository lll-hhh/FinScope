"""Metrics for the protected-decision to executable-action boundary.

These helpers deliberately operate on episode records rather than individual
messages.  They do not call a model and do not infer a missing ground truth.
An evaluator must provide the canonical action (usually the Vanilla action)
and the local alias-to-canonical resolver.
"""

from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


# Fields that can change the executable financial action.  ``reason`` and
# other explanatory fields are intentionally excluded from action equality.
NUMERIC_ACTION_FIELDS = frozenset(
    {
        "amount",
        "allocation",
        "notional",
        "percentage",
        "price",
        "quantity",
        "qty",
        "shares",
        "weight",
    }
)
EXECUTION_TEXT_FIELDS = frozenset(
    {"asset", "asset_name", "currency", "market", "symbol", "ticker", "venue"}
)
SIDE_FIELDS = ("action", "side", "order_side")
ASSET_FIELDS = ("asset", "asset_name", "symbol", "ticker", "instrument")
HANDLE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:FS_ASSET_[A-Z2-9]{8}|"
    r"(?:GA|EA)_[A-Z0-9_]+_[A-F0-9]{10}|"
    r"(?:FIXED|EP)_ASSET_[A-Z0-9_]+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _first(action: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in action:
            return action[key]
    return None


def _number(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        value = float(value)
        return value if math.isfinite(value) else "non-finite"
    return value


def _resolve(value: Any, resolver: Optional[Mapping[str, str]]) -> Any:
    if not isinstance(value, str):
        return value
    if resolver:
        token_match = HANDLE_PATTERN.search(value)
        token = token_match.group(0) if token_match else value
        return resolver.get(token) or resolver.get(token.upper()) or value
    return value


def canonical_action(action: Any, resolver: Optional[Mapping[str, str]] = None) -> Optional[Dict[str, Any]]:
    """Normalize an action without dropping executable fields.

    ``resolver`` is local-only and maps an opaque handle to its canonical
    security identifier.  The function never guesses an unknown handle.
    """

    if not isinstance(action, Mapping):
        return None
    asset = _first(action, ASSET_FIELDS)
    side = _first(action, SIDE_FIELDS)
    if asset is None or side is None:
        return None
    normalized: Dict[str, Any] = {
        "asset": _resolve(asset, resolver),
        "side": str(side).casefold(),
    }
    for key, value in action.items():
        key_name = str(key).casefold()
        if key_name in NUMERIC_ACTION_FIELDS:
            normalized[key_name] = _number(value)
        elif key_name in EXECUTION_TEXT_FIELDS and key_name not in {
            "asset",
            "asset_name",
            "symbol",
            "ticker",
        }:
            normalized[key_name] = str(value)
    return normalized


def decision_signature(
    action: Any, resolver: Optional[Mapping[str, str]] = None
) -> Optional[Tuple[Any, ...]]:
    """Return the decision identity, excluding order sizing.

    NLPCC currently exposes one final action and no tool trace, so this is the
    strongest decision-level comparison available there: canonical asset,
    direction, and (when present) tool name.  Quantity/weight belongs to Exact
    Action Restore below.
    """

    normalized = canonical_action(action, resolver)
    if normalized is None:
        return None
    tool = action.get("tool") if isinstance(action, Mapping) else None
    return (
        normalized.get("asset"),
        normalized.get("side"),
        str(tool) if tool is not None else None,
    )


def decision_preservation(
    protected: Sequence[Mapping[str, Any]],
    baseline: Sequence[Mapping[str, Any]],
    *,
    key: str = "episode_id",
) -> Dict[str, Any]:
    """Compare one protected outcome with one baseline outcome per episode.

    The denominator is every baseline episode, including parse/validation
    failures.  This prevents a method from hiding changed decisions by only
    reporting episodes where both outputs were valid.
    """

    protected_by_key = {str(row[key]): row for row in protected if key in row}
    preserved = 0
    comparable = 0
    direction_preserved = 0
    for reference in baseline:
        if key not in reference:
            continue
        current = protected_by_key.get(str(reference[key]))
        if current is None:
            continue
        comparable += 1
        baseline_sig = decision_signature(reference.get("action"))
        current_sig = decision_signature(current.get("action"))
        same = bool(
            reference.get("valid", False)
            and current.get("valid", False)
            and baseline_sig is not None
            and baseline_sig == current_sig
        )
        preserved += int(same)
        if same:
            direction_preserved += 1
    return {
        "preserved": preserved,
        "episodes": comparable,
        "rate": preserved / comparable if comparable else None,
        "direction_preserved": direction_preserved,
        "direction_rate": direction_preserved / comparable if comparable else None,
    }


def reference_continuity(views: Mapping[str, Mapping[str, str]]) -> Dict[str, Any]:
    """Check whether repeated local views use one handle per canonical asset.

    ``views`` maps a logical role/channel (for example ``research``,
    ``risk`` and ``trade``) to ``canonical_id -> handle``.  An asset counts in
    the denominator only when at least two views actually contain it.  A
    single-view episode is therefore reported as uncovered, not as perfect.
    """

    observations: Dict[str, list[str]] = {}
    for view in views.values():
        for canonical, handle in view.items():
            observations.setdefault(str(canonical), []).append(str(handle))
    comparable = {
        canonical: handles
        for canonical, handles in observations.items()
        if len(handles) >= 2
    }
    stable = sum(len(set(handles)) == 1 for handles in comparable.values())
    return {
        "stable": stable,
        "comparable_assets": len(comparable),
        "rate": stable / len(comparable) if comparable else None,
        "views": len([view for view in views.values() if view]),
    }


def exact_action_restore(
    outbound_action: Any,
    restored_action: Any,
    resolver: Optional[Mapping[str, str]],
    *,
    executed: bool,
) -> Optional[bool]:
    """Check complete action restoration and local execution acceptance.

    ``executed`` must come from the benchmark's local executor or transaction
    validator.  A syntactically valid action that is rejected for cash,
    holdings, market, or other business constraints is not an exact executable
    restore.
    """

    expected = canonical_action(outbound_action, resolver)
    actual = canonical_action(restored_action)
    if expected is None or actual is None:
        return False
    return bool(executed and expected == actual)
