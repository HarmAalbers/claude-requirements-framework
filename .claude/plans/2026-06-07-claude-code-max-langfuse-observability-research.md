# Claude Code (Max/OAuth) → self-hosted Langfuse: observability research report

**Date:** 2026-06-07
**Author:** Claude (deep-research workflow + docs agents)
**Scope:** How to run Claude Code authenticated via a Claude **Max subscription** (OAuth login, *no* Anthropic API key) while landing **full observability** of all usage into a **self-hosted Langfuse** instance.
**Method:** 101-agent deep-research workflow (5 search angles → 19 sources → 95 claims → 25 adversarially verified, 2/3-refute kill rule), cross-checked against two targeted documentation agents (Langfuse docs + Claude Code docs).

---

## 0. TL;DR

> **Use Langfuse's official hooks-based Claude Code integration.** A Claude Code `Stop` hook reads the local conversation transcript after each turn and pushes it to Langfuse via the Python SDK. It captures **full prompt/completion/tool content**, works with Max/OAuth **out of the box** (it never touches your auth), carries **zero ToS risk**, and is the exact path Langfuse's maintainers point CLI users to. Optionally layer **native OTEL beta-traces** on top for token/cost/latency operational telemetry.

The instinct — "point Claude Code's `OTEL_*` exporter at Langfuse's OTLP endpoint" — is the **wrong default**: Langfuse ingests the OTLP *traces* signal only, while most of Claude Code's native telemetry is *metrics + log events* that Langfuse will not accept.

---

## 1. The key reframe (why subscription auth is mostly a non-issue)

**Observability that reads *local artifacts* is completely decoupled from how Claude Code authenticates upstream.**

Claude Code writes a full conversation transcript to disk (`~/.claude/projects/**/*.jsonl`) and emits telemetry from its own process **regardless** of whether you logged in with Max OAuth or an API key. Therefore:

- The "does subscription auth survive?" problem **only exists for proxy interception** — the single approach that sits in the network path between Claude Code and Anthropic.
- **Every other approach is auth-agnostic by construction** (hooks, transcript ingestion, native OTEL emitted by the CLI process itself).

This one fact eliminates the ToS-risky options and points directly at the recommended architecture.

---

## 2. The six architectures — comparison matrix

| # | Approach | What lands in Langfuse | Works w/ Max OAuth? | Setup | Fragility | ToS risk |
|---|----------|------------------------|:---:|:---:|:---:|:---:|
| **3** | **Official hooks integration** (Stop hook → SDK) | ✅ **Full content** — prompts, completions, reasoning, tool I/O, tokens | ✅ **Yes** (reads local transcript; auth-blind) | Low | Medium (hook contract + JSONL schema) | **None** |
| 1a | Native OTEL **metrics/logs** → Langfuse OTLP | ❌ **Nothing** — Langfuse ingests *traces only* | ✅ Yes | — | — | None |
| 1b | Native OTEL **beta traces** → Langfuse OTLP | ⚠️ Token/cost/latency spans; content only via `OTEL_LOG_*` gates, 60 KB/attr cap | ✅ Yes (OAuth even *enriches* attrs) | Medium | **High** (beta; names/attrs may change; spans drop in SDK/ACP mode) | None |
| 2 | Proxy interception (LiteLLM / claude-code-proxy / claude-tap / mitmproxy) | ✅ Full fidelity — but to *their* backend; needs a Langfuse bridge (LiteLLM has a native callback) | ⚠️ Reportedly yes, but **mechanism only weakly verified** | High | High | ⚠️ **Real** — forwards subscription OAuth upstream; Anthropic crackdown Feb–Apr 2026 |
| 4 | Agent SDK + Langfuse instrumentation | ✅ Full (OpenInference) | ❌ **No** — Agent SDK may **not** use direct Max OAuth; needs API key or `CLAUDE_CODE_OAUTH_TOKEN` | Medium | Medium | ⚠️ Direct sub-OAuth in SDK is a ToS violation |
| 5 | Post-hoc JSONL batch ingestion of `~/.claude/projects/**/*.jsonl` | ✅ Full content (same data as the Stop hook, batched) | ✅ Yes (reads files) | Low–Med (DIY) | Medium | None |
| 6 | "Official Langfuse guide for Claude Code" | = **approach #3** (the official guide *is* the hooks integration) | ✅ | — | — | None |

---

## 3. What WORKS (high confidence, verified)

### 3.1 Official hooks-based integration — RECOMMENDED ✅
*(deep-research vote: merges 2× 3-0; corroborated)*

- **Mechanism:** registers a `Stop` hook (`langfuse_hook.py` in `~/.claude/hooks`) that runs after each response, reads Claude Code's local conversation transcript, and pushes it to Langfuse via the Python SDK.
- **Requirements:** `langfuse>=4.0,<5` (Python *client* SDK) + Langfuse public/secret keys only.
- **Data captured (full, not metrics-only):** every user prompt, Claude's responses/reasoning, and tool invocations with inputs and outputs; token counts (`input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`).
- **Trace structure in Langfuse UI:** `Claude Code – Turn N` (root) → `Claude Generation N` (generation) → `Tool: <name>` (tool span).
- **Truncation:** long texts truncate at `CC_LANGFUSE_MAX_CHARS` (default **20,000**); records original length + SHA256 when it truncates.
- **NOT captured:** cost figures (token counts present, but no pricing applied — add a Langfuse model-price map if you want cost).
- **Subscription auth:** works **by construction** — transcripts are written locally regardless of how Claude Code authenticates. No API key needed.
- **Also shipped as:** the `langfuse/Claude-Observability-Plugin` marketplace plugin.
- **Why this is "official":** Langfuse maintainers explicitly point CLI users here (discussion #9088: *"we are currently holding off on adding integrations directly in the CLI"*).

**Env vars for this integration:**

| Var | Required | Purpose |
|-----|----------|---------|
| `TRACE_TO_LANGFUSE` | Yes (`"true"`) | Master enable switch |
| `LANGFUSE_PUBLIC_KEY` / `CC_LANGFUSE_PUBLIC_KEY` | Yes | Auth |
| `LANGFUSE_SECRET_KEY` / `CC_LANGFUSE_SECRET_KEY` | Yes | Auth |
| `LANGFUSE_BASE_URL` / `CC_LANGFUSE_BASE_URL` | **Yes for self-host** | Point at your instance (default is EU cloud) |
| `CC_LANGFUSE_MAX_CHARS` | No | Truncation limit (default 20,000 — raise it) |
| `CC_LANGFUSE_DEBUG` | No | Verbose logging |

### 3.2 Claude Code native OpenTelemetry exists and is content-capable ✅
*(deep-research vote: 6 claims, all 3-0)*

- Enabled via `CLAUDE_CODE_ENABLE_TELEMETRY=1` + at least one of `OTEL_METRICS_EXPORTER` / `OTEL_LOGS_EXPORTER` / `OTEL_TRACES_EXPORTER`. Transports: `grpc`, `http/json`, `http/protobuf`.
- **Structural-only by default** (durations, model/tool names, token counts, cost). Full content is **opt-in**:
  - `OTEL_LOG_USER_PROMPTS=1` — prompt text
  - `OTEL_LOG_TOOL_DETAILS=1` — tool args / Bash commands
  - `OTEL_LOG_TOOL_CONTENT=1` — tool I/O bodies in span events (60 KB cap, requires tracing)
  - `OTEL_LOG_RAW_API_BODIES=1` — full Messages API request/response as `api_request_body`/`api_response_body` log events (inline truncated at 60 KB; or `=file:<dir>` untruncated to disk; only extended-thinking is always redacted)
- **Data ceiling of the native path = the entire conversation**, but opt-in, not on by default.
- **Works with Max OAuth and is *better*-attributed:** OAuth sign-in enriches telemetry with `user.email`, `user.account_uuid`, `user.account_id`, `organization.id`; API-key/Bedrock/Vertex/Foundry get only anonymous `user.id` + `session.id`.

### 3.3 Native distributed tracing is BETA, and traces are the ONLY signal Langfuse accepts ✅
*(deep-research vote: 3-0)*

- Requires `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` + `OTEL_TRACES_EXPORTER` on top of `CLAUDE_CODE_ENABLE_TELEMETRY=1`.
- Span hierarchy: `claude_code.interaction` (root, per prompt) → `claude_code.llm_request` (model, token counts, `ttft_ms`, `stop_reason`, GenAI semconv attrs) → `claude_code.tool` children.
- Content redacted in spans unless `OTEL_LOG_*` gates set.
- Trace-context propagation through a custom `ANTHROPIC_BASE_URL` proxy is **off by default** — needs `CLAUDE_CODE_PROPAGATE_TRACEPARENT=1`.
- **Beta caveat:** "span names and attributes may change between releases" → most fragile path. Issue #53954 reports interaction/tool spans missing in Agent SDK/ACP streaming mode.

### 3.4 Langfuse self-hosted OTLP endpoint — traces only ✅
*(deep-research vote: 3-0; corroborated by docs agent)*

- Endpoint: `/api/public/otel` (base) and `/api/public/otel/v1/traces` (signal-specific). Self-host example: `http://localhost:3000/api/public/otel`.
- **Traces signal only.** OTLP over **HTTP/JSON or HTTP/protobuf** — **gRPC unsupported.**
- Auth: HTTP **Basic** with `base64(public_key:secret_key)`; recommended header `x-langfuse-ingestion-version: 4` for real-time "Fast Preview" in the UI.
- Version floor: self-hosted **>= v3.22.0**.
- GenAI semantic-convention mapping (priority high→low): `langfuse.*` > `gen_ai.*` > OpenInference (`input.value`/`output.value`) > MLflow (`mlflow.spanInputs`/`Outputs`). Any span with a `model` attribute → treated as a *generation*.
- Documented-compatible instrumentation: OpenLLMetry, OpenLIT, Arize/OpenInference, MLflow, Pydantic AI (`Agent.instrument_all()`), LlamaIndex, LangChain, CrewAI, AutoGen, Semantic Kernel, smolagents, **Claude Agent SDK (Python + JS/TS via OpenInference)**.

### 3.5 Proxy interception works (full fidelity) but isn't turnkey for Langfuse ✅
*(deep-research vote: merges 6 claims, all 3-0)*

- `seifghazi/claude-code-proxy`: `ANTHROPIC_BASE_URL=http://localhost:3001` → forwards to `https://api.anthropic.com`; captures system prompts, full conversation history, tool schemas/calls, streaming responses, token usage; **stores to local SQLite + dashboard on :5173**.
- `liaohch3/claude-tap`: reverse/forward proxy pointing the base URL at itself, falling back to `HTTPS_PROXY` + CA injection.
- **Both have ZERO Langfuse/OTEL integration** (GitHub code search: 0 hits for `langfuse`/`otel`). Using them for Langfuse requires building a custom export bridge.
- Their docs **do not address** whether OAuth/Max-subscription auth survives proxying (silent, not claimed to fail).
- This establishes the **data ceiling** of the proxy approach (everything), but it's not the recommended Langfuse path.

### 3.6 LiteLLM documents Max-subscription sign-in ✅ (with caveats)
*(deep-research vote: 3-0 on the redirect + login-flow claims)*

- Claude Code redirected via `ANTHROPIC_BASE_URL=http://localhost:4000` + a LiteLLM virtual key in `ANTHROPIC_CUSTOM_HEADERS` (`x-litellm-api-key`).
- Documented login uses Claude Code's native browser OAuth ("Claude account with subscription") → works with non-API-key auth, gives gateway-level usage tracking.
- LiteLLM can forward content to Langfuse via its **own Langfuse callback** (must be configured separately).
- **Caveats below in §4/§5.**

---

## 4. What DOESN'T work (refuted / blocked)

### 4.1 ❌ Pointing native OTEL metrics/logs at Langfuse OTLP captures *nothing useful*
- Langfuse ingests **traces only**. Claude Code's native telemetry is **primarily metrics + log events**. Those signals **cannot reach Langfuse** at all.
- Langfuse co-founder **maxdeichmann (Dec 2025):** *"we currently do not have plans to also expose a logs/metrics endpoint."* (Reaffirmed via docs as of June 2026.)

### 4.2 ❌ Agent SDK cannot use your Max OAuth directly
*(docs agent, Claude Code authentication docs)*
- Agent SDK and `claude -p` on subscription plans draw from a separate **Agent SDK credit** (policy effective ~June 15, 2026).
- **Permitted:** `CLAUDE_CODE_OAUTH_TOKEN` (one-year token from `claude setup-token`) for Max/Pro users, **or** a standard `ANTHROPIC_API_KEY`.
- **NOT permitted:** direct Max/Pro OAuth tokens (`sk-ant-oat01-*`) in the Agent SDK or third-party tools — *"constitutes a violation of the Consumer Terms of Service."*

### 4.3 ❌ `ANTHROPIC_BASE_URL` is *silently bypassed* under subscription OAuth
*(docs agent, authentication docs)*
- `ANTHROPIC_BASE_URL` works for **API-key** auth. OAuth credentials from `/login` (Max/Pro/Team/Enterprise) have **hardcoded endpoints** that bypass a custom base URL — with **no notification**. This is why naive base-URL redirection of a Max session is unreliable.

### 4.4 Three claims explicitly REFUTED by the adversarial verifier
1. *"Native OTEL emits only logs/metrics/events (not traces), so Langfuse can't ingest it at all"* → **refuted 0-3.** Traces (beta) **ARE** ingestible. **Do not over-state the native path as fully blocked.**
2. *"Langfuse OTLP endpoint is documented as traces-only with no metrics/logs"* → marked **1-2** (the verifier split on the exact documentation wording — the *practical* traces-only behavior still holds via 3.4/4.1).
3. *"Claude Code subscription OAuth survives LiteLLM proxying via `forward_client_headers_to_llm_api`"* → **refuted 1-2** (mechanism only weakly verified — see §5.1).

---

## 5. What MIGHT work (uncertain / proceed-with-caution)

### 5.1 ⚠️ LiteLLM forwarding subscription OAuth upstream
- Probably works with `forward_client_headers_to_llm_api: true` + a recent LiteLLM including **PR #14821** (older versions returned 401).
- **But:** the precise OAuth-forwarding mechanism was the **weakest claim in the entire study (split 1-2 vote)**. Anthropic's own LLM-gateway docs document only `ANTHROPIC_AUTH_TOKEN`/API-key auth for gateways and **never bless subscription OAuth through a proxy**. Durability is at Anthropic's discretion.
- Verdict: viable if you want a central gateway, but adds a moving part + ToS/durability uncertainty the hooks path avoids.

### 5.2 ⚠️ Native OTEL beta-traces as a *secondary* operational layer
- Can deliver token/cost/latency/TTFT as spans into Langfuse. Treat as **best-effort** — beta status = most likely to break on a Claude Code update.
- **Open question:** how usefully does conversation *content* render in Langfuse's trace-centric UI when it arrives as span events / `api_request_body` log-style events truncated at 60 KB/attribute? (`file:<dir>` mode writes to disk, which Langfuse cannot follow.)

### 5.3 ⚠️ Post-hoc JSONL batch ingestion (`~/.claude/projects/**/*.jsonl`)
- Distinct from the near-realtime Stop hook. The transcript schema is known (`type`: user/assistant/system; `message.content` blocks: text/thinking/tool_use/tool_result; `message.usage` tokens; `uuid`/`parentUuid`/`timestamp`/`sessionId`/`cwd`/`gitBranch`).
- **Open question:** no *supported batch importer* was found — you'd build one on the same SDK calls the Stop hook uses. Fine for backfill / DIY, but unmaintained-by-default.

### 5.4 ⚠️ mitmproxy TLS interception of OAuth traffic
- Named in scope but **not covered by any surviving claim.** Whether TLS interception of the OAuth flow works without breaking Anthropic's auth, and its ToS posture vs. base-URL redirection, is **unverified**. Assume higher risk.

---

## 6. Recommended architecture (for this environment)

**Context:** self-hosted **Langfuse v3** (`infra/docker-compose.yml`: `langfuse:3` + ClickHouse / MinIO / Redis / Postgres), single-user, Max subscription. Creds source: `infra/.env`.

### Primary — official hooks integration (content backbone)
1. `pip install "langfuse>=4,<5"` in the Python the hook runs under.
   - **Version note:** SDK v4 is the *client*; it talks to **server v3.22+** fine over the OTel-backed ingestion path. There is **no "server v4"** to upgrade to — don't let the numbers confuse you.
2. Drop the official `langfuse_hook.py` into `~/.claude/hooks/` and register it as a **`Stop`** hook in `settings.json`.
3. Feed self-hosted creds from `infra/.env`:
   - `LANGFUSE_HOST=http://localhost:3000` (your instance — **not** the EU-cloud default)
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`
   - `TRACE_TO_LANGFUSE=true`
4. Raise `CC_LANGFUSE_MAX_CHARS` well above the 20,000 default to avoid truncating long turns.

**Result:** every turn → `Claude Code – Turn N` → `Claude Generation N` → `Tool: <name>`, with full prompts, completions, tool I/O, and token counts. Add a Langfuse model-price mapping if you want cost figures.

### Optional second layer — native OTEL beta traces (operational telemetry)
If you also want token/cost/latency dashboards:
```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:3000/api/public/otel
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=Basic <base64(pk:sk)>,x-langfuse-ingestion-version=4"
# optional content gates (privacy trade-off — single-user/self-hosted, so acceptable):
# export OTEL_LOG_USER_PROMPTS=1
```
Treat as best-effort; it's the most update-fragile piece.

### Avoid
- **Proxy interception** — ToS-risky, the auth-survival mechanism is the least-verified finding, and it needs a custom Langfuse bridge anyway.
- **Agent SDK route** — cannot use your Max OAuth directly.

---

## 7. Assumptions

1. **"Self-hosted Langfuse" = the `infra/docker-compose.yml` stack** (Langfuse server v3, reachable at `http://localhost:3000`). If you run it elsewhere, substitute the host.
2. **Single-user, self-hosted, no PII concern** → enabling content-capture gates (`OTEL_LOG_USER_PROMPTS`, raising `MAX_CHARS`) is acceptable. (Consistent with the project's "PII masking is out of scope" stance.)
3. **"Full observability" = full prompt/completion/tool content**, not metrics-only. This rules out the default native-OTEL config.
4. **You stay on Max OAuth and won't add an API key.** If an API key were acceptable, the Agent-SDK + OpenInference route opens up.
5. **Claude Code's Stop-hook contract and JSONL transcript schema remain stable** in the near term (true today; undocumented as a formal contract).
6. **Findings are time-stamped 2026-06-07.** The traces-only OTLP limit, the "no logs/metrics endpoint" stance (Dec 2025 / Mar 2026), and the active ToS crackdown (Feb–Apr 2026) are all subject to change.

---

## 8. Possible outcomes / what could break

| Scenario | Likelihood | Impact | Mitigation |
|----------|-----------|--------|-----------|
| Claude Code changes the `Stop` hook payload or JSONL schema | Medium | Hooks integration silently stops/garbles | Pin the integration version; the hook fails-open (won't block Claude Code); monitor for empty traces |
| Native beta-trace span names/attrs change | High (it's beta) | Operational dashboards break | Keep beta-traces as *secondary*; don't depend on it for content |
| Anthropic tightens OAuth/proxy enforcement further | Medium | Any proxy approach dies | Recommended path uses no proxy → unaffected |
| Langfuse adds a logs/metrics OTLP endpoint later | Low (maintainers said no) | Native metrics could finally land | Re-evaluate if it ships |
| Token-cost not showing in Langfuse | Certain (by design) | No spend visibility | Add Langfuse model-price mapping |
| Long turns truncated at 20k chars | Certain if default kept | Lost content (SHA256+len recorded) | Raise `CC_LANGFUSE_MAX_CHARS` |
| Agent SDK / `claude -p` usage under Max | N/A | Draws separate "Agent SDK credit"; direct OAuth = ToS violation | Use `CLAUDE_CODE_OAUTH_TOKEN` or API key if SDK needed |

---

## 9. Open questions (not resolved by this research)

1. **Agent SDK + subscription OAuth wrapped in Langfuse** (research item 4) not directly covered: does the SDK's CLI-child-process OTEL emit beta traces Langfuse ingests cleanly? Issue #53954 hints SDK/ACP streaming may drop interaction/tool spans.
2. **Supported batch importer** for `~/.claude` JSONL transcripts (item 5) — none found; must be built on the same SDK calls the Stop hook uses.
3. **Native beta-trace content rendering** in Langfuse's trace UI given 60 KB/attribute caps and `file:<dir>` mode (which Langfuse can't follow).
4. **mitmproxy interception** of OAuth-authenticated traffic — does TLS interception break Anthropic auth, and what's the ToS posture vs. base-URL redirection?

---

## 10. Sources

### Primary (vendor docs / project source)
- `https://code.claude.com/docs/en/monitoring-usage` — native OTEL env vars, signals, content gates, beta traces
- `https://code.claude.com/docs/en/agent-sdk/observability` — observability env var reference
- `https://code.claude.com/docs/en/authentication` — auth priority, `ANTHROPIC_BASE_URL` OAuth bypass, Agent SDK policy
- `https://code.claude.com/docs/en/hooks` — hook events, `transcript_path`, JSONL format
- `https://code.claude.com/docs/en/legal-and-compliance` — ToS / compliance
- `https://langfuse.com/integrations/other/claude-code` — **official hooks integration (recommended path)**
- `https://langfuse.com/integrations/native/opentelemetry` — OTLP endpoint, traces-only, attribute mapping
- `https://langfuse.com/integrations/frameworks/claude-agent-sdk` — Agent SDK + OpenInference
- `https://github.com/orgs/langfuse/discussions/9088` — maintainers redirect CLI users to hooks; "no logs/metrics endpoint"
- `https://github.com/orgs/langfuse/discussions/9242` — OTel discussion
- `https://docs.litellm.ai/docs/tutorials/claude_code_max_subscription` — LiteLLM Max-subscription tutorial
- `https://github.com/seifghazi/claude-code-proxy` — base-URL interception proxy (SQLite/dashboard)
- `https://github.com/liaohch3/claude-tap` — reverse/forward proxy + CA injection
- `https://github.com/pdhoolia/langfuse-claude-code-plugin` — community hooks plugin
- `https://github.com/doneyli/claude-code-langfuse-template` — community template
- `https://github.com/michaeloboyle/claude-langfuse-monitor` — community monitor

### Secondary / supporting
- `https://github.com/BerriAI/litellm/issues/13380`, `/issues/29190` — LiteLLM Claude Code threads (PR #14821 context)
- `https://generalanalysis.com/guides/claude-code-control-observability-opentelemetry` — OTEL guide (blog)
- `https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/` — ToS crackdown
- `https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/` — ToS crackdown (corroborating)
- Issue #53954 (Claude Code) — interaction/tool spans missing in Agent SDK/ACP streaming mode

### Verification stats
5 angles · 19 sources fetched · 95 claims extracted · 25 verified (3-vote adversarial) · 22 confirmed · 3 killed · 7 findings after synthesis · 101 agent calls.
