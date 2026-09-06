"""Run FinScope on the public NLPCC 2026 Track 1 data.

This runner uses the official no-future-leakage DataLoader, real daily news,
real ETF/index prices, and a local Qwen decision model.  It is deliberately
separate from ``run_benchmark.py``, whose inputs are synthetic smoke cases.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
from pathlib import Path
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from finscope import (
    ActionValidationError,
    AmbiguousRestorationError,
    LocalPrivacyAgent,
)
from benchmarks.run_benchmark import BackendResult, OpenAIBackend, TransformersBackend
from benchmarks.local_privacy_agent import (
    LocalPrivacyModelConfig,
    build_model_assisted_agent,
    usage_delta,
)
from benchmarks.closed_loop_metrics import (
    decision_preservation,
    exact_action_restore,
    reference_continuity,
)


METHODS = (
    "vanilla",
    "deletion",
    "llm_rewrite",
    "fixed_alias",
    "episode_alias",
    "finscope",
)
FUND_POOL = (
    "000300.SH",
    "000905.SH",
    "399006.SZ",
    "000688.SH",
    "000932.SH",
    "000941.SH",
    "399971.SZ",
    "000819.SH",
    "000928.SH",
    "000012.SH",
    "518880.SH",
)
FUND_PROFILES = {
    "000300.SH": ("沪深300", "大盘蓝筹"),
    "000905.SH": ("中证500", "中小盘"),
    "399006.SZ": ("创业板指", "成长科技"),
    "000688.SH": ("科创50", "硬科技"),
    "000932.SH": ("中证消费", "消费"),
    "000941.SH": ("新能源指数", "新能源主题"),
    "399971.SZ": ("中证传媒", "传媒"),
    "000819.SH": ("有色金属指数", "有色金属行业"),
    "000928.SH": ("中证能源指数", "传统能源"),
    "000012.SH": ("国债指数", "固定收益"),
    "518880.SH": ("黄金ETF", "贵金属"),
}
DISCLOSURE_GROUPS = {
    "000300.SH": ("宽基权益组", "权益风险资产"),
    "000905.SH": ("宽基权益组", "权益风险资产"),
    "399006.SZ": ("成长权益组", "权益风险资产"),
    "000688.SH": ("成长权益组", "权益风险资产"),
    "000932.SH": ("消费传媒组", "权益风险资产"),
    "399971.SZ": ("消费传媒组", "权益风险资产"),
    "000941.SH": ("周期资源组", "权益风险资产"),
    "000819.SH": ("周期资源组", "权益风险资产"),
    "000928.SH": ("周期资源组", "权益风险资产"),
    "000012.SH": ("防御分散组", "防御分散资产"),
    "518880.SH": ("防御分散组", "防御分散资产"),
}
CANONICAL_ASSET = {
    identifier.casefold(): asset
    for asset, profile in FUND_PROFILES.items()
    for identifier in (asset, asset.split(".", 1)[0], profile[0])
}
NEWS_SOURCES = ("caixin", "tiantian", "sinafinance", "tencent")
MODEL_REVISION = "1098534ab5d7220ea0f4a6b9f07bb03729a79c1d"
PROMPT_VERSION = "nlpcc-track1-single-action-v1"


def source_provenance() -> Tuple[str, bool]:
    """Return the checked-out revision and whether tracked files differ from it."""

    git = shutil.which("git")
    if git is None:
        local_git = Path.home() / ".local" / "usr" / "bin" / "git"
        git = str(local_git) if local_git.is_file() else None
    if git is None:
        return "unknown", True
    repository = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            [git, "status", "--porcelain", "--untracked-files=no"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown", True
    return revision, bool(status.strip())


FINSCOPE_COMMIT, FINSCOPE_SOURCE_DIRTY = source_provenance()
_EPISODE_ALIAS_KEY = secrets.token_bytes(32)


@dataclass
class Portfolio:
    cash: float = 100_000.0
    holdings: Dict[str, float] = field(
        default_factory=lambda: {asset: 0.0 for asset in FUND_POOL}
    )
    turnover: float = 0.0

    @property
    def value(self) -> float:
        return self.cash + sum(self.holdings.values())


@dataclass
class DayRecord:
    method: str
    date: str
    outbound_prompt_sha256: str
    direct_identifier_leak: bool
    input_tokens: int
    output_tokens: int
    model_latency_ms: float
    preprocess_ms: float
    postprocess_ms: float
    parsed: bool
    valid: bool
    executed: bool
    rejection_reason: Optional[str]
    raw_output: str
    outbound_action: Optional[Dict[str, Any]]
    restored_action: Optional[Dict[str, Any]]
    portfolio_value: float
    cash: float
    portfolio_weights: Dict[str, float]
    rewrite_input_tokens: int = 0
    rewrite_output_tokens: int = 0
    rewrite_latency_ms: float = 0.0
    rewrite_succeeded: Optional[bool] = None
    privacy_model_usage: Dict[str, float] = field(default_factory=dict)
    privacy_agent_metrics: Dict[str, int] = field(default_factory=dict)
    # These are episode-level closed-loop measures.  They are optional so
    # older checkpoints remain readable and methods without a restoration
    # boundary can be reported as N/A rather than as a fabricated zero.
    reference_continuity: Optional[bool] = None
    reference_comparable_assets: int = 0
    reference_view_count: int = 0
    exact_action_restore: Optional[bool] = None
    attacker_view: Dict[str, Any] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real NLPCC 2026 Track 1 news-price-backtest evaluation"
    )
    parser.add_argument(
        "--nlpcc-root",
        default="../data/nlpcc2026_20260818",
        help="directory containing repo/ and lfs/ from the official dataset",
    )
    parser.add_argument("--model", default="../models/Qwen3.8-27B")
    parser.add_argument(
        "--model-base-url",
        default="",
        help="OpenAI-compatible task-model endpoint; when set, --model is metadata only",
    )
    parser.add_argument(
        "--model-api-key",
        default="",
        help="optional API key for --model-base-url; never written to result metadata",
    )
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--privacy-model-base-url",
        default="",
        help="OpenAI-compatible endpoint for the local small privacy model",
    )
    parser.add_argument(
        "--privacy-model-name",
        default="Qwen2.5-3B-Instruct",
        help="served model ID for the local privacy Agent",
    )
    parser.add_argument("--start-date", default="2025-01-02")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--max-days", type=int, default=0)
    parser.add_argument("--lookback-days", type=int, default=6)
    parser.add_argument("--top-rank", type=int, default=20)
    parser.add_argument("--pre-k-days", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument(
        "--disclosure-level",
        choices=("P1", "P2", "P3", "P4", "P5"),
        default="P3",
    )
    parser.add_argument("--methods", nargs="+", choices=METHODS, default=list(METHODS))
    parser.add_argument(
        "--rewrite-cache",
        nargs="*",
        default=[],
        help="validated rewrite-cache shards used by the llm_rewrite method",
    )
    parser.add_argument(
        "--output",
        default="benchmarks/results/nlpcc_real_2025_qwen38_p3.json",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="checkpoint path; defaults to OUTPUT.checkpoint.json",
    )
    parser.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="ignore an existing compatible checkpoint",
    )
    parser.set_defaults(resume=True)
    return parser.parse_args()


def load_official_data(args: argparse.Namespace) -> Tuple[Any, List[int], Dict[str, str]]:
    root = Path(args.nlpcc_root)
    tasks_root = root / "repo" / "NLPCC_tasks"
    lfs_dataset = root / "lfs" / "NLPCC_tasks" / "dataset"
    sys.path.insert(0, str(tasks_root))
    from dataset.dataloader_eval import DataLoader

    price_dir = lfs_dataset / "price_data" / "export_data"
    news_dir = lfs_dataset / "news_data" / "export_data"
    loader = DataLoader(str(price_dir), str(news_dir))
    start = int(args.start_date.replace("-", ""))
    end = int(args.end_date.replace("-", ""))
    dates = loader.get_trading_dates(start, end)
    if args.max_days > 0:
        dates = dates[: args.max_days]
    if not dates:
        raise RuntimeError("no official trading dates in the requested window")
    files = {
        "official_loader": str(tasks_root / "dataset" / "dataloader_eval.py"),
        "price_dir": str(price_dir),
        "news_dir": str(news_dir),
    }
    return loader, dates, files


def asset_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "canonical_id": asset,
            "name": FUND_PROFILES[asset][0],
            "aliases": [asset, asset.split(".", 1)[0]],
            "asset_type": "金融资产",
            "market": "中国公开市场",
            "sector_l1": DISCLOSURE_GROUPS[asset][1],
            "sector_l2": DISCLOSURE_GROUPS[asset][0],
            "sector_l3": DISCLOSURE_GROUPS[asset][0],
            "size_bucket": "标准",
            "version": "nlpcc-track1-2026-anonymity-groups-v1",
        }
        for asset in FUND_POOL
    ]


def build_payload(
    loader: Any,
    date: int,
    portfolio: Portfolio,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    history = loader.get_historical_prices(
        list(FUND_POOL), date, args.lookback_days
    )
    candidates = []
    for asset in FUND_POOL:
        observations = []
        for row in history.get(asset, []):
            if int(row.get("date_int") or 0) == date and any(
                row.get(field) is not None
                for field in ("close", "high", "low", "pct_change", "change")
            ):
                raise RuntimeError(
                    "official DataLoader exposed decision-day future price fields"
                )
            observations.append(
                {
                    "date": row.get("date"),
                    "open": row.get("open"),
                    "close": row.get("close"),
                    "pct_change": row.get("pct_change"),
                }
            )
        candidates.append(
            {
                "asset": asset,
                "name": FUND_PROFILES[asset][0],
                "category": FUND_PROFILES[asset][1],
                "prices": observations,
            }
        )

    news_rows = loader.get_news(
        list(NEWS_SOURCES),
        date,
        top_rank=args.top_rank,
        pre_k_days=args.pre_k_days,
    )
    # The public files contain several list types per source, so RANKING <= 20
    # can return hundreds of rows.  The task specification says daily Top-20;
    # deduplicate identical headlines and cap the merged ranked stream at 20.
    news = []
    seen_titles = set()
    for row in news_rows:
        title = str(row.get("TITLE", "")).strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        news.append(
            {
                "source": str(row.get("APP_TYPE", "")),
                "date": str(row.get("THEDATE", "")),
                "rank": int(row.get("RANKING", 999)),
                "title": title,
            }
        )
        if len(news) >= args.top_rank:
            break
    holdings = [
        {"asset": asset, "value": round(value, 2)}
        for asset, value in portfolio.holdings.items()
        if value > 1e-6
    ]
    return {
        "date": datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d"),
        "candidate_pool": candidates,
        "news": news,
        "portfolio": {
            "cash": round(portfolio.cash, 2),
            "holdings": holdings,
            "total_value": round(portfolio.value, 2),
        },
        "execution_rules": {
            "commission_rate": 0.0001,
            "buy_uses_current_cash_only": True,
            "one_action_max": True,
        },
    }


def _bucket(value: float, boundaries: Sequence[float], labels: Sequence[str]) -> str:
    for boundary, label in zip(boundaries, labels):
        if value < boundary:
            return label
    return labels[-1]


def coarsen_market_features(
    payload: Mapping[str, Any], disclosure_level: str
) -> Dict[str, Any]:
    """Remove exact public-price fingerprints while retaining coarse signals."""

    level = str(disclosure_level).upper()
    transformed = dict(payload)
    candidates = []
    for candidate in payload.get("candidate_pool", []):
        item = dict(candidate)
        asset = str(item.get("asset", ""))
        observations = list(item.pop("prices", []))
        returns = [
            float(row["pct_change"])
            for row in observations
            if row.get("pct_change") is not None
        ]
        momentum = sum(returns)
        volatility = statistics.mean(abs(value) for value in returns) if returns else 0.0
        positive_days = sum(value > 0 for value in returns)
        current_open = next(
            (
                float(row["open"])
                for row in reversed(observations)
                if row.get("open") is not None and row.get("close") is None
            ),
            None,
        )
        previous_close = next(
            (
                float(row["close"])
                for row in reversed(observations)
                if row.get("close") is not None
            ),
            None,
        )
        open_gap = (
            (current_open / previous_close - 1) * 100
            if current_open is not None and previous_close not in {None, 0}
            else 0.0
        )
        features: Dict[str, Any] = {}
        if level in {"P1", "P2"}:
            item["category"] = DISCLOSURE_GROUPS[asset][0]
            features["momentum"] = _bucket(
                momentum,
                (-3.0, -1.0, 1.0, 3.0),
                ("strong_down", "down", "flat", "up", "strong_up"),
            )
            features["volatility"] = _bucket(
                volatility,
                (0.8, 1.8),
                ("low", "medium", "high"),
            )
            gap_boundaries = (-1.5, -0.4, 0.4, 1.5) if level == "P1" else (-0.6, 0.6)
            gap_labels = (
                ("large_down", "down", "flat", "up", "large_up")
                if level == "P1"
                else ("down", "flat", "up")
            )
            features["open_gap"] = _bucket(open_gap, gap_boundaries, gap_labels)
            if level == "P1":
                features["positive_days"] = _bucket(
                    float(positive_days),
                    (2.0, 4.0),
                    ("few", "mixed", "many"),
                )
        elif level == "P3":
            item["category"] = DISCLOSURE_GROUPS[asset][1]
            features["momentum"] = _bucket(
                momentum, (-1.0, 1.0), ("down", "flat", "up")
            )
            features["volatility"] = _bucket(
                volatility, (0.8, 1.8), ("low", "medium", "high")
            )
        elif level == "P4":
            item["category"] = "公开市场资产"
            features["trend"] = _bucket(
                momentum, (-1.0, 1.0), ("down", "flat", "up")
            )
        elif level == "P5":
            item.pop("category", None)
        else:
            raise ValueError(f"unknown disclosure level: {disclosure_level}")
        item["market_features"] = features
        candidates.append(item)
    transformed["candidate_pool"] = candidates
    return transformed


def build_prompt(payload: Mapping[str, Any]) -> str:
    return (
        "你是NLPCC 2026 Track 1的日频资产配置智能体。根据真实历史行情、截至"
        "当日15:00的财经新闻和当前持仓，最多给出一个交易动作。决策时不能使用当日"
        "收盘价等未来信息。买入amount不得超过cash；卖出percentage必须在(0,1]；"
        "不交易时action为hold。asset必须逐字复制candidate_pool中的一个asset值。"
        "只输出一个严格JSON对象，不要Markdown，不要解释，格式为："
        '{"asset":"候选值","action":"buy|sell|hold","amount":数字,'
        '"percentage":数字,"reason":"简短原因"}。\n'
        "BEGIN_NLPCC_INPUT\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\nEND_NLPCC_INPUT"
    )


def replace_known_assets(value: Any, replacements: Mapping[str, str]) -> Any:
    ordered = sorted(replacements, key=len, reverse=True)

    def replace_text(text: str) -> str:
        for source in ordered:
            text = re.sub(re.escape(source), replacements[source], text, flags=re.I)
        return text

    if isinstance(value, str):
        return replace_text(value)
    if isinstance(value, list):
        return [replace_known_assets(item, replacements) for item in value]
    if isinstance(value, Mapping):
        return {
            replace_text(str(key)): replace_known_assets(item, replacements)
            for key, item in value.items()
        }
    return value


def build_episode_aliases(date: int) -> Dict[str, str]:
    """Create keyed per-day aliases for the opaque episode baseline."""

    return {
        asset: "EP_ASSET_"
        + hmac.new(
            _EPISODE_ALIAS_KEY,
            f"nlpcc-episode-alias-v2:{date}:{asset}".encode(),
            hashlib.sha256,
        ).hexdigest()[:10].upper()
        for asset in FUND_POOL
    }


def rewrite_news(
    backend: TransformersBackend,
    outbound: Dict[str, Any],
) -> Tuple[Dict[str, Any], BackendResult, bool]:
    """Rewrite all daily headlines in one constrained local-model call."""

    titles = [str(item.get("title", "")) for item in outbound.get("news", [])]
    prompt = (
        "你是本地金融隐私改写器。将每条标题改写为不含证券、公司、基金、指数、"
        "人物或机构专名的简短金融事件摘要，同时保留行业、事件类型、方向和情绪。"
        "不得输出输入中的代码、专名或匿名代号。每条不超过24个汉字，数量和顺序必须"
        "与输入一致。只输出严格JSON：{\"news\":[\"摘要1\",\"摘要2\"]}。\n"
        + json.dumps({"news": titles}, ensure_ascii=False, separators=(",", ":"))
    )
    result = backend.generate(prompt, max_new_tokens=384)
    parsed = parse_action(result.text)
    rewritten = parsed.get("news") if isinstance(parsed, Mapping) else None
    succeeded = (
        isinstance(rewritten, list)
        and len(rewritten) == len(titles)
        and all(isinstance(item, str) and 0 < len(item.strip()) <= 48 for item in rewritten)
    )
    safe_titles = (
        [item.strip() for item in rewritten]
        if succeeded
        else ["匿名金融事件" for _ in titles]
    )
    outbound["news"] = [
        {**item, "title": safe_title}
        for item, safe_title in zip(outbound.get("news", []), safe_titles)
    ]
    return outbound, result, succeeded


def news_titles_sha256(payload: Mapping[str, Any]) -> str:
    titles = [str(item.get("title", "")) for item in payload.get("news", [])]
    encoded = json.dumps(titles, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_rewrite_cache(paths: Sequence[str]) -> Dict[str, Mapping[str, Any]]:
    cache: Dict[str, Mapping[str, Any]] = {}
    for value in paths:
        path = Path(value)
        document = json.loads(path.read_text(encoding="utf-8"))
        for date, entry in document.get("entries", {}).items():
            if date in cache:
                raise RuntimeError(f"duplicate rewrite-cache date: {date}")
            cache[str(date)] = entry
    return cache


def apply_cached_rewrite(
    payload: Dict[str, Any], date: int, cache: Mapping[str, Mapping[str, Any]]
) -> Tuple[Dict[str, Any], BackendResult, bool]:
    key = str(date)
    if key not in cache:
        raise RuntimeError(f"rewrite cache lacks trading day: {key}")
    entry = cache[key]
    source_hash = news_titles_sha256(payload)
    if entry.get("source_titles_sha256") != source_hash:
        raise RuntimeError(f"rewrite-cache source mismatch on {key}")
    safe_titles = entry.get("safe_titles")
    if not isinstance(safe_titles, list) or len(safe_titles) != len(payload.get("news", [])):
        raise RuntimeError(f"rewrite-cache title count mismatch on {key}")
    payload["news"] = [
        {**item, "title": str(title)}
        for item, title in zip(payload.get("news", []), safe_titles)
    ]
    usage = entry.get("usage", {})
    return (
        payload,
        BackendResult(
            "",
            int(usage.get("input_tokens", 0)),
            int(usage.get("output_tokens", 0)),
            float(usage.get("latency_ms", 0.0)),
        ),
        bool(entry.get("succeeded")),
    )


def prepare_outbound(
    method: str,
    payload: Dict[str, Any],
    date: int,
    privacy_agent: LocalPrivacyAgent,
    fixed_aliases: Mapping[str, str],
    disclosure_level: str,
) -> Tuple[Dict[str, Any], Optional[Any], Dict[str, str], float]:
    started = time.perf_counter()
    scope = None
    representation: Dict[str, str]
    if method == "vanilla":
        outbound = payload
        representation = {asset: asset for asset in FUND_POOL}
    elif method == "deletion":
        replacements = {}
        for asset in FUND_POOL:
            replacements[asset] = "REDACTED"
            replacements[FUND_PROFILES[asset][0]] = "REDACTED"
        outbound = replace_known_assets(payload, replacements)
        for index, candidate in enumerate(outbound["candidate_pool"], start=1):
            candidate["asset"] = f"REDACTED_{index:02d}"
            candidate["name"] = "REDACTED"
        outbound["portfolio"]["holdings"] = [
            {"asset": "REDACTED", "value": item["value"]}
            for item in outbound["portfolio"]["holdings"]
        ]
        representation = {asset: "REDACTED" for asset in FUND_POOL}
    elif method in {"llm_rewrite", "fixed_alias", "episode_alias"}:
        replacements = {}
        for asset, alias in fixed_aliases.items():
            replacements[asset] = alias
            replacements[FUND_PROFILES[asset][0]] = alias
        outbound = replace_known_assets(payload, replacements)
        if method in {"llm_rewrite", "episode_alias"}:
            outbound["candidate_pool"].sort(key=lambda item: str(item["asset"]))
            outbound["portfolio"]["holdings"].sort(
                key=lambda item: str(item["asset"])
            )
        representation = dict(fixed_aliases)
    elif method == "finscope":
        trading_day = datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
        scope = privacy_agent.open_scope(
            "nlpcc-track1-real",
            trading_day,
            conversation_id="qwen38-track1",
        )
        protected_payload = coarsen_market_features(payload, disclosure_level)
        outbound = privacy_agent.sanitize(
            protected_payload,
            scope,
            disclosure_level=disclosure_level,
            purpose="portfolio-allocation",
        )
        representation = {
            asset: str(candidate["asset"])
            for asset, candidate in zip(FUND_POOL, outbound["candidate_pool"])
        }
        outbound["candidate_pool"].sort(key=lambda item: str(item["asset"]))
        outbound["portfolio"]["holdings"].sort(
            key=lambda item: str(item["asset"])
        )
    else:  # pragma: no cover - argparse guards this
        raise ValueError(method)
    elapsed = (time.perf_counter() - started) * 1000
    return outbound, scope, representation, elapsed


def parse_action(text: str) -> Optional[Dict[str, Any]]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    documents = [candidate]
    match = re.search(r"\{.*\}", candidate, re.S)
    if match and match.group(0) != candidate:
        documents.append(match.group(0))
    for document in documents:
        try:
            value = json.loads(document)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, Mapping):
            continue
        if isinstance(value.get("trades"), list) and value["trades"]:
            non_hold = [
                item
                for item in value["trades"]
                if isinstance(item, Mapping)
                and str(item.get("action", "hold")).casefold() != "hold"
            ]
            value = non_hold[0] if non_hold else value["trades"][0]
        action = dict(value)
        if "asset" not in action and "fund_id" in action:
            action["asset"] = action.pop("fund_id")
        if "action" not in action and "side" in action:
            action["action"] = action.pop("side")
        return action
    return None


def restore_and_validate(
    method: str,
    action: Optional[Dict[str, Any]],
    scope: Optional[Any],
    privacy_agent: LocalPrivacyAgent,
    fixed_restore: Mapping[str, str],
) -> Tuple[Optional[Dict[str, Any]], bool, Optional[str]]:
    if action is None:
        return None, False, "model output is not parseable JSON"
    restored = dict(action)
    try:
        if method == "finscope":
            if scope is None:  # pragma: no cover - defensive
                raise ActionValidationError("missing FinScope scope")
            restored = privacy_agent.validate_action(restored, scope).action
            restored["asset"] = CANONICAL_ASSET.get(
                str(restored.get("asset", "")).casefold(),
                restored.get("asset"),
            )
        elif method in {"llm_rewrite", "fixed_alias", "episode_alias"}:
            asset = str(restored.get("asset", ""))
            if asset not in fixed_restore:
                raise ActionValidationError("unknown fixed alias")
            restored["asset"] = fixed_restore[asset]
        elif method == "deletion":
            raise ActionValidationError("deleted identifier cannot be restored")

        asset = restored.get("asset")
        side = str(restored.get("action", "")).casefold()
        if asset not in FUND_POOL:
            raise ActionValidationError("asset is outside the NLPCC Track 1 pool")
        if side not in {"buy", "sell", "hold"}:
            raise ActionValidationError("unsupported action")
        restored["action"] = side
        if side == "buy":
            amount = float(restored.get("amount", 0))
            if not math.isfinite(amount) or amount <= 0:
                raise ActionValidationError("buy amount must be positive")
            restored["amount"] = amount
        if side == "sell":
            percentage = float(restored.get("percentage", 0))
            if not math.isfinite(percentage) or not 0 < percentage <= 1:
                raise ActionValidationError("sell percentage must be in (0, 1]")
            restored["percentage"] = percentage
        return restored, True, None
    except (ActionValidationError, AmbiguousRestorationError, TypeError, ValueError) as exc:
        return restored, False, str(exc)


_ASSET_ALIAS_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:FS_ASSET_[A-Z2-9]{8}|"
    r"(?:FIXED|EP)_ASSET_[A-Z0-9_]+)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def _asset_token(value: Any) -> Optional[str]:
    """Extract a local asset handle from a raw field or FinScope wrapper."""

    if not isinstance(value, str):
        return None
    match = _ASSET_ALIAS_PATTERN.search(value)
    return match.group(0).upper() if match else value.strip()


def _asset_resolver(
    method: str,
    scope: Optional[Any],
    privacy_agent: LocalPrivacyAgent,
    alias_restore: Mapping[str, str],
) -> Dict[str, str]:
    """Return the evaluator-only handle -> canonical asset mapping."""

    if method == "finscope" and scope is not None:
        local = privacy_agent.mediator.get_local_mapping(scope)
        resolved: Dict[str, str] = {}
        for alias, canonical in local.items():
            value = str(canonical)
            value = CANONICAL_ASSET.get(value.casefold(), value)
            if value in FUND_POOL:
                resolved[str(alias).upper()] = value
        return resolved
    return {
        str(alias).upper(): str(canonical)
        for alias, canonical in alias_restore.items()
        if str(canonical) in FUND_POOL
    }


def _resolve_asset_field(value: Any, resolver: Mapping[str, str]) -> Optional[str]:
    token = _asset_token(value)
    if not token:
        return None
    canonical = resolver.get(token.upper())
    if canonical is not None:
        return canonical
    return CANONICAL_ASSET.get(token.casefold())


def _reference_views(
    outbound: Mapping[str, Any],
    outbound_action: Optional[Mapping[str, Any]],
    resolver: Mapping[str, str],
) -> Dict[str, Dict[str, str]]:
    """Build local research/risk/trade views from one NLPCC episode.

    NLPCC exposes one daily decision call rather than three independent
    Agent endpoints.  The three views are therefore the candidate/news side,
    portfolio-risk side, and returned trade action.  This is an honest
    episode-level continuity check; StockBench/FinVault role logs use the same
    helper over their actual role requests.
    """

    views: Dict[str, Dict[str, str]] = {
        "research": {},
        "risk": {},
        "trade": {},
    }
    for candidate in outbound.get("candidate_pool", ()):
        if not isinstance(candidate, Mapping):
            continue
        raw = candidate.get("asset")
        canonical = _resolve_asset_field(raw, resolver)
        token = _asset_token(raw)
        if canonical is not None and token:
            views["research"][canonical] = token
    portfolio = outbound.get("portfolio", {})
    holdings = portfolio.get("holdings", ()) if isinstance(portfolio, Mapping) else ()
    for holding in holdings:
        if not isinstance(holding, Mapping):
            continue
        raw = holding.get("asset")
        canonical = _resolve_asset_field(raw, resolver)
        token = _asset_token(raw)
        if canonical is not None and token:
            views["risk"][canonical] = token
    if isinstance(outbound_action, Mapping):
        raw = outbound_action.get("asset")
        canonical = _resolve_asset_field(raw, resolver)
        token = _asset_token(raw)
        if canonical is not None and token:
            views["trade"][canonical] = token
    return views


def mark_to_market(portfolio: Portfolio, prices: Mapping[str, Mapping[str, Any]]) -> None:
    for asset, value in portfolio.holdings.items():
        if value <= 0:
            continue
        pct_change = prices.get(asset, {}).get("pct_change")
        if pct_change is not None:
            portfolio.holdings[asset] = value * (1 + float(pct_change) / 100)


def execute_action(portfolio: Portfolio, action: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    asset = action["asset"]
    side = action["action"]
    fee = 0.0001
    if side == "hold":
        return True, None
    if side == "buy":
        amount = float(action["amount"])
        if amount > portfolio.cash + 0.01:
            return False, "buy amount exceeds current cash"
        amount = min(amount, portfolio.cash)
        portfolio.cash -= amount
        portfolio.holdings[asset] += amount * (1 - fee)
        portfolio.turnover += amount
        return True, None
    percentage = float(action["percentage"])
    current = portfolio.holdings[asset]
    if current <= 1e-6:
        return False, "cannot sell an empty holding"
    sold = current * percentage
    portfolio.holdings[asset] -= sold
    portfolio.cash += sold * (1 - fee)
    portfolio.turnover += sold
    return True, None


def contains_direct_identifier(prompt: str) -> bool:
    identifiers = list(FUND_POOL) + [profile[0] for profile in FUND_PROFILES.values()]
    return any(identifier.casefold() in prompt.casefold() for identifier in identifiers)


def percentile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def performance_metrics(values: Sequence[float], turnover: float) -> Dict[str, float]:
    returns = [values[index] / values[index - 1] - 1 for index in range(1, len(values))]
    total_return = values[-1] / values[0] - 1 if values else 0.0
    if len(returns) > 1 and statistics.stdev(returns) > 0:
        sharpe = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252)
    else:
        sharpe = 0.0
    downside = [min(item, 0.0) for item in returns]
    downside_rms = math.sqrt(sum(item * item for item in downside) / len(downside)) if downside else 0
    sortino = statistics.mean(returns) / downside_rms * math.sqrt(252) if downside_rms else 0.0
    peak = values[0] if values else 1.0
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = max(max_drawdown, 1 - value / peak)
    return {
        "total_return": total_return,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "turnover_over_initial_capital": turnover / 100_000.0,
        "final_portfolio_value": values[-1] if values else 100_000.0,
    }


def summarize(
    methods: Sequence[str],
    records: Sequence[DayRecord],
    values: Mapping[str, Sequence[float]],
    portfolios: Mapping[str, Portfolio],
    representations: Mapping[str, Sequence[Mapping[str, str]]],
) -> List[Dict[str, Any]]:
    table = []
    vanilla_rows = {
        row.date: row for row in records if row.method == "vanilla"
    }
    for method in methods:
        rows = [row for row in records if row.method == method]
        perf = performance_metrics(values[method], portfolios[method].turnover)
        links = []
        method_representations = representations[method]
        for previous, current in zip(method_representations, method_representations[1:]):
            current_counts = {
                value: list(current.values()).count(value) for value in set(current.values())
            }
            for asset in FUND_POOL:
                links.append(
                    previous[asset] == current[asset]
                    and current_counts[current[asset]] == 1
                )
        weight_errors = []
        for row in rows:
            vanilla = vanilla_rows.get(row.date)
            if vanilla is None:
                continue
            weight_errors.extend(
                abs(row.portfolio_weights.get(asset, 0.0) - vanilla.portfolio_weights.get(asset, 0.0))
                for asset in FUND_POOL
            )
        decision = decision_preservation(
            [
                {
                    "episode_id": row.date,
                    "action": row.restored_action,
                    "valid": row.valid,
                }
                for row in rows
            ],
            [
                {
                    "episode_id": row.date,
                    "action": row.restored_action,
                    "valid": row.valid,
                }
                for row in vanilla_rows.values()
            ],
        )
        continuity_rows = [
            row for row in rows if row.reference_continuity is not None
        ]
        continuity_rate = (
            statistics.mean(bool(row.reference_continuity) for row in continuity_rows)
            if continuity_rows
            else None
        )
        exact_rows = [row for row in rows if row.exact_action_restore is not None]
        exact_rate = (
            statistics.mean(bool(row.exact_action_restore) for row in exact_rows)
            if exact_rows
            else None
        )
        table.append(
            {
                "method": method,
                **perf,
                "valid_action_rate": sum(row.valid for row in rows) / len(rows) if rows else 0.0,
                "execution_success_rate": sum(row.executed for row in rows) / len(rows) if rows else 0.0,
                # Kept as a compatibility alias for older result consumers.
                "decision_agreement_with_vanilla": decision["rate"] or 0.0,
                "decision_preservation_rate": decision["rate"],
                "decision_preserved_episodes": decision["preserved"],
                "decision_comparable_episodes": decision["episodes"],
                "reference_continuity_rate": continuity_rate,
                "reference_continuity_episodes": len(continuity_rows),
                "reference_comparable_assets": sum(
                    row.reference_comparable_assets for row in continuity_rows
                ),
                "exact_action_restore_rate": exact_rate,
                "exact_action_restore_episodes": len(exact_rows),
                "portfolio_weight_mae_vs_vanilla": (
                    statistics.mean(weight_errors) if weight_errors else 0.0
                ),
                "direct_identifier_leak_rate": sum(
                    row.direct_identifier_leak for row in rows
                )
                / len(rows),
                "cross_day_unique_link_rate": sum(links) / len(links) if links else 0.0,
                "avg_input_tokens": (
                    statistics.mean(
                        row.input_tokens + row.rewrite_input_tokens for row in rows
                    )
                    if rows
                    else 0.0
                ),
                "avg_output_tokens": (
                    statistics.mean(
                        row.output_tokens + row.rewrite_output_tokens for row in rows
                    )
                    if rows
                    else 0.0
                ),
                "rewrite_success_rate": (
                    statistics.mean(
                        bool(row.rewrite_succeeded)
                        for row in rows
                        if row.rewrite_succeeded is not None
                    )
                    if any(row.rewrite_succeeded is not None for row in rows)
                    else None
                ),
                "local_p95_ms": percentile(
                    [row.preprocess_ms + row.postprocess_ms for row in rows], 0.95
                ),
                "e2e_p95_ms": percentile(
                    [
                        row.preprocess_ms
                        + row.rewrite_latency_ms
                        + row.model_latency_ms
                        + row.postprocess_ms
                        for row in rows
                    ],
                    0.95,
                ),
            }
        )
    return table


def render_markdown(result: Mapping[str, Any]) -> str:
    metadata = result["metadata"]
    model_name = Path(str(metadata["model"])).name

    def rate(value: Optional[float]) -> str:
        return "N/A" if value is None else f"{value:.1%}"

    lines = [
        "# Real NLPCC 2026 Track 1 Main Table",
        "",
        f"- Model: `{model_name}` (`{metadata['model_revision']}`)",
        f"- Window: `{metadata['start_date']}` to `{metadata['end_date']}` "
        f"({metadata['trading_days']} trading days)",
        "- Data: official public NLPCC 2026 Track 1 news and ETF/index prices; "
        "current-day close/high/low/return hidden from prompts",
        "- Trading: CNY 100,000 initial capital, daily close execution, 0.01% friction",
        "",
        "| Method | Return ↑ | Sharpe ↑ | MDD ↓ | Valid ↑ | Decision Preservation ↑ | Reference Continuity ↑ | Exact Action Restore ↑ | Direct leak ↓ | Cross-day link ↓ | In tok. ↓ | E2E p95 ms ↓ |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["main_table"]:
        lines.append(
            "| {method} | {ret:.2%} | {sharpe:.3f} | {mdd:.2%} | {valid:.1%} | "
            "{decision} | {continuity} | {restore} | {leak:.1%} | {link:.1%} | "
            "{tokens:.1f} | {e2e:.2f} |".format(
                method=row["method"],
                ret=row["total_return"],
                sharpe=row["sharpe"],
                mdd=row["max_drawdown"],
                valid=row["valid_action_rate"],
                decision=rate(row.get("decision_preservation_rate")),
                continuity=rate(row.get("reference_continuity_rate")),
                restore=rate(row.get("exact_action_restore_rate")),
                leak=row["direct_identifier_leak_rate"],
                link=row["cross_day_unique_link_rate"],
                tokens=row["avg_input_tokens"],
                e2e=row["e2e_p95_ms"],
            )
        )
    expanded = result.get("expanded_metrics")
    if expanded:
        by_method = expanded["by_method"]
        lines.extend(
            [
                "",
                "## Financial Detail",
                "",
                "| Method | Final CNY | Ann. return | Ann. vol. | Calmar | Positive days | VaR 95 | CVaR 95 | Best day | Worst day | Max DD duration | Trades | Final cash |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in result["main_table"]:
            method = row["method"]
            metric = by_method[method]["finance"]
            lines.append(
                "| {method} | {final:,.2f} | {annual:.2%} | {vol:.2%} | {calmar:.3f} | "
                "{positive:.1%} | {var:.2%} | {cvar:.2%} | {best:.2%} | {worst:.2%} | "
                "{duration} | {trades} | {cash:,.2f} |".format(
                    method=method,
                    final=row["final_portfolio_value"],
                    annual=metric["annualized_return"],
                    vol=metric["annualized_volatility"],
                    calmar=metric["calmar_ratio"],
                    positive=metric["positive_day_rate"],
                    var=metric["historical_var_95"],
                    cvar=metric["historical_cvar_95"],
                    best=metric["best_daily_return"],
                    worst=metric["worst_daily_return"],
                    duration=metric["max_drawdown_duration_days"],
                    trades=metric["executed_trade_count"],
                    cash=metric["final_cash"],
                )
            )

        lines.extend(
            [
                "",
                "## Continuity And Utility",
                "",
                "| Method | Parse success | Valid / parsed | Execute / valid | Interrupted | Asset agree* | Action agree* | Full agree | Weight MAE | Malformed | Audit rejects | Execution rejects |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in result["main_table"]:
            method = row["method"]
            metric = by_method[method]["continuity"]
            lines.append(
                "| {method} | {parsed:.1%} | {valid_parsed:.1%} | {executed_valid:.1%} | "
                "{interrupted:.1%} | {asset:.1%} | {action:.1%} | {full:.1%} | "
                "{mae:.4f} | {malformed} | {audit} | {execution} |".format(
                    method=method,
                    parsed=metric["parse_success_rate"],
                    valid_parsed=metric["valid_given_parsed_rate"],
                    executed_valid=metric["execution_given_valid_rate"],
                    interrupted=metric["workflow_interruption_rate"],
                    asset=metric["asset_agreement_given_common_valid"],
                    action=metric["action_agreement_given_common_valid"],
                    full=row["decision_agreement_with_vanilla"],
                    mae=row["portfolio_weight_mae_vs_vanilla"],
                    malformed=metric["malformed_output_count"],
                    audit=metric["restoration_audit_rejection_count"],
                    execution=metric["execution_rejection_count"],
                )
            )
        lines.extend(
            [
                "",
                "*Asset and action agreement are conditional on both the method and Vanilla producing valid actions; full agreement uses all 243 days.*",
                "",
                "## Privacy",
                "",
                "| Method | Direct leaks | Direct leak rate | Cross-day unique link |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for method in metadata["methods"]:
            metric = by_method[method]["privacy"]
            lines.append(
                "| {method} | {count} / {days} | {leak:.1%} | {link:.1%} |".format(
                    method=method,
                    count=metric["direct_identifier_leak_count"],
                    days=metadata["trading_days"],
                    leak=metric["direct_identifier_leak_rate"],
                    link=metric["cross_day_unique_link_rate"],
                )
            )

        lines.extend(
            [
                "",
                "## Cost And Latency",
                "",
                "| Method | Total input tok. | Avg input | Input overhead | Avg output | Model avg ms | Model p95 ms | Local avg ms | Local p95 ms | E2E avg ms | E2E p50 ms | E2E p95 ms | Model hours | Output tok/s |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for method in metadata["methods"]:
            metric = by_method[method]["cost"]
            lines.append(
                "| {method} | {total_input:,} | {avg_input:.1f} | {overhead:+.1%} | "
                "{avg_output:.1f} | {model_avg:.2f} | {model_p95:.2f} | {local_avg:.2f} | "
                "{local_p95:.2f} | {e2e_avg:.2f} | {e2e_p50:.2f} | {e2e_p95:.2f} | "
                "{hours:.3f} | {throughput:.2f} |".format(
                    method=method,
                    total_input=metric["total_input_tokens"],
                    avg_input=metric["average_input_tokens"],
                    overhead=metric["input_token_overhead_vs_vanilla"],
                    avg_output=metric["average_output_tokens"],
                    model_avg=metric["average_model_latency_ms"],
                    model_p95=metric["p95_model_latency_ms"],
                    local_avg=metric["average_local_overhead_ms"],
                    local_p95=metric["p95_local_overhead_ms"],
                    e2e_avg=metric["average_e2e_latency_ms"],
                    e2e_p50=metric["p50_e2e_latency_ms"],
                    e2e_p95=metric["p95_e2e_latency_ms"],
                    hours=metric["total_model_time_hours"],
                    throughput=metric["aggregate_output_tokens_per_second"],
                )
            )

        lines.extend(["", "## Rejection Breakdown", ""])
        for method in metadata["methods"]:
            rejections = by_method[method]["continuity"]["rejection_counts"]
            rendered = "; ".join(
                f"`{reason}`: {count}" for reason, count in rejections.items()
            )
            lines.append(f"- **{method}**: {rendered or 'none'}")
        lines.extend(
            [
                "",
                "## Not Measured In This Run",
                "",
                ", ".join(expanded["not_measured"]) + ".",
            ]
        )
    lines.extend(
        [
            "",
            "This is a full-year public A-set replay, not an official NLPCC "
            "leaderboard submission. Direct leak checks literal candidate identifiers; "
            "semantic re-identification requires a separate attacker experiment.",
        ]
    )
    return "\n".join(lines) + "\n"


def checkpoint_path(args: argparse.Namespace) -> Path:
    if args.checkpoint:
        return Path(args.checkpoint)
    return Path(str(args.output) + ".checkpoint.json")


def run_fingerprint(args: argparse.Namespace, dates: Sequence[int]) -> str:
    payload = {
        "commit": FINSCOPE_COMMIT,
        "source_dirty": FINSCOPE_SOURCE_DIRTY,
        "model": str(Path(args.model).resolve()),
        "model_base_url": args.model_base_url,
        "model_revision": MODEL_REVISION,
        "dates": list(dates),
        "methods": list(args.methods),
        "disclosure_level": args.disclosure_level,
        "lookback_days": args.lookback_days,
        "top_rank": args.top_rank,
        "pre_k_days": args.pre_k_days,
        "max_new_tokens": args.max_new_tokens,
        "privacy_model_base_url": args.privacy_model_base_url,
        "privacy_model_name": args.privacy_model_name,
        "rewrite_cache": [
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in args.rewrite_cache
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_checkpoint(
    path: Path,
    fingerprint: str,
    completed_days: int,
    portfolios: Mapping[str, Portfolio],
    values: Mapping[str, Sequence[float]],
    representations: Mapping[str, Sequence[Mapping[str, str]]],
    records: Sequence[DayRecord],
) -> None:
    payload = {
        "fingerprint": fingerprint,
        "completed_days": completed_days,
        "portfolios": {key: asdict(value) for key, value in portfolios.items()},
        "values": values,
        "representations": representations,
        "records": [asdict(record) for record in records],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def load_checkpoint(
    path: Path,
    fingerprint: str,
    methods: Sequence[str],
) -> Optional[Tuple[int, Dict[str, Portfolio], Dict[str, List[float]], Dict[str, List[Mapping[str, str]]], List[DayRecord]]]:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("fingerprint") != fingerprint:
        raise RuntimeError(
            "checkpoint configuration does not match this run; use --checkpoint "
            "with another path or --no-resume"
        )
    portfolios = {
        method: Portfolio(**payload["portfolios"][method]) for method in methods
    }
    values = {method: list(payload["values"][method]) for method in methods}
    representations = {
        method: list(payload["representations"][method]) for method in methods
    }
    records = [DayRecord(**row) for row in payload["records"]]
    return int(payload["completed_days"]), portfolios, values, representations, records


def run(args: argparse.Namespace) -> Dict[str, Any]:
    loader, dates, files = load_official_data(args)
    fingerprint = run_fingerprint(args, dates)
    saved = (
        load_checkpoint(checkpoint_path(args), fingerprint, args.methods)
        if args.resume
        else None
    )
    backend = (
        OpenAIBackend(
            args.model_base_url,
            args.model,
            api_key=args.model_api_key or None,
            max_new_tokens=args.max_new_tokens,
        )
        if args.model_base_url
        else TransformersBackend(args.model, args.device, args.max_new_tokens)
    )
    privacy_bundle = None
    if args.privacy_model_base_url:
        privacy_bundle = build_model_assisted_agent(
            asset_catalog(),
            LocalPrivacyModelConfig(
                name="local-qwen-privacy-agent",
                base_url=args.privacy_model_base_url,
                model=args.privacy_model_name,
                default_level=args.disclosure_level,
            ),
        )
        privacy_agent = privacy_bundle.agent
    else:
        privacy_agent = LocalPrivacyAgent(
            asset_catalog(), default_level=args.disclosure_level
        )
    fixed_aliases = {
        asset: f"FIXED_ASSET_{index:03d}"
        for index, asset in enumerate(FUND_POOL, start=1)
    }
    rewrite_cache = load_rewrite_cache(args.rewrite_cache)
    if saved is None:
        completed_days = 0
        portfolios = {method: Portfolio() for method in args.methods}
        values = {method: [100_000.0] for method in args.methods}
        representations: Dict[str, List[Mapping[str, str]]] = {
            method: [] for method in args.methods
        }
        records: List[DayRecord] = []
    else:
        completed_days, portfolios, values, representations, records = saved
        print(
            f"resuming after {completed_days}/{len(dates)} completed trading days",
            flush=True,
        )

    for day_index, date in enumerate(dates[completed_days:], start=completed_days + 1):
        prices = loader.get_price_data(list(FUND_POOL), date)
        for method in args.methods:
            portfolio = portfolios[method]
            privacy_usage_before = (
                privacy_bundle.usage()
                if privacy_bundle is not None and method == "finscope"
                else {}
            )
            raw_payload = build_payload(loader, date, portfolio, args)
            rewrite_result = BackendResult("", 0, 0, 0.0)
            rewrite_succeeded = None
            if method == "llm_rewrite":
                if rewrite_cache:
                    raw_payload, rewrite_result, rewrite_succeeded = apply_cached_rewrite(
                        raw_payload, date, rewrite_cache
                    )
                else:
                    raw_payload, rewrite_result, rewrite_succeeded = rewrite_news(
                        backend, raw_payload
                    )
            aliases = (
                build_episode_aliases(date)
                if method in {"llm_rewrite", "episode_alias"}
                else fixed_aliases
            )
            alias_restore = {alias: asset for asset, alias in aliases.items()}
            outbound, scope, representation, preprocess_ms = prepare_outbound(
                method,
                raw_payload,
                date,
                privacy_agent,
                aliases,
                args.disclosure_level,
            )
            representations[method].append(representation)
            prompt = build_prompt(outbound)
            backend_result: BackendResult = backend.generate(prompt)
            outbound_action = parse_action(backend_result.text)
            post_started = time.perf_counter()
            restored, valid, rejection = restore_and_validate(
                method,
                outbound_action,
                scope,
                privacy_agent,
                alias_restore,
            )
            privacy_agent_metrics = (
                privacy_agent.get_metrics(scope) if scope is not None else {}
            )
            privacy_model_usage = (
                usage_delta(privacy_usage_before, privacy_bundle.usage())
                if privacy_bundle is not None and method == "finscope"
                else {}
            )
            # The decision sees prior-close portfolio state plus the current
            # open. Existing positions receive the current-day return only
            # after generation, immediately before close execution.
            mark_to_market(portfolio, prices)
            executed = False
            if valid and restored is not None:
                executed, execution_rejection = execute_action(portfolio, restored)
                if not executed:
                    rejection = execution_rejection
            resolver = _asset_resolver(
                method,
                scope,
                privacy_agent,
                alias_restore,
            )
            views = _reference_views(outbound, outbound_action, resolver)
            continuity = reference_continuity(views)
            # Vanilla and deletion have no local restoration boundary.  Keep
            # them out of the restore denominator rather than treating direct
            # use or an unrecoverable deletion as a successful restore.
            exact_restore = (
                exact_action_restore(
                    outbound_action,
                    restored,
                    resolver,
                    executed=executed,
                )
                if method not in {"vanilla", "deletion"}
                else None
            )
            postprocess_ms = (time.perf_counter() - post_started) * 1000
            values[method].append(portfolio.value)
            records.append(
                DayRecord(
                    method=method,
                    date=datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d"),
                    outbound_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
                    direct_identifier_leak=contains_direct_identifier(prompt),
                    input_tokens=backend_result.input_tokens,
                    output_tokens=backend_result.output_tokens,
                    model_latency_ms=backend_result.latency_ms,
                    preprocess_ms=preprocess_ms,
                    postprocess_ms=postprocess_ms,
                    parsed=outbound_action is not None,
                    valid=valid,
                    executed=executed,
                    rejection_reason=rejection,
                    raw_output=backend_result.text,
                    outbound_action=outbound_action,
                    restored_action=restored,
                    portfolio_value=portfolio.value,
                    cash=portfolio.cash,
                    portfolio_weights={
                        asset: (
                            portfolio.holdings[asset] / portfolio.value
                            if portfolio.value > 0
                            else 0.0
                        )
                        for asset in FUND_POOL
                    },
                    rewrite_input_tokens=rewrite_result.input_tokens,
                    rewrite_output_tokens=rewrite_result.output_tokens,
                    rewrite_latency_ms=rewrite_result.latency_ms,
                    rewrite_succeeded=rewrite_succeeded,
                    privacy_model_usage=privacy_model_usage,
                    privacy_agent_metrics=privacy_agent_metrics,
                    reference_continuity=(
                        bool(continuity["rate"] == 1.0)
                        if continuity["rate"] is not None
                        else None
                    ),
                    reference_comparable_assets=int(continuity["comparable_assets"]),
                    reference_view_count=int(continuity["views"]),
                    exact_action_restore=exact_restore,
                    attacker_view={
                        "request": outbound,
                        "response": backend_result.text,
                    },
                )
            )
            if scope is not None:
                privacy_agent.close_scope(scope)
            print(
                f"[{day_index:02d}/{len(dates):02d}] {date} {method}: "
                f"valid={valid} executed={executed} value={portfolio.value:.2f}",
                flush=True,
            )
        write_checkpoint(
            checkpoint_path(args),
            fingerprint,
            day_index,
            portfolios,
            values,
            representations,
            records,
        )

    table = summarize(
        args.methods, records, values, portfolios, representations
    )
    return {
        "metadata": {
            "benchmark": "NLPCC 2026 Shared Task 4 Track 1 public A-set",
            "prompt_version": PROMPT_VERSION,
            "model": args.model,
            "model_base_url": args.model_base_url,
            "model_revision": MODEL_REVISION,
            "finscope_commit": FINSCOPE_COMMIT,
            "finscope_source_dirty": FINSCOPE_SOURCE_DIRTY,
            "finscope_disclosure_level": args.disclosure_level,
            "finscope_disclosure_planner": (
                "model-assisted-security-master-validated"
                if privacy_bundle is not None
                else "deterministic-security-master"
            ),
            "local_privacy_model": (
                privacy_bundle.metadata() if privacy_bundle is not None else None
            ),
            "finscope_market_disclosure": "coarse-non-invertible-buckets-v1",
            "backend": backend.metadata,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start_date": datetime.strptime(str(dates[0]), "%Y%m%d").strftime("%Y-%m-%d"),
            "end_date": datetime.strptime(str(dates[-1]), "%Y%m%d").strftime("%Y-%m-%d"),
            "trading_days": len(dates),
            "methods": list(args.methods),
            "fund_pool": list(FUND_POOL),
            "news_sources": list(NEWS_SOURCES),
            "official_rank_threshold": args.top_rank,
            "merged_news_cap": args.top_rank,
            "news_selection": "official merged stream, title-deduplicated, first Top-20",
            "news_trading_day_lookback": args.pre_k_days,
            "price_lookback_days": args.lookback_days,
            "commission_rate": 0.0001,
            "initial_capital": 100_000.0,
            "temperature": 0,
            "do_sample": False,
            "files": files,
            "rewrite_cache_files": list(args.rewrite_cache),
            "limitations": [
                (
                    "requested date window may be shorter than the full 2025 A-set"
                    if len(dates) < 243
                    else "single full-year 2025 A-set replay"
                ),
                "direct literal identifier leakage only; no semantic attacker model",
                "one deterministic generation per method and day",
                (
                    "LLM Rewrite uses the same local base model for one constrained "
                    "headline-rewrite call before each decision"
                ),
            ],
        },
        "main_table": table,
        "daily_records": [asdict(record) for record in records],
        "portfolio_value_history": values,
    }


def main() -> None:
    args = parse_args()
    result = run(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = output.with_suffix(".md")
    markdown.write_text(render_markdown(result), encoding="utf-8")
    print(f"wrote {output}")
    print(f"wrote {markdown}")


if __name__ == "__main__":
    main()
