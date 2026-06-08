#!/usr/bin/env python3
"""Test suite for scripts/sync_langfuse_models.py — R5 model-price sync.

Follows the framework's TestRunner convention (see tests/test_setup_langfuse_tracing.py).
Run with: python3 tests/test_sync_langfuse_models.py

Dependency-free and NETWORK-FREE: the module's urllib opener is monkeypatched
so GET returns a controlled fake model list and POSTs are captured in-memory.
Never touches the network or a real Langfuse.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import sync_langfuse_models as slm  # noqa: E402

CREDS = {
    "LANGFUSE_PUBLIC_KEY": "pk-lf-x",
    "LANGFUSE_SECRET_KEY": "sk-lf-y",
    "LANGFUSE_HOST": "http://localhost:3000",
}


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests = []

    def test(self, name, condition, msg=""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self):
        print(f"\n{self.passed} passed, {self.failed} failed")
        return 1 if self.failed else 0


class _FakeResponse:
    """Minimal context-manager response mimicking urllib's HTTPResponse."""

    def __init__(self, status, body):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body

    def getcode(self):
        return self.status


class _FakeOpener:
    """Routes GET to a paginated fake list; captures POSTs.

    `pages` is a list of (data_list, totalPages) describing successive GET
    responses keyed by the `page` query param (1-indexed). POST requests are
    appended to `self.posts` as (url, parsed_body_dict).
    """

    def __init__(self, pages, post_status=200):
        self.pages = pages
        self.post_status = post_status
        self.posts = []
        self.get_urls = []

    def open(self, req, timeout=None):
        method = req.get_method()
        url = req.full_url
        if method == "GET":
            self.get_urls.append(url)
            page = 1
            if "page=" in url:
                page = int(url.split("page=")[1].split("&")[0])
            data, total_pages = self.pages[page - 1]
            body = json.dumps(
                {"data": data, "meta": {"totalPages": total_pages, "page": page}}
            )
            return _FakeResponse(200, body)
        if method == "POST":
            body = json.loads(req.data.decode())
            self.posts.append((url, body))
            return _FakeResponse(self.post_status, json.dumps(body))
        raise AssertionError(f"unexpected method {method}")


def _install_opener(monkey_target, opener):
    """Patch build_opener on the module to return our fake opener."""
    original = slm.urllib.request.build_opener
    slm.urllib.request.build_opener = lambda *a, **k: opener
    return original


def _restore_opener(original):
    slm.urllib.request.build_opener = original


def _model_def(name):
    """Build the canonical def the module would POST for `name`."""
    for m in slm.MODELS:
        if m["modelName"] == name:
            return dict(m)
    raise KeyError(name)


# --- expected price table (mirror of the plan, for cross-check) ---
EXPECTED_PRICES = {
    "claude-opus-4-8": {
        "input": 0.000005,
        "output": 0.000025,
        "cache_read_input_tokens": 0.0000005,
        "cache_creation_input_tokens": 0.00000625,
    },
    "claude-haiku-4-5": {
        "input": 0.000001,
        "output": 0.000005,
        "cache_read_input_tokens": 0.0000001,
        "cache_creation_input_tokens": 0.00000125,
    },
    "claude-sonnet-4-6": {
        "input": 0.000003,
        "output": 0.000015,
        "cache_read_input_tokens": 0.0000003,
        "cache_creation_input_tokens": 0.00000375,
    },
}
EXPECTED_PATTERNS = {
    "claude-opus-4-8": r"(?i)^claude-opus-4-8.*$",
    "claude-haiku-4-5": r"(?i)^claude-haiku-4-5.*$",
    "claude-sonnet-4-6": r"(?i)^claude-sonnet-4-6.*$",
}


def test_register_models_posts_three_when_absent(runner):
    print("\ntest_register_models_posts_three_when_absent")
    opener = _FakeOpener(pages=[([], 1)])
    orig = _install_opener(slm, opener)
    try:
        actions = slm.register_models(CREDS)
    finally:
        _restore_opener(orig)

    runner.test(
        "exactly 3 POSTs",
        len(opener.posts) == 3,
        f"posts={[b['modelName'] for _, b in opener.posts]}",
    )
    posted = {b["modelName"]: b for _, b in opener.posts}
    runner.test(
        "posted all three model names",
        set(posted) == set(EXPECTED_PRICES),
        f"got={set(posted)}",
    )
    for name, body in posted.items():
        runner.test(
            f"{name}: unit TOKENS",
            body.get("unit") == "TOKENS",
            f"got={body.get('unit')!r}",
        )
        runner.test(
            f"{name}: matchPattern correct",
            body.get("matchPattern") == EXPECTED_PATTERNS[name],
            f"got={body.get('matchPattern')!r}",
        )
        runner.test(
            f"{name}: prices keyed by USAGE_DETAIL_KEYS",
            set(body.get("prices", {}).keys()) == set(slm.USAGE_DETAIL_KEYS),
            f"got={set(body.get('prices', {}).keys())}",
        )
        runner.test(
            f"{name}: prices values correct",
            body.get("prices") == EXPECTED_PRICES[name],
            f"got={body.get('prices')}",
        )
    runner.test(
        "returns a list of action strings",
        isinstance(actions, list) and all(isinstance(a, str) for a in actions),
        f"got={actions!r}",
    )


def test_register_models_idempotent_skips_existing(runner):
    print("\ntest_register_models_idempotent_skips_existing")
    existing = [_model_def(n) for n in EXPECTED_PRICES]
    opener = _FakeOpener(pages=[(existing, 1)])
    orig = _install_opener(slm, opener)
    try:
        actions = slm.register_models(CREDS)
    finally:
        _restore_opener(orig)
    runner.test("0 POSTs when all exist", len(opener.posts) == 0, f"posts={opener.posts}")
    runner.test("3 action lines returned", len(actions) == 3, f"actions={actions}")


def test_register_models_partial_existence(runner):
    print("\ntest_register_models_partial_existence")
    existing = [_model_def("claude-opus-4-8")]
    opener = _FakeOpener(pages=[(existing, 1)])
    orig = _install_opener(slm, opener)
    try:
        slm.register_models(CREDS)
    finally:
        _restore_opener(orig)
    posted_names = sorted(b["modelName"] for _, b in opener.posts)
    runner.test(
        "exactly 2 POSTs",
        len(opener.posts) == 2,
        f"posts={posted_names}",
    )
    runner.test(
        "the correct two missing models posted",
        posted_names == ["claude-haiku-4-5", "claude-sonnet-4-6"],
        f"got={posted_names}",
    )


def test_prices_keys_match_usage_details(runner):
    print("\ntest_prices_keys_match_usage_details")
    for m in slm.MODELS:
        runner.test(
            f"{m['modelName']}: prices keys == USAGE_DETAIL_KEYS",
            set(m["prices"].keys()) == set(slm.USAGE_DETAIL_KEYS),
            f"got={set(m['prices'].keys())}",
        )
    runner.test(
        "USAGE_DETAIL_KEYS has the 4 expected members",
        set(slm.USAGE_DETAIL_KEYS)
        == {
            "input",
            "output",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        },
        f"got={slm.USAGE_DETAIL_KEYS}",
    )


def test_check_mode_never_posts(runner):
    print("\ntest_check_mode_never_posts")
    opener = _FakeOpener(pages=[([], 1)])
    orig = _install_opener(slm, opener)
    try:
        actions = slm.register_models(CREDS, check=True)
    finally:
        _restore_opener(orig)
    runner.test("0 POSTs in check mode", len(opener.posts) == 0, f"posts={opener.posts}")
    would_create = [a for a in actions if "would create" in a.lower()]
    runner.test(
        "reports 'would create' for all 3",
        len(would_create) == 3,
        f"actions={actions}",
    )


def test_pagination_followed(runner):
    print("\ntest_pagination_followed")
    # page1 (totalPages=2) has opus; page2 has haiku. sonnet absent -> 1 POST.
    page1 = ([_model_def("claude-opus-4-8")], 2)
    page2 = ([_model_def("claude-haiku-4-5")], 2)
    opener = _FakeOpener(pages=[page1, page2])
    orig = _install_opener(slm, opener)
    try:
        slm.register_models(CREDS)
    finally:
        _restore_opener(orig)
    runner.test(
        "fetched both pages",
        len(opener.get_urls) == 2,
        f"get_urls={opener.get_urls}",
    )
    posted_names = sorted(b["modelName"] for _, b in opener.posts)
    runner.test(
        "only the truly-absent model posted",
        posted_names == ["claude-sonnet-4-6"],
        f"got={posted_names}",
    )


def test_missing_creds_hard_fails(runner):
    print("\ntest_missing_creds_hard_fails")
    orig_resolve = slm._resolve_creds_via_setup
    slm._resolve_creds_via_setup = lambda: (_ for _ in ()).throw(SystemExit(1))
    try:
        try:
            slm.main(["--check"])
            runner.test("main exits on missing creds", False, "no SystemExit raised")
        except SystemExit as exc:
            runner.test(
                "main hard-fails (nonzero SystemExit) on missing creds",
                exc.code != 0,
                f"code={exc.code}",
            )
    finally:
        slm._resolve_creds_via_setup = orig_resolve


def test_drift_reported_not_updated(runner):
    print("\ntest_drift_reported_not_updated")
    drifted = _model_def("claude-opus-4-8")
    drifted = dict(drifted)
    drifted["prices"] = dict(drifted["prices"])
    drifted["prices"]["input"] = 0.999  # stale/wrong price
    existing = [drifted] + [_model_def(n) for n in ("claude-haiku-4-5", "claude-sonnet-4-6")]
    opener = _FakeOpener(pages=[(existing, 1)])
    orig = _install_opener(slm, opener)
    try:
        actions = slm.register_models(CREDS)
    finally:
        _restore_opener(orig)
    runner.test("0 POSTs (drift not auto-updated)", len(opener.posts) == 0, f"posts={opener.posts}")
    drift_lines = [a for a in actions if "drift" in a.lower()]
    runner.test(
        "drift action line reported for opus",
        any("claude-opus-4-8" in a for a in drift_lines),
        f"actions={actions}",
    )


def test_non_2xx_post_raises_domain_error(runner):
    print("\ntest_non_2xx_post_raises_domain_error")
    opener = _FakeOpener(pages=[([], 1)], post_status=500)
    orig = _install_opener(slm, opener)
    try:
        try:
            slm.register_models(CREDS)
            runner.test("raises on non-2xx POST", False, "no exception raised")
        except slm.LangfuseModelSyncError:
            runner.test("raises LangfuseModelSyncError on non-2xx POST", True)
        except SystemExit:
            runner.test(
                "raises domain error (not SystemExit) on non-2xx POST",
                False,
                "got SystemExit",
            )
    finally:
        _restore_opener(orig)


def main():
    runner = TestRunner()
    print("Testing scripts/sync_langfuse_models.py")
    test_register_models_posts_three_when_absent(runner)
    test_register_models_idempotent_skips_existing(runner)
    test_register_models_partial_existence(runner)
    test_prices_keys_match_usage_details(runner)
    test_check_mode_never_posts(runner)
    test_pagination_followed(runner)
    test_missing_creds_hard_fails(runner)
    test_drift_reported_not_updated(runner)
    test_non_2xx_post_raises_domain_error(runner)
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
