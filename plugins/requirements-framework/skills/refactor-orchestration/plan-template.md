# <Refactor Title> — <Layer> Redesign Plan

**Branch:** `<branch>`
**Date:** YYYY-MM-DD
**Status:** <Design draft | Design complete | In execution | Done>

## 0. Scope

<One paragraph describing what this plan covers and what it explicitly defers. State the top-down principle: design THIS layer; push unfit responsibilities into the NEXT layer even if there's no clean home yet. Name the input artifact for the next-layer pass (typically: the Export Manifest in §9).>

Everything in this plan has been validated against:
- ADRs <list of ADR numbers, comma-separated>
- <library name> via context7
- <library name> via context7

## 1. Architectural North Star

```
<ASCII diagram of the ideal shape of this layer.
Each line is one structural element. Indent to show containment.>
```

### Forbidden inside <layer>

<Numbered list of things the layer must NOT contain. Be specific and quotable. Each item should be testable structurally (grep, AST).>

1. <e.g. "try/except of any kind">
2. <e.g. "Direct SDK imports (openai, azure.*, anthropic)">
3. <...>

## 2. Validation Findings from context7

| Pattern in v1 design | context7 says | Action |
|---|---|---|
| <library claim, e.g. "with_keepalive() wrapper"> | <doc finding, e.g. "sse-starlette has built-in ping=15"> | <kept / change / delete> |

<Every third-party API the plan touches gets a row here. Zero rows = you haven't run Stage 3 — go back and do it. This table is what makes the plan trustworthy enough to FREEZE.>

## 3. <Path / Wire-shape> Conventions

<Sub-sections for each new convention introduced by this refactor.
E.g. "All streaming endpoints end in /stream", "All commands return Result<T>", "All workers idempotency-key their writes". One subsection per convention.>

### 3.1 <Convention Name>

<Description.>

| Current | New | Rationale |
|---|---|---|
| ... | ... | ... |

## 4. <Shared Primitives>

<Code blocks for the small set of helpers EVERY file in this layer depends on. Aim for ≤ 5 helpers. If you have more, ask whether the layer is doing too much.>

```python
<helper code>
```

## 5. Fixed <Parameter / Field> Order

<Numbered list. Same order in every file. The point is to make every item in the layer scan-identical from the top.>

```
1. <group name>
2. <group name>
...
```

## 6. Canonical <Item> Template

```python
<the one shape every item in this layer conforms to>
```

<One paragraph naming the verb vocabulary or other naming conventions the items use.>

## 7. All N <Items> (Final Shape)

### 7.1 <relative path to file 1>

```python
<full code, ~20-30 lines per item — every endpoint/function/class fully written out>
```

### 7.2 <relative path to file 2>

```python
<...>
```

<Continue for every item in this layer. The reviewer of the plan should be able to read §7 alone and know exactly what the layer looks like after the refactor.>

## 8. Shared Layer Primitives Inventory

| File | Responsibility |
|---|---|
| <path> | <one-line description> |

**Files DELETED from <layer>:**
- <path> — <reason>

## 9. Export Manifest — What <Next Layer> Must Absorb

| From <this layer> | Hands down | Target |
|---|---|---|
| <current responsibility> | <what's being pushed down> | <destination Protocol or module> |

<Every responsibility being pushed down to the next layer gets a row. Even if the next layer has no clean home yet, name the destination Protocol or method. This is the INPUT CONTRACT for the next-pass refactor.>

## 10. Structural Tests to Add

<Numbered list of properties that must hold AFTER the refactor. Each test should fail fast on the first offending file. Use ast for shape checks, grep for forbidden imports.>

1. <e.g. "No `try` (of any form) inside endpoint function bodies in `routers/**`">
2. <e.g. "No imports of `src.app.infrastructure.*` in `routers/**`">
3. <...>

## 11. End State

```
<file tree of the layer after the refactor>
```

```
Total LOC: ~X (down from current ~Y)
Every <item> body: <e.g. "exactly one line">
Every <item> signature: <e.g. "same N-group order">
```

## 12. Breaking Changes Summary

| Old | New | Coordination needed |
|---|---|---|
| <e.g. "POST /chat"> | <e.g. "POST /chat/stream"> | <e.g. "Frontend caller update"> |

<If no breaking changes, write "None.">

## 13. Out of Scope (Next Pass)

<Bulleted list of decisions deliberately deferred to the next layer's pass. Each item is an input to the next refactor's planning.>

- <e.g. "Whether use cases X and Y share a common Provider">
- <e.g. "Final home for shared cancellation primitives">
