"""Download the ten manifest-listed local privacy models without changing roles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Mapping


def load_manifest(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    models = payload.get("models")
    if not isinstance(models, list) or len(models) != 10:
        raise ValueError("manifest must contain exactly ten models")
    if any(float(item["parameters_b"]) > 4.0 for item in models):
        raise ValueError("manifest contains a model above 4B")
    return payload


def download(model_id: str, target: Path, source: str) -> str:
    target.mkdir(parents=True, exist_ok=True)
    if source in {"auto", "modelscope"}:
        try:
            from modelscope import snapshot_download

            snapshot_download(model_id, local_dir=str(target))
            return "modelscope"
        except ImportError:
            if source == "modelscope":
                raise
        except Exception:
            if source == "modelscope":
                raise
    from huggingface_hub import snapshot_download

    snapshot_download(model_id, local_dir=str(target))
    return "huggingface"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="benchmarks/local_privacy_models.json")
    parser.add_argument("--model-root", default="/home/zgx/models")
    parser.add_argument("--source", choices=("auto", "modelscope", "huggingface"), default="auto")
    parser.add_argument("--only-missing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = load_manifest(Path(args.manifest))
    root = Path(args.model_root)
    results: Dict[str, str] = {}
    for item in manifest["models"]:
        model_id = str(item["model_id"])
        target = root / str(item["local_dir"])
        if item.get("availability") == "alias_required":
            results[model_id] = "alias_required"
            continue
        if args.only_missing and (target / "config.json").is_file():
            results[model_id] = "already_present"
            continue
        try:
            provider = download(model_id, target, args.source)
            results[model_id] = f"downloaded:{provider}"
        except Exception as exc:
            results[model_id] = f"failed:{type(exc).__name__}: {exc}"
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(value.startswith("failed:") for value in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
