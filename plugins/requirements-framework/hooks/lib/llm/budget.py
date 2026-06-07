"""SDK monthly spend tracker — Step 17a.

Post-hoc capture of `claude-agent-sdk` `ResultMessage.total_cost_usd` into an
append-only JSONL ledger at ``~/.claude/requirements-framework/usage/<YYYY-MM>.jsonl``.

Design (see `.claude/plans/variant3/17a-sdk-spend-tracker.md`):

- One JSONL line per ``query()`` / ``ClaudeSDKClient`` ResultMessage.
- Global scope (the SDK credit pool is per user account, not per repo).
- Fail-open: any I/O error is swallowed (logged once at WARNING). The
  framework never raises into the caller from a recording side-effect.
- Reactive: we never *predict* a cost before sending. We record what the
  SDK already calculated. Pre-call estimation is Step 17b.

Public API:

    record(result, agent=None, ...)         — extract from ResultMessage, append
    record_dict(record_obj, year, month, ledger_dir=None) — low-level append
    load_month(year, month, ledger_dir=None) — iterator over records
    summarize(records)                       — reduce to dict[mtd_usd, ...]
    project_eom(mtd_usd, now)                — linear EOM projection
    check_thresholds(summary, config)        — list[Alert] vs warn/critical

The module is intentionally dependency-free at import time. It is safe to
import even when the `claude-agent-sdk` extras are not installed.
"""

import calendar
import json
import logging
import os
from collections import Counter
from collections.abc import Iterable, Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

LOG = logging.getLogger("requirements.budget")

DEFAULT_LEDGER_DIR = Path.home() / ".claude" / "requirements-framework" / "usage"
DEFAULT_WARN_THRESHOLD_PCT = 75
DEFAULT_CRITICAL_THRESHOLD_PCT = 95
DEFAULT_MONTHLY_LIMIT_USD = 100  # Max 5x; users with Max 20x bump to 200.


# ---------- ledger I/O -------------------------------------------------------


def _ledger_path(year: int, month: int, ledger_dir: Path | None) -> Path:
    base = ledger_dir if ledger_dir is not None else DEFAULT_LEDGER_DIR
    return base / f"{year:04d}-{month:02d}.jsonl"


def record_dict(
    record_obj: dict[str, Any],
    *,
    year: int | None = None,
    month: int | None = None,
    ledger_dir: Path | None = None,
) -> None:
    """Append ``record_obj`` as one JSON line. Fail-open on any I/O error.

    ``year``/``month`` default to the current UTC month. They are passed
    explicitly by ``record()`` so the file name matches the record's own
    timestamp even at the month boundary.
    """
    if year is None or month is None:
        now = datetime.now(timezone.utc)
        year = year if year is not None else now.year
        month = month if month is not None else now.month

    path = _ledger_path(year, month, ledger_dir)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Single write() of one line keeps the append atomic for typical
        # single-process use. The OS guarantees write() is atomic up to
        # PIPE_BUF (usually 4096 bytes). Records are well under that.
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record_obj, separators=(",", ":")) + "\n")
    except Exception as exc:  # noqa: BLE001 — fail-open is the design
        LOG.warning("budget ledger write failed (%s): %s",
                    type(exc).__name__, exc)


def record(
    result: Any,
    *,
    agent: str | None = None,
    repo: str | None = None,
    now: datetime | None = None,
    ledger_dir: Path | None = None,
    enabled: bool | None = None,
) -> None:
    """Extract usage from a ResultMessage-like object and append to the ledger.

    ``enabled=False`` makes this a no-op (config gate).

    The signature accepts duck-typed objects so tests don't need the SDK.
    Production callers pass real ``claude_agent_sdk.ResultMessage`` instances.
    """
    if enabled is False:
        return

    if now is None:
        now = datetime.now(timezone.utc)

    usage = getattr(result, "usage", None) or {}
    record_obj: dict[str, Any] = {
        "ts": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "agent": agent or "unknown",
        "cost_usd": getattr(result, "total_cost_usd", None),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "duration_ms": getattr(result, "duration_ms", None),
        "is_error": getattr(result, "is_error", False),
        "sdk_session_id": getattr(result, "session_id", None),
        "model_usage": getattr(result, "model_usage", None),
        "repo": repo or os.getcwd(),
    }
    record_dict(record_obj, year=now.year, month=now.month, ledger_dir=ledger_dir)


# ---------- read-side --------------------------------------------------------


def load_month(
    year: int, month: int, *, ledger_dir: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield each well-formed record for the given month. Missing file → empty."""
    path = _ledger_path(year, month, ledger_dir)
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    # Malformed line — skip and continue. The whole point of
                    # an append-only ledger is durability across malformed
                    # writes.
                    continue
                if isinstance(obj, dict):
                    yield obj
    except OSError as exc:
        LOG.warning("budget ledger read failed (%s): %s",
                    type(exc).__name__, exc)


def summarize(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Reduce records to month-to-date totals and a top-agents ranking."""
    mtd = 0.0
    count = 0
    agent_costs: dict[str, float] = {}
    agent_calls: Counter[str] = Counter()

    for r in records:
        count += 1
        cost = r.get("cost_usd")
        if isinstance(cost, (int, float)):
            mtd += float(cost)
            agent = r.get("agent") or "unknown"
            agent_costs[agent] = agent_costs.get(agent, 0.0) + float(cost)
            agent_calls[agent] += 1

    top_agents = sorted(agent_costs.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "mtd_usd": mtd,
        "call_count": count,
        "top_agents": top_agents,
        "agent_calls": dict(agent_calls),
    }


# ---------- projection -------------------------------------------------------


def project_eom(mtd_usd: float, now: datetime) -> float:
    """Linear extrapolation of MTD spend to end-of-month.

    Stdlib only — uses ``calendar.monthrange`` to find month length. Returns
    ``mtd_usd`` unchanged when less than one hour has elapsed in the month
    (otherwise the projection explodes from a near-zero divisor).
    """
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    next_month_start = month_start + timedelta(days=days_in_month)
    elapsed_s = (now - month_start).total_seconds()
    total_s = (next_month_start - month_start).total_seconds()
    if elapsed_s < 3600:
        return mtd_usd
    return mtd_usd * (total_s / elapsed_s)


# ---------- thresholds -------------------------------------------------------


def check_thresholds(
    summary: dict[str, Any], config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return alerts (possibly empty) for projected_eom_usd vs warn/critical.

    ``config`` is the ``budgets.sdk_pool`` block; missing keys take defaults.
    Only the highest-severity alert is returned — warn is suppressed when
    critical fires, to keep stderr from doubling up.
    """
    proj = summary.get("projected_eom_usd")
    if proj is None:
        return []

    limit = float(config.get("monthly_limit_usd", DEFAULT_MONTHLY_LIMIT_USD))
    warn_pct = float(config.get("warn_threshold_pct", DEFAULT_WARN_THRESHOLD_PCT))
    crit_pct = float(config.get("critical_threshold_pct",
                                DEFAULT_CRITICAL_THRESHOLD_PCT))
    pct = (proj / limit) * 100 if limit > 0 else 0.0

    if pct >= crit_pct:
        return [{
            "level": "critical",
            "projected_eom_usd": proj,
            "limit_usd": limit,
            "pct": pct,
        }]
    if pct >= warn_pct:
        return [{
            "level": "warn",
            "projected_eom_usd": proj,
            "limit_usd": limit,
            "pct": pct,
        }]
    return []
