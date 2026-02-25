# Testing Anti-Patterns

**Load this reference when:** writing or changing tests, adding mocks, or tempted to add test-only methods to production code.

## Overview

Tests must verify real behavior, not mock behavior. Mocks are a means to isolate, not the thing being tested.

**Core principle:** Test what the code does, not what the mocks do.

**Following strict TDD prevents these anti-patterns.**

## The Iron Laws

```
1. NEVER test mock behavior
2. NEVER add test-only methods to production classes
3. NEVER mock without understanding dependencies
```

## Anti-Pattern 1: Testing Mock Behavior

**The violation:**
```python
# BAD: Testing that the mock exists
def test_renders_sidebar(mocker):
    mock_sidebar = mocker.patch("app.sidebar.Sidebar")
    page = render_page()
    mock_sidebar.assert_called_once()  # Tests mock, not page
```

**Why this is wrong:**
- You're verifying the mock works, not that the component works
- Test passes when mock is present, fails when it's not
- Tells you nothing about real behavior

**The fix:**
```python
# GOOD: Test real component behavior
def test_renders_sidebar():
    page = render_page()  # Don't mock sidebar
    assert page.sidebar is not None
    assert page.sidebar.items == expected_items
```

### Gate Function

```
BEFORE asserting on any mock element:
  Ask: "Am I testing real component behavior or just mock existence?"

  IF testing mock existence:
    STOP - Delete the assertion or unmock the component

  Test real behavior instead
```

## Anti-Pattern 2: Test-Only Methods in Production

**The violation:**
```python
# BAD: _reset() only used in tests
class SessionManager:
    def _reset(self):
        """Only called in tests!"""
        self._sessions.clear()
        self._active = None
```

**Why this is wrong:**
- Production class polluted with test-only code
- Dangerous if accidentally called in production
- Violates YAGNI and separation of concerns

**The fix:**
```python
# GOOD: Test utilities handle test cleanup
# session_manager.py has no _reset() - it's not needed in production

# In conftest.py or test_utils.py:
@pytest.fixture
def clean_session_manager():
    manager = SessionManager()
    yield manager
    # Cleanup handled by fixture teardown, not production code
```

### Gate Function

```
BEFORE adding any method to production class:
  Ask: "Is this only used by tests?"

  IF yes:
    STOP - Don't add it
    Put it in test utilities / fixtures instead

  Ask: "Does this class own this resource's lifecycle?"

  IF no:
    STOP - Wrong class for this method
```

## Anti-Pattern 3: Mocking Without Understanding

**The violation:**
```python
# BAD: Mock breaks test logic
def test_detects_duplicate_config(mocker):
    # Mock prevents config write that test depends on!
    mocker.patch("config.ConfigLoader.save", return_value=None)

    add_config(entry)
    add_config(entry)  # Should raise - but won't because save was mocked!
```

**Why this is wrong:**
- Mocked method had side effect test depended on (writing config)
- Over-mocking to "be safe" breaks actual behavior
- Test passes for wrong reason or fails mysteriously

**The fix:**
```python
# GOOD: Mock at correct level
def test_detects_duplicate_config(tmp_path):
    config_file = tmp_path / "config.yaml"
    loader = ConfigLoader(config_file)

    add_config(loader, entry)   # Config written to temp file
    with pytest.raises(DuplicateError):
        add_config(loader, entry)  # Duplicate detected
```

### Gate Function

```
BEFORE mocking any method:
  STOP - Don't mock yet

  1. Ask: "What side effects does the real method have?"
  2. Ask: "Does this test depend on any of those side effects?"
  3. Ask: "Do I fully understand what this test needs?"

  IF depends on side effects:
    Mock at lower level (the actual slow/external operation)
    OR use test doubles that preserve necessary behavior
    NOT the high-level method the test depends on

  IF unsure what test depends on:
    Run test with real implementation FIRST
    Observe what actually needs to happen
    THEN add minimal mocking at the right level
```

## Anti-Pattern 4: Incomplete Mocks

**The violation:**
```python
# BAD: Partial mock - only fields you think you need
mock_response = {
    "status": "success",
    "data": {"user_id": "123", "name": "Alice"}
    # Missing: metadata that downstream code uses
}

# Later: breaks when code accesses response["metadata"]["request_id"]
```

**Why this is wrong:**
- Partial mocks hide structural assumptions
- Downstream code may depend on fields you didn't include
- Tests pass but integration fails

**The fix:**
```python
# GOOD: Mirror real API completeness
mock_response = {
    "status": "success",
    "data": {"user_id": "123", "name": "Alice"},
    "metadata": {"request_id": "req-789", "timestamp": 1234567890}
    # All fields real API returns
}
```

## Anti-Pattern 5: Integration Tests as Afterthought

**The violation:**
```
Implementation complete
No tests written
"Ready for testing"
```

**The fix:**
```
TDD cycle:
1. Write failing test
2. Implement to pass
3. Refactor
4. THEN claim complete
```

## When Mocks Become Too Complex

**Warning signs:**
- Mock setup longer than test logic
- Mocking everything to make test pass
- Mocks missing methods real components have
- Test breaks when mock changes

**Consider:** Integration tests with real components often simpler than complex mocks.

## Quick Reference

| Anti-Pattern | Fix |
|--------------|-----|
| Assert on mock elements | Test real component or unmock it |
| Test-only methods in production | Move to test utilities / fixtures |
| Mock without understanding | Understand dependencies first, mock minimally |
| Incomplete mocks | Mirror real API completely |
| Tests as afterthought | TDD — tests first |
| Over-complex mocks | Consider integration tests |

## Red Flags

- Assertion checks for mock IDs or mock call counts as primary test logic
- Methods only called in test files
- Mock setup is >50% of test
- Test fails when you remove mock
- Can't explain why mock is needed
- Mocking "just to be safe"

## The Bottom Line

**Mocks are tools to isolate, not things to test.**

If TDD reveals you're testing mock behavior, you've gone wrong.

Fix: Test real behavior or question why you're mocking at all.
