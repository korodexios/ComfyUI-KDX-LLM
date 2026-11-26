"""Unified model profile matching and precedence engine.

Single source of truth for:
- profile normalization (normalize_profile)
- profile resolution with fixed precedence (resolve_profile)
- UI dropdown filtering (match_all_profiles)

Precedence: exact > case_insensitive > suffix (model-) > glob > none.
Within the same category: specificity (key length) > lexical order.
"""

import fnmatch
from typing import Any, Dict, List, Optional

MODES = ("thinking", "non_thinking")


def _normalize_mode(value: Any) -> Dict[str, dict]:
    """Normalize a single mode (thinking/non_thinking) to {sampling, request}."""
    if not isinstance(value, dict):
        return {"sampling": {}, "request": {}}
    # Legacy format: flat dict without sampling/request keys
    if "sampling" not in value and "request" not in value:
        return {"sampling": dict(value), "request": {}}
    return {
        "sampling": dict(value.get("sampling", {})) if isinstance(value.get("sampling"), dict) else {},
        "request": dict(value.get("request", {})) if isinstance(value.get("request"), dict) else {},
    }


def normalize_profile(profile: Any) -> Dict[str, Dict[str, dict]]:
    """Normalize a profile to the canonical two-mode structure.

    Single source of truth — sampling_store delegates here.
    """
    if not isinstance(profile, dict):
        return {mode: {"sampling": {}, "request": {}} for mode in MODES}
    return {mode: _normalize_mode(profile.get(mode, {})) for mode in MODES}


def resolve_profile(model: str, models_data: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a model name to the best-matching profile.

    Precedence:
    1. exact (key == model)
    2. case_insensitive (key.lower() == model.lower())
    3. suffix (key starts with model + "-", case-insensitive)
    4. glob (fnmatch pattern, sorted by -len, lexical)
    5. none
    """
    empty_result = {
        "key": None,
        "profile": normalize_profile(None),
        "match_type": "none",
        "specificity": 0,
    }

    if not model or not isinstance(models_data, dict):
        return empty_result

    target = model.strip()
    if not target:
        return empty_result

    target_low = target.lower()

    # 1. Exact match
    if target in models_data:
        return {
            "key": target,
            "profile": normalize_profile(models_data[target]),
            "match_type": "exact",
            "specificity": len(target),
        }

    # 2. Case-insensitive exact
    for key, val in models_data.items():
        if isinstance(key, str) and key.lower() == target_low:
            return {
                "key": key,
                "profile": normalize_profile(val),
                "match_type": "case_insensitive",
                "specificity": len(key),
            }

    # 3. Suffix match (key starts with "model-")
    prefix_candidates = []
    for key, val in models_data.items():
        if not isinstance(key, str):
            continue
        if key.lower().startswith(target_low + "-"):
            prefix_candidates.append((len(key), key, val))

    if prefix_candidates:
        prefix_candidates.sort(key=lambda x: (-x[0], x[1]))
        _, best_key, best_val = prefix_candidates[0]
        return {
            "key": best_key,
            "profile": normalize_profile(best_val),
            "match_type": "suffix",
            "specificity": len(best_key),
        }

    # 4. Glob match
    glob_candidates = []
    for key, val in models_data.items():
        if isinstance(key, str) and any(c in key for c in "*?["):
            glob_candidates.append((len(key), key, val))

    glob_candidates.sort(key=lambda x: (-x[0], x[1].lower()))
    for _, key, val in glob_candidates:
        if fnmatch.fnmatchcase(target_low, key.lower()):
            return {
                "key": key,
                "profile": normalize_profile(val),
                "match_type": "glob",
                "specificity": len(key),
            }

    return empty_result


def match_all_profiles(model: str, models_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all profiles that qualify for a given model (UI dropdown).

    When model is empty, returns all profiles.
    """
    if not isinstance(models_data, dict):
        return []

    target = (model or "").strip()
    target_low = target.lower()
    results = []

    for key, value in models_data.items():
        if not isinstance(key, str):
            continue

        is_glob = any(c in key for c in "*?[")

        if not target:
            results.append({
                "key": key,
                "matched": True,
                "is_glob": is_glob,
                "profile": normalize_profile(value),
            })
            continue

        key_low = key.lower()
        matched = (
            key == target
            or key_low == target_low
            or key_low.startswith(target_low + "-")
            or (is_glob and fnmatch.fnmatchcase(target_low, key_low))
        )

        if matched:
            results.append({
                "key": key,
                "matched": True,
                "is_glob": is_glob,
                "profile": normalize_profile(value),
            })

    return results
