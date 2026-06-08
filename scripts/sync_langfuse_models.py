#!/usr/bin/env python3
"""Register project-scoped Langfuse model-price definitions (R5 cost accuracy).

Self-hosted Langfuse v3 generations emit per-token usage under the keys
``input``, ``output``, ``cache_read_input_tokens`` and
``cache_creation_input_tokens`` (plus a derived ``total`` that gets NO price).
For Langfuse to attach a cost to a generation, a model definition whose
``matchPattern`` matches the generation's ``model`` and whose ``prices`` keys
match those usage keys exactly must exist **in the authenticating key's
project**. Model defs are project-scoped, so this runs per project (the R5
setup path calls it after writing creds; backfill re-runs it per project).

This script is idempotent and CREATE-IF-ABSENT ONLY:
  * It lists existing models (``GET /api/public/models?limit=100``, paginated)
    and keys them by ``modelName``.
  * Absent name  -> POST the canonical def (or, in ``--check``, report "would
    create").
  * Present + matching per-token prices -> skip ("ok"). A Langfuse-managed def
    that already prices the keys R5 emits counts as a match (its broader
    matchPattern / extra alias keys are ignored).
  * Present but per-token prices differ -> report DRIFT and do NOTHING.
    ``register_models`` deliberately does NOT correct a stale def and never POSTs
    a duplicate for an existing name. To re-register with corrected prices,
    delete the stale def in Langfuse manually, then re-run.

Create bodies use ``pricingTiers`` (a single default tier whose ``prices`` is a
flat ``{usageKey: pricePerUnit}`` map) — the create endpoint rejects a top-level
``prices`` dict, and the deprecated flat ``inputPrice``/``outputPrice`` cannot
carry cache pricing.

The model-pricing registry is SHARED infrastructure: besides the R5 Stop-hook
turn traces it also backs ``/v3-review`` (ADR-018) Sonnet-worker cost
attribution. Scope changes accordingly — do not treat it as R5-only.

Stdlib-only (urllib, base64, json, argparse) and mirrors
``setup_langfuse_tracing.py``'s HTTP style (base64 Basic auth, raw urllib).
Credentials for the thin ``main()`` are resolved by REUSING
``setup_langfuse_tracing._resolve_creds`` (no second hand-rolled .env parser).

Failure semantics: ``register_models`` raises the domain
``LangfuseModelSyncError`` on a non-2xx GET/POST (NOT ``SystemExit``) so the
setup script can catch-and-warn after creds are already written. The thin
``main()`` converts that to a nonzero exit and hard-fails on missing creds.

Usage:
    python3 scripts/sync_langfuse_models.py            # register missing models
    python3 scripts/sync_langfuse_models.py --check    # report only, never POST
"""

import argparse
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Shared usage-key contract (amendment A1): the four usageDetails keys R5
# generations emit. Referenced by the MODELS price builder AND the contract
# test — single source of truth for the cross-system key set.
USAGE_DETAIL_KEYS = (
    "input",
    "output",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)

UNIT = "TOKENS"

# Per-token prices ($/MTok / 1_000_000), ordered to match USAGE_DETAIL_KEYS.
_PRICE_TABLE = {
    "claude-opus-4-8": {
        "matchPattern": r"(?i)^claude-opus-4-8.*$",
        "prices": (0.000005, 0.000025, 0.0000005, 0.00000625),
    },
    "claude-haiku-4-5": {
        "matchPattern": r"(?i)^claude-haiku-4-5.*$",
        "prices": (0.000001, 0.000005, 0.0000001, 0.00000125),
    },
    "claude-sonnet-4-6": {
        "matchPattern": r"(?i)^claude-sonnet-4-6.*$",
        "prices": (0.000003, 0.000015, 0.0000003, 0.00000375),
    },
}


def _build_models():
    """Materialize MODELS, keying each prices dict by USAGE_DETAIL_KEYS."""
    models = []
    for name, spec in _PRICE_TABLE.items():
        prices = dict(zip(USAGE_DETAIL_KEYS, spec["prices"]))
        models.append(
            {
                "modelName": name,
                "matchPattern": spec["matchPattern"],
                "unit": UNIT,
                "prices": prices,
            }
        )
    return models


MODELS = _build_models()


class LangfuseModelSyncError(Exception):
    """A GET/POST against the Langfuse models API returned a non-2xx status."""


def _auth_header(creds):
    pk = creds["LANGFUSE_PUBLIC_KEY"]
    sk = creds["LANGFUSE_SECRET_KEY"]
    return "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()


def _list_existing(creds):
    """Return {modelName: existing_def} across all pages of the models list."""
    host = creds["LANGFUSE_HOST"].rstrip("/")
    auth = _auth_header(creds)
    opener = urllib.request.build_opener()
    existing = {}
    page = 1
    total_pages = 1
    while page <= total_pages:
        url = f"{host}/api/public/models?limit=100&page={page}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", auth)
        try:
            with opener.open(req, timeout=10) as resp:
                status = getattr(resp, "status", None)
                if status is None:
                    status = resp.getcode()
                body = resp.read()
        except urllib.error.HTTPError as exc:
            raise LangfuseModelSyncError(
                f"GET {url} failed: HTTP {exc.code}"
            ) from exc
        except OSError as exc:
            raise LangfuseModelSyncError(f"GET {url} failed: {exc}") from exc
        if not (200 <= status < 300):
            raise LangfuseModelSyncError(f"GET {url} failed: HTTP {status}")
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, ValueError) as exc:
            raise LangfuseModelSyncError(f"GET {url}: invalid JSON: {exc}") from exc
        for item in payload.get("data", []):
            name = item.get("modelName")
            if name is not None and name not in existing:
                existing[name] = item
        meta = payload.get("meta", {}) or {}
        total_pages = int(meta.get("totalPages", 1) or 1)
        page += 1
    return existing


def _model_payload(model):
    """Build the CreateModelRequest body from a MODELS entry.

    The Langfuse create endpoint does NOT accept a top-level ``prices`` dict
    (the ``prices`` field in GET responses is a computed/derived view). Per
    CreateModelRequest, per-usage-type pricing — including the cache tiers — is
    expressed via ``pricingTiers``: a single default tier whose ``prices`` is a
    flat ``{usageKey: pricePerUnit}`` map. The flat ``inputPrice``/``outputPrice``
    fields are deprecated and cannot carry cache pricing.
    """
    return {
        "modelName": model["modelName"],
        "matchPattern": model["matchPattern"],
        "unit": model["unit"],
        "pricingTiers": [
            {
                "name": "Standard",
                "isDefault": True,
                "priority": 0,
                "conditions": [],
                "prices": dict(model["prices"]),
            }
        ],
    }


def _post_model(creds, model):
    host = creds["LANGFUSE_HOST"].rstrip("/")
    auth = _auth_header(creds)
    opener = urllib.request.build_opener()
    url = f"{host}/api/public/models"
    data = json.dumps(_model_payload(model)).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", auth)
    req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=10) as resp:
            status = getattr(resp, "status", None)
            if status is None:
                status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raise LangfuseModelSyncError(
            f"POST {url} ({model['modelName']}) failed: HTTP {exc.code}"
        ) from exc
    except OSError as exc:
        raise LangfuseModelSyncError(
            f"POST {url} ({model['modelName']}) failed: {exc}"
        ) from exc
    if not (200 <= status < 300):
        raise LangfuseModelSyncError(
            f"POST {url} ({model['modelName']}) failed: HTTP {status}"
        )


def _existing_prices(existing):
    """Normalize a GET model def's ``prices`` to ``{usageKey: float}``.

    The list endpoint returns ``prices`` as a nested ``{key: {"price": n}}`` view
    (and may also expose flat numbers); accept either.
    """
    raw = existing.get("prices")
    out = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            price = v.get("price") if isinstance(v, dict) else v
            if isinstance(price, (int, float)):
                out[k] = float(price)
    return out


def _spec_differs(existing, model):
    """True if the existing def's pricing drifts from our canonical spec.

    Compares ONLY our ``USAGE_DETAIL_KEYS`` prices against the existing
    (normalized) prices. ``matchPattern``/``unit`` are intentionally not
    compared: a Langfuse-managed def legitimately carries a broader regex and
    extra alias usage keys (``input_tokens``, ``input_cache_read``, …) — only
    the per-token prices for the keys R5 emits matter for cost. So a managed def
    that already prices these keys correctly reports ``ok``, not drift.
    """
    existing_prices = _existing_prices(existing)
    for key, want in model["prices"].items():
        got = existing_prices.get(key)
        if got is None or abs(got - float(want)) > 1e-12:
            return True
    return False


def register_models(creds, *, check=False):
    """Create the canonical model defs that are absent; report the rest.

    Returns a human-readable ``list[str]`` of action lines. Raises
    ``LangfuseModelSyncError`` on a non-2xx GET/POST (never ``SystemExit``).
    Create-if-absent only: a present name is never re-POSTed; drift is reported,
    not corrected.
    """
    existing = _list_existing(creds)
    actions = []
    for model in MODELS:
        name = model["modelName"]
        if name not in existing:
            if check:
                actions.append(f"would create {name}")
            else:
                _post_model(creds, model)
                actions.append(f"created {name}")
            continue
        if _spec_differs(existing[name], model):
            actions.append(
                f"drift {name}: existing def differs from canonical spec "
                "(not updated — delete it manually to re-register)"
            )
        else:
            actions.append(f"ok {name}")
    return actions


def _resolve_creds_via_setup():
    """Resolve creds by reusing setup_langfuse_tracing._resolve_creds.

    Family A (stdlib/base64/urllib/cwd-relative infra/.env) single-sourced —
    no second hand-rolled .env parser. Hard-fails (SystemExit) on missing creds.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import setup_langfuse_tracing

    return setup_langfuse_tracing._resolve_creds()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="report which models are present/missing/drifted; never POST",
    )
    args = parser.parse_args(argv)

    creds = _resolve_creds_via_setup()  # hard-fails on missing creds
    try:
        actions = register_models(creds, check=args.check)
    except LangfuseModelSyncError as exc:
        print(f"ERROR: model sync failed: {exc}", file=sys.stderr)
        sys.exit(1)

    for line in actions:
        print(line)


if __name__ == "__main__":
    main()
