# Unified Requirements Framework - Implementation Plan v2.0

**Document Version**: 2.0 (Revised Architecture)
**Created**: 2025-12-08
**Status**: Ready for Implementation
**Estimated Effort**: 15-20 hours (MVP: 4-6 hours)

---

## ARCHITECTURE PRINCIPLES

### 1. Framework Lives in ~/.claude (User-Level)
- All Python code, libraries, and global config in `~/.claude/hooks/`
- Framework updated independently of projects
- **Nothing in project git repos except config files**

### 2. Projects Opt-In via Config
- Projects add `.claude/requirements.yaml` to enable/configure
- Config files ARE versioned (team sees and reviews them)
- No config = requirements framework skipped for that project

### 3. State is Local (Never Committed)
- State files in `.git/requirements/` (gitignored automatically)
- Per-branch, per-session state tracking
- Cleaned up automatically

### 4. Zero Dependencies
- **No hookify** - completely standalone
- **No external packages** required (uses stdlib only)
- **Optional**: PyYAML for config (falls back to JSON if missing)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Directory Structure](#2-directory-structure)
3. [Component Specifications](#3-component-specifications)
4. [Implementation Phases](#4-implementation-phases)
5. [Configuration Reference](#5-configuration-reference)
6. [Per-Project Setup](#6-per-project-setup)
7. [API Reference](#7-api-reference)
8. [Edge Cases & Solutions](#8-edge-cases--solutions)
9. [Testing Strategy](#9-testing-strategy)
10. [Migration & Rollout](#10-migration--rollout)
11. [User Workflows & Use Cases](#11-user-workflows--use-cases)

---

## 1. Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Claude Code Session                    │
│                  (in project directory)                  │
│                                                           │
│  ┌─────────────┐    ┌──────────────────────────────┐   │
│  │   Edit/     │───▶│  PreToolUse Hook             │   │
│  │   Write/    │    │  (check-requirements.py)     │   │
│  │   MultiEdit │    └──────────────┬───────────────┘   │
│  └─────────────┘                   │                    │
│                                     ▼                    │
│                    ┌────────────────────────────┐       │
│                    │  Requirements Manager      │       │
│                    │  (~/.claude/hooks/lib/)    │       │
│                    └──────┬──────────────┬──────┘       │
│                           │              │               │
│             ┌─────────────▼───┐    ┌────▼──────────┐   │
│             │  Local State    │    │  Project      │   │
│             │  (.git/req/)    │    │  Config       │   │
│             └─────────────────┘    │  (.claude/)   │   │
│                                     └───────────────┘   │
└─────────────────────────────────────────────────────────┘

                            ▲
                            │
              ┌─────────────┴──────────────┐
              │  Framework in ~/.claude    │
              │  - Python libraries        │
              │  - Hook scripts            │
              │  - Global config           │
              └────────────────────────────┘
```

### Key Design Decisions

#### Decision 1: Framework Location
**Choice**: All framework code in `~/.claude/hooks/`

**Rationale**:
- User-level installation (not per-project)
- Updated once, affects all projects
- No code clutter in project repos
- Easy to maintain centrally

#### Decision 2: Project Integration
**Choice**: Projects only have `.claude/requirements.yaml` config file

**Rationale**:
- Minimal per-project footprint
- Config is versioned and code-reviewed
- Easy to see what requirements apply
- Can be disabled per-project

#### Decision 3: State Storage
**Choice**: State files in `.git/requirements/` (auto-gitignored)

**Rationale**:
- Lives with the repo (not global)
- Never committed (private state)
- Auto-cleaned when branch deleted
- Project-specific session tracking

#### Decision 4: Zero External Dependencies
**Choice**: Pure Python stdlib (PyYAML optional)

**Rationale**:
- Works in any Python 3.9+ environment
- No pip install needed
- Falls back gracefully (YAML → JSON)
- Reduces environment friction

---

## 2. Directory Structure

### User-Level Framework (~/.claude)

```
~/.claude/
├── hooks/
│   ├── check-requirements.py          # PreToolUse hook entry point
│   ├── requirements-cli.py            # CLI tool for users
│   │
│   └── lib/                           # Framework libraries
│       ├── __init__.py
│       ├── requirements.py            # Core BranchRequirements class
│       ├── config.py                  # Configuration loader
│       ├── state_storage.py           # State file I/O
│       ├── git_utils.py               # Git operations
│       └── session.py                 # Session ID management
│
├── requirements.yaml                  # Global default config
│
└── settings.json                      # Claude Code settings
    └── hooks.PreToolUse               # References check-requirements.py
```

### Project Integration (Per-Project)

```
/Users/harm/Work/solarmonkey-app/
├── .git/
│   └── requirements/                  # State files (gitignored)
│       ├── feature-auth.json
│       ├── feature-payments.json
│       └── bugfix-login.json
│
├── .gitignore                         # Contains: .git/requirements/
│
└── .claude/
    └── requirements.yaml              # Project config (VERSIONED)
```

### What Goes Where

| File Type | Location | Versioned? | Purpose |
|-----------|----------|------------|---------|
| Python code | `~/.claude/hooks/` | No | Framework implementation |
| Global config | `~/.claude/requirements.yaml` | No | User defaults |
| Project config | `.claude/requirements.yaml` | **YES** | Project requirements |
| State files | `.git/requirements/*.json` | No | Runtime state |
| Hook registration | `~/.claude/settings.json` | No | Claude Code integration |

---

## 3. Component Specifications

### 3.1 Hook Entry Point (`~/.claude/hooks/check-requirements.py`)

**Purpose**: Claude Code PreToolUse hook integration

**Key Features**:
- Detects project directory
- Loads project config (if exists)
- Checks requirements
- Outputs "ask" decision if not satisfied
- **Fails open** on any error

**Pseudocode**:
```python
def main():
    try:
        # Get context
        tool_name = get_tool_from_stdin()
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR')

        # Only check on write operations
        if tool_name not in ['Edit', 'Write', 'MultiEdit']:
            exit(0)

        # Check if project has requirements config
        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
        if not config_file.exists():
            exit(0)  # No config = no requirements

        # Load config and check requirements
        config = load_config(project_dir)
        if not config.get('enabled', True):
            exit(0)  # Disabled for this project

        reqs = BranchRequirements(branch, session_id, project_dir)

        for req_name in get_enabled_requirements(config):
            if not reqs.is_satisfied(req_name):
                output_prompt(req_name, config)
                exit(0)

        # All satisfied
        exit(0)

    except Exception as e:
        # FAIL OPEN with visible warning
        log_error(f"Requirements check failed: {e}")
        print(f"⚠️ Requirements check error: {e}", file=sys.stderr)
        exit(0)
```

### 3.2 Configuration Loader (`lib/config.py`)

**Purpose**: Load and merge config files

**Configuration Cascade**:
```
1. Global defaults (~/.claude/requirements.yaml)
   ↓ (merge)
2. Project config (.claude/requirements.yaml)
   ↓ (override)
3. Local overrides (.claude/requirements.local.yaml) [gitignored]
```

**Key Methods**:
```python
class RequirementsConfig:
    def __init__(self, project_dir: str):
        """Load config for project."""
        self.project_dir = project_dir
        self._config = self._load_cascade()

    def _load_cascade(self) -> dict:
        """Load and merge: global → project → local."""
        config = {}

        # 1. Global
        global_file = Path.home() / '.claude' / 'requirements.yaml'
        if global_file.exists():
            config = load_yaml_or_json(global_file)

        # 2. Project
        project_file = Path(self.project_dir) / '.claude' / 'requirements.yaml'
        if project_file.exists():
            project_config = load_yaml_or_json(project_file)
            if project_config.get('inherit', True):
                deep_merge(config, project_config)
            else:
                config = project_config

        # 3. Local overrides
        local_file = Path(self.project_dir) / '.claude' / 'requirements.local.yaml'
        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
            deep_merge(config, local_config)

        return config

    def is_enabled(self, req_name: str) -> bool:
        """Check if requirement is enabled."""

    def get_requirement(self, req_name: str) -> dict:
        """Get full config for requirement."""
```

**Zero-Dependency Config Loading**:
```python
def load_yaml_or_json(path: Path) -> dict:
    """Load YAML if available, else JSON, else fail gracefully."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # No PyYAML - try JSON
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ Config {path} is not valid JSON (PyYAML not available)",
                  file=sys.stderr)
            return {}
    except Exception as e:
        print(f"⚠️ Could not load {path}: {e}", file=sys.stderr)
        return {}
```

### 3.3 State Storage (`lib/state_storage.py`)

**Purpose**: Manage per-branch state files

**State File Format**:
```json
{
  "version": "1.0",
  "branch": "feature/auth",
  "project": "/Users/harm/Work/solarmonkey-app",
  "created_at": 1234567890,
  "updated_at": 1234567890,
  "requirements": {
    "commit_plan": {
      "scope": "session",
      "sessions": {
        "abc123": {
          "satisfied": true,
          "satisfied_at": 1234567890,
          "satisfied_by": "cli",
          "expires_at": null
        }
      }
    },
    "github_ticket": {
      "scope": "branch",
      "satisfied": true,
      "satisfied_at": 1234567890,
      "metadata": {
        "ticket": "#1234"
      }
    }
  }
}
```

**Location**: `.git/requirements/` in project directory

**Key Methods**:
```python
def get_state_dir(project_dir: str) -> Path:
    """Get state directory for project."""
    return Path(project_dir) / '.git' / 'requirements'

def load_state(branch: str, project_dir: str) -> dict:
    """Load state for branch in project."""

def save_state(branch: str, project_dir: str, state: dict) -> None:
    """Save state atomically with file locking."""

def delete_state(branch: str, project_dir: str) -> None:
    """Delete state file."""
```

### 3.4 Requirements Manager (`lib/requirements.py`)

**Purpose**: Core API for checking/satisfying requirements

```python
class BranchRequirements:
    """Main API for requirements management."""

    def __init__(self, branch: str, session_id: str, project_dir: str):
        """Initialize for branch in project."""
        self.branch = branch
        self.session_id = session_id
        self.project_dir = project_dir
        self._state = load_state(branch, project_dir)

    def is_satisfied(self, req_name: str, scope: str = 'session') -> bool:
        """Check if requirement satisfied (with TTL check)."""

    def satisfy(self, req_name: str, scope: str = 'session',
                method: str = 'manual', metadata: dict = None,
                ttl: int = None) -> None:
        """Mark requirement as satisfied."""

    def clear(self, req_name: str) -> None:
        """Clear requirement."""

    def get_status(self) -> dict:
        """Get full status."""
```

### 3.5 CLI Tool (`~/.claude/hooks/requirements-cli.py`)

**Purpose**: User-facing command-line interface

**Commands**:
```bash
# Status (must be run in project directory)
cd /Users/harm/Work/solarmonkey-app
python3 ~/.claude/hooks/requirements-cli.py status

# Satisfy
python3 ~/.claude/hooks/requirements-cli.py satisfy commit_plan

# Clear
python3 ~/.claude/hooks/requirements-cli.py clear commit_plan

# List (show all tracked branches in current project)
python3 ~/.claude/hooks/requirements-cli.py list

# Prune (cleanup stale state in current project)
python3 ~/.claude/hooks/requirements-cli.py prune
```

**Shell Alias** (add to ~/.bashrc or ~/.zshrc):
```bash
alias req='python3 ~/.claude/hooks/requirements-cli.py'

# Usage:
req status
req satisfy commit_plan
```

---

## 4. Implementation Phases

### Phase 1: MVP (4-6 hours)

**Goal**: Basic commit_plan requirement working

#### Step 1.1: Create Framework Structure (15 min)

```bash
# Create directories
mkdir -p ~/.claude/hooks/lib
touch ~/.claude/hooks/lib/__init__.py

# Create state directory in project
mkdir -p /Users/harm/Work/solarmonkey-app/.git/requirements

# Update .gitignore in project
echo ".git/requirements/" >> /Users/harm/Work/solarmonkey-app/.gitignore
```

#### Step 1.2: Implement Session Management (30 min)

Create `~/.claude/hooks/lib/session.py`:

```python
#!/usr/bin/env python3
"""Session ID management."""
import os
import uuid
from pathlib import Path

def get_session_id() -> str:
    """
    Get or generate session ID.

    Strategy:
    1. Check CLAUDE_SESSION_ID env var
    2. Use parent process ID (stable for CLI session)
    3. Generate and cache in temp file
    """
    # Check environment
    if 'CLAUDE_SESSION_ID' in os.environ:
        return os.environ['CLAUDE_SESSION_ID']

    # Use parent PID as stable session identifier
    ppid = os.getppid()
    session_file = Path(f"/tmp/claude-session-{ppid}.id")

    if session_file.exists():
        try:
            return session_file.read_text().strip()
        except:
            pass

    # Generate new
    session_id = uuid.uuid4().hex[:8]
    try:
        session_file.write_text(session_id)
    except:
        pass  # Best effort

    return session_id
```

#### Step 1.3: Implement Git Utilities (30 min)

Create `~/.claude/hooks/lib/git_utils.py`:

```python
#!/usr/bin/env python3
"""Git operation helpers."""
import subprocess
import os

def run_git(cmd: str, cwd: str = None) -> tuple[int, str, str]:
    """Run git command. Returns (exit_code, stdout, stderr)."""
    if cwd is None:
        cwd = os.getcwd()

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=3
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)

def get_current_branch(project_dir: str = None) -> str | None:
    """Get current branch name."""
    code, branch, _ = run_git("git symbolic-ref --short HEAD", project_dir)
    return branch if code == 0 else None

def get_all_branches(project_dir: str = None) -> list[str]:
    """Get all local branches."""
    code, output, _ = run_git(
        "git for-each-ref --format='%(refname:short)' refs/heads/",
        project_dir
    )
    if code != 0:
        return []
    return [b.strip("'") for b in output.split('\n') if b]

def is_git_repo(project_dir: str = None) -> bool:
    """Check if directory is a git repo."""
    code, _, _ = run_git("git rev-parse --git-dir", project_dir)
    return code == 0
```

#### Step 1.4: Implement State Storage (45 min)

Create `~/.claude/hooks/lib/state_storage.py`:

```python
#!/usr/bin/env python3
"""State file storage with atomic operations."""
import json
import os
import time
from pathlib import Path
import fcntl

def get_state_dir(project_dir: str) -> Path:
    """Get state directory for project."""
    return Path(project_dir) / '.git' / 'requirements'

def ensure_state_dir(project_dir: str):
    """Create state directory if needed."""
    get_state_dir(project_dir).mkdir(parents=True, exist_ok=True)

def branch_to_filename(branch: str) -> str:
    """Convert branch name to safe filename."""
    safe = branch.replace('/', '-').replace('\\', '-')
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in safe)
    return f"{safe}.json"

def get_state_path(branch: str, project_dir: str) -> Path:
    """Get path to state file."""
    ensure_state_dir(project_dir)
    return get_state_dir(project_dir) / branch_to_filename(branch)

def load_state(branch: str, project_dir: str) -> dict:
    """Load state for branch. Returns empty state if not found."""
    path = get_state_path(branch, project_dir)

    if not path.exists():
        return create_empty_state(branch, project_dir)

    try:
        with open(path, 'r') as f:
            fcntl.flock(f, fcntl.LOCK_SH)  # Shared lock
            try:
                state = json.load(f)
                if state.get('version') != '1.0':
                    return create_empty_state(branch, project_dir)
                return state
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError) as e:
        # Corrupted - return empty state
        print(f"⚠️ State file corrupted for {branch}: {e}",
              file=sys.stderr)
        return create_empty_state(branch, project_dir)

def save_state(branch: str, project_dir: str, state: dict) -> None:
    """Save state atomically."""
    path = get_state_path(branch, project_dir)
    state['updated_at'] = int(time.time())

    # Write to temp, then rename
    temp_path = path.with_suffix('.tmp')

    try:
        with open(temp_path, 'w') as f:
            fcntl.flock(f, fcntl.LOCK_EX)  # Exclusive lock
            try:
                json.dump(state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

        # Atomic rename
        temp_path.rename(path)
    except OSError as e:
        print(f"⚠️ Could not save state for {branch}: {e}",
              file=sys.stderr)
        if temp_path.exists():
            temp_path.unlink()

def create_empty_state(branch: str, project_dir: str) -> dict:
    """Create empty state structure."""
    return {
        "version": "1.0",
        "branch": branch,
        "project": project_dir,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
        "requirements": {}
    }

def delete_state(branch: str, project_dir: str) -> None:
    """Delete state file."""
    path = get_state_path(branch, project_dir)
    if path.exists():
        path.unlink()

def list_all_states(project_dir: str) -> list[tuple[str, Path]]:
    """List all state files in project."""
    state_dir = get_state_dir(project_dir)
    if not state_dir.exists():
        return []

    states = []
    for path in state_dir.glob('*.json'):
        if path.name.endswith('.tmp'):
            continue
        try:
            with open(path) as f:
                state = json.load(f)
                branch = state.get('branch', path.stem)
                states.append((branch, path))
        except:
            states.append((path.stem, path))

    return states
```

#### Step 1.5: Implement Config Loader (45 min)

Create `~/.claude/hooks/lib/config.py`:

```python
#!/usr/bin/env python3
"""Configuration loading."""
import json
import sys
from pathlib import Path

def load_yaml_or_json(path: Path) -> dict:
    """Load YAML if available, else JSON."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # No PyYAML - try JSON
        try:
            with open(path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️ Config {path} is invalid JSON (PyYAML not installed)",
                  file=sys.stderr)
            return {}
    except Exception as e:
        print(f"⚠️ Could not load {path}: {e}", file=sys.stderr)
        return {}

def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base

class RequirementsConfig:
    """Configuration manager."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self._config = self._load_cascade()

    def _load_cascade(self) -> dict:
        """Load: global → project → local."""
        config = {'requirements': {}}

        # 1. Global defaults
        global_file = Path.home() / '.claude' / 'requirements.yaml'
        if global_file.exists():
            global_config = load_yaml_or_json(global_file)
            config = global_config

        # 2. Project config
        project_file = Path(self.project_dir) / '.claude' / 'requirements.yaml'
        if project_file.exists():
            project_config = load_yaml_or_json(project_file)

            if project_config.get('inherit', True):
                # Merge
                deep_merge(config, project_config)
            else:
                # Replace
                config = project_config

        # 3. Local overrides (gitignored)
        local_file = Path(self.project_dir) / '.claude' / 'requirements.local.yaml'
        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
            deep_merge(config, local_config)

        return config

    def is_enabled(self) -> bool:
        """Check if framework enabled for this project."""
        return self._config.get('enabled', True)

    def get_requirement(self, name: str) -> dict | None:
        """Get requirement config."""
        return self._config.get('requirements', {}).get(name)

    def get_all_requirements(self) -> list[str]:
        """Get all requirement names."""
        return list(self._config.get('requirements', {}).keys())

    def is_requirement_enabled(self, name: str) -> bool:
        """Check if specific requirement enabled."""
        req = self.get_requirement(name)
        return req is not None and req.get('enabled', False)

    def get_scope(self, name: str) -> str:
        """Get scope (session/branch/permanent)."""
        req = self.get_requirement(name)
        return req.get('scope', 'session') if req else 'session'

    def get_trigger_tools(self, name: str) -> list[str]:
        """Get tools that trigger this requirement."""
        req = self.get_requirement(name)
        return req.get('trigger_tools', ['Edit', 'Write', 'MultiEdit']) if req else []
```

#### Step 1.6: Implement Requirements Manager (60 min)

Create `~/.claude/hooks/lib/requirements.py`:

```python
#!/usr/bin/env python3
"""Core requirements management."""
import time
from .state_storage import load_state, save_state, delete_state, list_all_states
from .git_utils import get_all_branches

class BranchRequirements:
    """Requirements manager for a branch."""

    def __init__(self, branch: str, session_id: str, project_dir: str):
        self.branch = branch
        self.session_id = session_id
        self.project_dir = project_dir
        self._state = load_state(branch, project_dir)

    def _save(self):
        """Save current state."""
        save_state(self.branch, self.project_dir, self._state)

    def _get_req_state(self, req_name: str) -> dict:
        """Get or create requirement state."""
        if req_name not in self._state['requirements']:
            self._state['requirements'][req_name] = {}
        return self._state['requirements'][req_name]

    def is_satisfied(self, req_name: str, scope: str = 'session') -> bool:
        """Check if requirement satisfied."""
        req_state = self._get_req_state(req_name)

        if scope == 'session':
            sessions = req_state.get('sessions', {})
            if self.session_id not in sessions:
                return False

            session_state = sessions[self.session_id]
            if not session_state.get('satisfied', False):
                return False

            # Check TTL
            expires_at = session_state.get('expires_at')
            if expires_at and time.time() > expires_at:
                return False

            return True

        elif scope == 'branch':
            if not req_state.get('satisfied', False):
                return False

            expires_at = req_state.get('expires_at')
            if expires_at and time.time() > expires_at:
                return False

            return True

        elif scope == 'permanent':
            return req_state.get('satisfied', False)

        return False

    def satisfy(self, req_name: str, scope: str = 'session',
                method: str = 'manual', metadata: dict = None,
                ttl: int = None) -> None:
        """Mark requirement satisfied."""
        req_state = self._get_req_state(req_name)
        req_state['scope'] = scope

        if scope == 'session':
            if 'sessions' not in req_state:
                req_state['sessions'] = {}

            session_state = {
                'satisfied': True,
                'satisfied_at': int(time.time()),
                'satisfied_by': method
            }

            if metadata:
                session_state['metadata'] = metadata

            if ttl is not None:
                session_state['expires_at'] = int(time.time() + ttl)
            else:
                session_state['expires_at'] = None

            req_state['sessions'][self.session_id] = session_state

        else:  # branch or permanent
            req_state['satisfied'] = True
            req_state['satisfied_at'] = int(time.time())
            req_state['satisfied_by'] = method

            if metadata:
                req_state['metadata'] = metadata

            if ttl and scope == 'branch':
                req_state['expires_at'] = int(time.time() + ttl)
            else:
                req_state['expires_at'] = None

        self._save()

    def clear(self, req_name: str) -> None:
        """Clear requirement."""
        if req_name in self._state['requirements']:
            del self._state['requirements'][req_name]
            self._save()

    def clear_all(self) -> None:
        """Clear all requirements."""
        self._state['requirements'] = {}
        self._save()

    def get_status(self) -> dict:
        """Get full status."""
        return {
            'branch': self.branch,
            'session_id': self.session_id,
            'project': self.project_dir,
            'requirements': self._state['requirements']
        }

    @staticmethod
    def cleanup_stale_branches(project_dir: str) -> int:
        """Remove state for deleted branches."""
        count = 0
        existing = set(get_all_branches(project_dir))

        for branch, path in list_all_states(project_dir):
            if branch not in existing:
                delete_state(branch, project_dir)
                count += 1

        return count
```

#### Step 1.7: Implement PreToolUse Hook (60 min)

Create `~/.claude/hooks/check-requirements.py`:

```python
#!/usr/bin/env python3
"""
Requirements Framework - PreToolUse Hook
Checks requirements before Edit/Write/MultiEdit operations.
"""
import json
import sys
import os
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from requirements import BranchRequirements
from config import RequirementsConfig
from git_utils import get_current_branch, is_git_repo
from session import get_session_id

def should_skip_plan_file(file_path: str) -> bool:
    """
    Check if a file path is a plan file that should skip requirements checks.

    Plan files need to be written before requirements can be satisfied,
    so we skip checks for them to avoid chicken-and-egg problems.

    Args:
        file_path: Path to check

    Returns:
        True if this is a plan file that should be skipped
    """
    try:
        # Normalize path (expand ~, resolve symlinks, make absolute)
        normalized = Path(file_path).expanduser().resolve()

        # Skip files in global plans directory (~/.claude/plans/)
        global_plans = Path.home() / '.claude' / 'plans'
        try:
            if normalized.is_relative_to(global_plans):
                return True
        except (ValueError, AttributeError):
            # Python < 3.9 doesn't have is_relative_to, use string matching
            pass

        # Skip files in project .claude/plans/ directories
        # Check if path contains .claude/plans/
        path_str = str(normalized)
        if '/.claude/plans/' in path_str or '\\.claude\\plans\\' in path_str:
            return True

        return False

    except Exception:
        # If anything fails, don't skip (fail safe)
        return False


def main():
    """Hook entry point."""
    try:
        # Read hook input
        input_data = {}
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            pass

        tool_name = input_data.get('tool_name', '')

        # Only check on write operations
        if tool_name not in ['Edit', 'Write', 'MultiEdit']:
            sys.exit(0)

        # Skip plan files - plan mode needs to write plans before requirements can be satisfied
        tool_input = input_data.get('tool_input', {})
        if tool_input:
            file_path = tool_input.get('file_path', '')
            if file_path and should_skip_plan_file(file_path):
                sys.exit(0)

        # Get project directory
        project_dir = os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())

        # Check if project has requirements config
        config_file = Path(project_dir) / '.claude' / 'requirements.yaml'
        if not config_file.exists():
            # No config = no requirements for this project
            sys.exit(0)

        # Skip if not git repo
        if not is_git_repo(project_dir):
            sys.exit(0)

        # Get current branch
        branch = get_current_branch(project_dir)
        if not branch:
            sys.exit(0)  # Detached HEAD

        # Skip main/master
        if branch in ['main', 'master']:
            sys.exit(0)

        # Load configuration
        config = RequirementsConfig(project_dir)

        # Check if enabled for this project
        if not config.is_enabled():
            sys.exit(0)

        # Get session ID
        session_id = get_session_id()

        # Initialize requirements manager
        reqs = BranchRequirements(branch, session_id, project_dir)

        # Check all enabled requirements
        for req_name in config.get_all_requirements():
            if not config.is_requirement_enabled(req_name):
                continue

            req_config = config.get_requirement(req_name)
            scope = config.get_scope(req_name)

            # Check if this tool triggers this requirement
            trigger_tools = config.get_trigger_tools(req_name)
            if tool_name not in trigger_tools:
                continue

            # Check if satisfied
            if not reqs.is_satisfied(req_name, scope):
                # Not satisfied - prompt user
                output_prompt(req_name, req_config)
                sys.exit(0)

        # All requirements satisfied
        sys.exit(0)

    except Exception as e:
        # FAIL OPEN with visible warning
        import traceback
        error_msg = f"Requirements check error: {e}"
        print(f"⚠️ {error_msg}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Log to file for debugging
        try:
            log_file = Path.home() / '.claude' / 'requirements-errors.log'
            with open(log_file, 'a') as f:
                f.write(f"\n{'='*60}\n")
                f.write(f"Error at {time.time()}\n")
                f.write(traceback.format_exc())
        except:
            pass

        sys.exit(0)

def output_prompt(req_name: str, config: dict):
    """Output 'ask' decision for user approval."""
    message = config.get('message', f'Requirement "{req_name}" not satisfied.')

    # Add helper hint
    message += f"\n\n💡 **To satisfy this requirement**: Run `req satisfy {req_name}`"

    response = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": message
        }
    }
    print(json.dumps(response))

if __name__ == '__main__':
    main()
```

#### Step 1.8: Implement CLI Tool (60 min)

Create `~/.claude/hooks/requirements-cli.py`:

```python
#!/usr/bin/env python3
"""
Requirements Framework CLI Tool
"""
import sys
import os
import argparse
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent / 'lib'))

from requirements import BranchRequirements
from config import RequirementsConfig
from git_utils import get_current_branch, get_session_id
from state_storage import list_all_states

def get_project_dir() -> str:
    """Get current project directory."""
    return os.environ.get('CLAUDE_PROJECT_DIR', os.getcwd())

def cmd_status(args):
    """Show status."""
    project_dir = get_project_dir()
    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch", file=sys.stderr)
        return 1

    session_id = get_session_id()
    config = RequirementsConfig(project_dir)
    reqs = BranchRequirements(branch, session_id, project_dir)

    print(f"Branch: {branch}")
    print(f"Session: {session_id}")
    print(f"Project: {project_dir}")
    print()

    if not config.is_enabled():
        print("⚠️ Requirements framework disabled for this project")
        return 0

    all_reqs = config.get_all_requirements()
    if not all_reqs:
        print("No requirements configured for this project.")
        return 0

    print("Requirements:")
    for req_name in all_reqs:
        if not config.is_requirement_enabled(req_name):
            print(f"  ⊘ {req_name} (disabled)")
            continue

        scope = config.get_scope(req_name)
        satisfied = reqs.is_satisfied(req_name, scope)

        icon = "✅" if satisfied else "❌"
        print(f"  {icon} {req_name} ({scope})")

    return 0

def cmd_satisfy(args):
    """Satisfy requirement."""
    project_dir = get_project_dir()
    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch", file=sys.stderr)
        return 1

    session_id = get_session_id()
    config = RequirementsConfig(project_dir)

    req_name = args.requirement
    if req_name not in config.get_all_requirements():
        print(f"❌ Unknown requirement: {req_name}", file=sys.stderr)
        print(f"Available: {', '.join(config.get_all_requirements())}")
        return 1

    scope = config.get_scope(req_name)
    reqs = BranchRequirements(branch, session_id, project_dir)

    metadata = {}
    if args.metadata:
        import json
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print("❌ Invalid JSON metadata", file=sys.stderr)
            return 1

    reqs.satisfy(req_name, scope, method='cli', metadata=metadata)
    print(f"✅ Satisfied '{req_name}' for {branch} ({scope} scope)")
    return 0

def cmd_clear(args):
    """Clear requirement."""
    project_dir = get_project_dir()
    branch = args.branch or get_current_branch(project_dir)

    if not branch:
        print("❌ Not on a branch", file=sys.stderr)
        return 1

    session_id = get_session_id()
    reqs = BranchRequirements(branch, session_id, project_dir)

    if args.all:
        reqs.clear_all()
        print(f"✅ Cleared all requirements for {branch}")
    else:
        reqs.clear(args.requirement)
        print(f"✅ Cleared '{args.requirement}' for {branch}")

    return 0

def cmd_list(args):
    """List tracked branches."""
    project_dir = get_project_dir()
    states = list_all_states(project_dir)

    if not states:
        print("No tracked branches in this project.")
        return 0

    print(f"Tracked branches ({len(states)}):")
    for branch, path in states:
        from state_storage import load_state
        state = load_state(branch, project_dir)
        req_count = len(state.get('requirements', {}))
        print(f"  {branch}: {req_count} requirement(s)")

    return 0

def cmd_prune(args):
    """Cleanup stale state."""
    project_dir = get_project_dir()

    print("Cleaning up stale state...")
    count = BranchRequirements.cleanup_stale_branches(project_dir)
    print(f"✅ Removed {count} state file(s) for deleted branches")

    return 0

def main():
    parser = argparse.ArgumentParser(
        prog='req',
        description='Requirements Framework CLI'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command')

    # status
    status_parser = subparsers.add_parser('status', help='Show status')
    status_parser.add_argument('--branch', '-b')

    # satisfy
    satisfy_parser = subparsers.add_parser('satisfy', help='Satisfy requirement')
    satisfy_parser.add_argument('requirement')
    satisfy_parser.add_argument('--branch', '-b')
    satisfy_parser.add_argument('--metadata', '-m', help='JSON metadata')

    # clear
    clear_parser = subparsers.add_parser('clear', help='Clear requirement')
    clear_parser.add_argument('requirement', nargs='?')
    clear_parser.add_argument('--branch', '-b')
    clear_parser.add_argument('--all', '-a', action='store_true')

    # list
    list_parser = subparsers.add_parser('list', help='List tracked branches')

    # prune
    prune_parser = subparsers.add_parser('prune', help='Clean up stale state')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        'status': cmd_status,
        'satisfy': cmd_satisfy,
        'clear': cmd_clear,
        'list': cmd_list,
        'prune': cmd_prune
    }

    return commands[args.command](args)

if __name__ == '__main__':
    sys.exit(main())
```

Make it executable and create alias:

```bash
chmod +x ~/.claude/hooks/requirements-cli.py

# Add to ~/.bashrc or ~/.zshrc:
alias req='python3 ~/.claude/hooks/requirements-cli.py'
```

#### Step 1.9: Create Configuration Files (30 min)

**Global Config** (`~/.claude/requirements.yaml`):

```yaml
# Global Requirements Framework Configuration
# This is the default config for all projects

version: "1.0"

# Global settings
enabled: true

# Default requirements (projects can override)
requirements:
  commit_plan:
    enabled: false  # Disabled by default, projects opt-in
    type: blocking
    scope: session
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      📋 **No commit plan found for this session**

      Before making code changes, you should plan your commits.

      **Required**: Invoke the `atomic-commits` skill to create a plan

      **Why this matters**:
      - Ensures commits are atomic and reviewable
      - Prevents "fix comments" commits
      - Follows project conventions

      **To proceed**: Run `req satisfy commit_plan` after creating a plan
```

**Project Config** (`/Users/harm/Work/solarmonkey-app/.claude/requirements.yaml`):

```yaml
# Requirements Configuration for solarmonkey-app
version: "1.0"

# Inherit global requirements
inherit: true

# Enable framework for this project
enabled: true

# Project-specific requirements
requirements:
  # Enable commit_plan for this project
  commit_plan:
    enabled: true
    # Inherits message and settings from global config
```

**Add to .gitignore**:

```bash
cd /Users/harm/Work/solarmonkey-app
echo "" >> .gitignore
echo "# Requirements framework state (not committed)" >> .gitignore
echo ".git/requirements/" >> .gitignore
echo ".claude/requirements.local.yaml" >> .gitignore
```

#### Step 1.10: Register Hook (5 min)

Edit `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/check-requirements.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/requirements-cli.py prune 2>&1 | head -1",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

#### Step 1.11: Test MVP (30 min)

```bash
# Test 1: CLI exists
req --help

# Test 2: Check status (should show commit_plan not satisfied)
cd /Users/harm/Work/solarmonkey-app
req status

# Test 3: Satisfy requirement
req satisfy commit_plan

# Test 4: Check status again (should show satisfied)
req status

# Test 5: Clear requirement
req clear commit_plan

# Test 6: Test in Claude session
# Start Claude Code, try to edit a file
# Should see prompt about commit plan
```

---

### Phase 2: Additional Requirements (6-8 hours)

#### Step 2.1: Add GitHub Ticket Requirement

Update `/Users/harm/Work/solarmonkey-app/.claude/requirements.yaml`:

```yaml
requirements:
  commit_plan:
    enabled: true

  github_ticket:
    enabled: true
    type: blocking
    scope: branch
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      🎫 **No GitHub issue linked to this branch**

      Please link a GitHub issue to track this work.

      **To satisfy**: `req satisfy github_ticket --metadata '{"ticket":"#1234"}'`

    auto_satisfy:
      - type: branch_name_pattern
        pattern: '(\d+)-'
        extract: ticket
        prefix: '#'
```

Implement auto-satisfy in hook (Phase 2 enhancement).

#### Step 2.2: Add ADR Review for cclv2

Create `/Users/harm/Work/cclv2/.claude/requirements.yaml`:

```yaml
version: "1.0"
inherit: true
enabled: true

requirements:
  commit_plan:
    enabled: true

  adr_reviewed:
    enabled: true
    type: blocking
    scope: session
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      📚 **Working in cclv2 - Have you reviewed relevant ADRs?**

      ADRs are in: /Users/harm/Work/cclv2/ADR/

      Review relevant ADRs before proceeding.

      **To satisfy**: `req satisfy adr_reviewed` after reviewing
```

---

### Phase 3: Polish & UX (4-6 hours)

- Colored CLI output
- Better error messages
- Auto-satisfy patterns
- Metrics collection (optional)

---

### Phase 4: Advanced Features (Future)

See original plan for:
- Requirement dependencies
- Conditional requirements
- CI/CD integration
- Team approvals

---

## 5. Configuration Reference

### Global Config (~/.claude/requirements.yaml)

```yaml
version: "1.0"

# Framework enabled globally
enabled: true

# Default requirements
requirements:
  # Requirement name
  requirement_name:
    enabled: false        # Enable/disable
    type: blocking        # blocking, warning, info
    scope: session        # session, branch, permanent
    trigger_tools:        # Which tools trigger check
      - Edit
      - Write
      - MultiEdit
    message: |            # Markdown message to user
      Message text
    ttl: 3600            # Optional TTL in seconds
    auto_satisfy:        # Optional auto-satisfy rules
      - type: pattern
        config: value
```

### Project Config (.claude/requirements.yaml)

```yaml
version: "1.0"

# Inherit global requirements (default: true)
inherit: true

# Enable for this project (default: true)
enabled: true

# Project requirements (merged with global if inherit=true)
requirements:
  commit_plan:
    enabled: true    # Override global setting

  project_specific:
    enabled: true
    # ... requirement config
```

### Local Overrides (.claude/requirements.local.yaml)

**Gitignored** - personal overrides

```yaml
version: "1.0"

requirements:
  commit_plan:
    enabled: false  # Disable for local dev
```

---

## 6. Per-Project Setup

### Enable Requirements for a Project

```bash
cd /path/to/project

# Create config
cat > .claude/requirements.yaml <<'EOF'
version: "1.0"
inherit: true
enabled: true

requirements:
  commit_plan:
    enabled: true
EOF

# Update .gitignore
echo ".git/requirements/" >> .gitignore
echo ".claude/requirements.local.yaml" >> .gitignore

# Commit config
git add .claude/requirements.yaml .gitignore
git commit -m "Enable requirements framework"
```

### Disable Requirements for a Project

```bash
cd /path/to/project

# Option 1: Disable in config (preserves config)
cat > .claude/requirements.yaml <<'EOF'
version: "1.0"
enabled: false
EOF

# Option 2: Delete config (completely disables)
rm .claude/requirements.yaml

# Option 3: Local override (your machine only)
cat > .claude/requirements.local.yaml <<'EOF'
version: "1.0"
enabled: false
EOF
```

---

## 7. API Reference

### CLI Commands

```bash
# Show status
req status
req status --branch feature/auth

# Satisfy requirement
req satisfy commit_plan
req satisfy github_ticket --metadata '{"ticket":"#1234"}'

# Clear requirement
req clear commit_plan
req clear --all

# List tracked branches
req list

# Cleanup stale state
req prune
```

### Python API

```python
from lib.requirements import BranchRequirements
from lib.config import RequirementsConfig

# Load config
config = RequirementsConfig('/path/to/project')

# Initialize requirements
reqs = BranchRequirements('feature/auth', 'session-123', '/path/to/project')

# Check satisfaction
if not reqs.is_satisfied('commit_plan', scope='session'):
    print("Not satisfied")

# Satisfy
reqs.satisfy('commit_plan', scope='session', method='cli')

# Clear
reqs.clear('commit_plan')

# Cleanup
BranchRequirements.cleanup_stale_branches('/path/to/project')
```

---

## 8. Edge Cases & Solutions

| Scenario | Behavior | Implementation |
|----------|----------|----------------|
| No config file | Skip requirements | Early exit if config missing |
| Config disabled | Skip requirements | Check `enabled: false` |
| Python version < 3.9 | Fail open with warning | Version check, log error |
| No PyYAML | Use JSON config | Fallback in config loader |
| Corrupted state | Rebuild empty state | Exception handling in load |
| Multiple sessions | Independent tracking | Session ID in state |
| Branch renamed | Treat as new branch | State keyed by branch name |
| Detached HEAD | Skip checks | Early exit |
| Git worktrees | Shared requirements | State in .git/requirements/ |
| Hook timeout | Fail open | 5-second timeout in settings |
| **Plan files** | **Skip requirements** | **Whitelist `~/.claude/plans/` and `.claude/plans/`** |

### Plan File Whitelisting (Critical Feature)

**Problem**: Chicken-and-egg scenario where Claude needs to write plan files to satisfy `commit_plan` requirement, but the hook blocks Write operations.

**Solution**: The `should_skip_plan_file()` function automatically whitelists plan files:

```python
def should_skip_plan_file(file_path: str) -> bool:
    """Check if file is a plan file that should skip requirements."""
    # Whitelisted paths:
    # - ~/.claude/plans/*
    # - {project}/.claude/plans/*
```

**Files that skip requirements:**
- ✅ `~/.claude/plans/my-plan.md` - Global plan directory
- ✅ `/project/.claude/plans/feature.md` - Project plan directory
- ✅ Any path containing `/.claude/plans/`

**Files that still require checks:**
- ❌ ADR files (`/ADR/*.md`)
- ❌ Source code
- ❌ Config files (`.claude/requirements.yaml`)
- ❌ Other `.claude` files

**Why this matters:**
- Allows Claude to enter plan mode and write plans
- Plans can be created BEFORE satisfying `commit_plan`
- Preserves security for all other file operations
- No chicken-and-egg blocking

---

## 9. Testing Strategy

### Unit Tests

```python
# tests/test_requirements.py
def test_session_scope_satisfaction():
    reqs = BranchRequirements('test-branch', 'session-1', '/tmp/test')
    assert not reqs.is_satisfied('test_req', 'session')

    reqs.satisfy('test_req', 'session')
    assert reqs.is_satisfied('test_req', 'session')

    # Different session
    reqs2 = BranchRequirements('test-branch', 'session-2', '/tmp/test')
    assert not reqs2.is_satisfied('test_req', 'session')

def test_branch_scope_persistence():
    reqs1 = BranchRequirements('test', 'session-1', '/tmp')
    reqs1.satisfy('test_req', 'branch')

    # New session, same branch
    reqs2 = BranchRequirements('test', 'session-2', '/tmp')
    assert reqs2.is_satisfied('test_req', 'branch')
```

### Integration Tests

```bash
#!/bin/bash
# test-integration.sh

set -e

echo "Testing requirements framework..."

# Setup
TEST_DIR=$(mktemp -d)
cd $TEST_DIR
git init
git checkout -b test-branch

# Create config
mkdir -p .claude
cat > .claude/requirements.yaml <<'EOF'
version: "1.0"
enabled: true
requirements:
  test_req:
    enabled: true
    scope: session
EOF

# Test CLI
req status | grep "test_req"
req satisfy test_req
req status | grep "✅"

# Cleanup
cd /
rm -rf $TEST_DIR

echo "✅ Integration tests passed"
```

---

## 10. Migration & Rollout

### Migrating from Hookify

```bash
# 1. Disable hookify rule
cd /Users/harm/Work/solarmonkey-app
rm .claude/hookify.require-commit-plan.local.md

# 2. Enable requirements framework
cat > .claude/requirements.yaml <<'EOF'
version: "1.0"
inherit: true
enabled: true

requirements:
  commit_plan:
    enabled: true
EOF

# 3. Test
req status

# 4. Commit
git add .claude/requirements.yaml
git commit -m "Switch from hookify to requirements framework"
```

### Rollout Strategy

**Week 1**: Test on personal branches
**Week 2**: Enable for solarmonkey-app
**Week 3**: Enable for cclv2
**Week 4+**: Team adoption

### Quick Disable

```bash
# Per-project
echo "enabled: false" > .claude/requirements.local.yaml

# Global
export CLAUDE_SKIP_REQUIREMENTS=1

# Or edit settings.json and remove hook
```

---

## 11. User Workflows & Use Cases

This section provides detailed, real-world workflows showing how users interact with the requirements framework in their daily development work.

---

### Use Case 1: First-Time Framework Installation

**Actor**: Developer setting up requirements framework for the first time

**Goal**: Install framework and enable for a project

**Steps**:

```bash
# 1. Create framework directories
mkdir -p ~/.claude/hooks/lib
cd ~/.claude/hooks

# 2. Install framework files (one-time)
# Copy all Python files from implementation plan
# - lib/session.py
# - lib/git_utils.py
# - lib/state_storage.py
# - lib/config.py
# - lib/requirements.py
# - check-requirements.py
# - requirements-cli.py

chmod +x check-requirements.py requirements-cli.py

# 3. Create global config
cat > ~/.claude/requirements.yaml <<'EOF'
version: "1.0"
enabled: true

requirements:
  commit_plan:
    enabled: false  # Disabled by default
    type: blocking
    scope: session
    trigger_tools: [Edit, Write, MultiEdit]
    message: |
      📋 **No commit plan found**

      Create a commit plan using atomic-commits skill.

      To satisfy: `req satisfy commit_plan`
EOF

# 4. Set up shell alias
echo "alias req='python3 ~/.claude/hooks/requirements-cli.py'" >> ~/.zshrc
source ~/.zshrc

# 5. Test installation
req --help
# Should show help message

# 6. Register hook in Claude Code settings
# Edit ~/.claude/settings.json and add PreToolUse hook
```

**Result**: Framework installed and ready to use across all projects

**Time**: 15-30 minutes (one-time setup)

---

### Use Case 2: Daily Developer Workflow - Feature Development

**Actor**: Developer working on a feature with requirements enabled

**Scenario**: Start work on `feature/add-payment-flow` in solarmonkey-app

**Steps**:

```bash
# Morning: Start new feature
cd /Users/harm/Work/solarmonkey-app
git checkout master
git pull
git checkout -b feature/1234-add-payment-flow

# Check requirements status
req status
# Output:
# Branch: feature/1234-add-payment-flow
# Session: abc123
# Project: /Users/harm/Work/solarmonkey-app
#
# Requirements:
#   ❌ commit_plan (session)
#   ✅ github_ticket (branch)  # Auto-extracted from branch name

# Start Claude Code session
claude

# User: "Let's add the payment flow. Edit Payment.tsx"
# Claude: Attempts to edit file
# Hook: Prompts for commit_plan requirement
# User sees:
#   📋 No commit plan found for this session
#   Create a commit plan using atomic-commits skill.
#   💡 To satisfy: `req satisfy commit_plan`

# User: "First, use the atomic-commits skill to plan"
# Claude: Invokes skill, creates plan
# User: "Now mark commit plan as satisfied"

# In terminal:
req satisfy commit_plan
# ✅ Satisfied 'commit_plan' for feature/1234-add-payment-flow (session scope)

# Back in Claude:
# User: "Now edit Payment.tsx"
# Claude: Attempts edit → Hook checks → commit_plan satisfied → Edit allowed

# Continue working...
# All edits now proceed without prompts (requirement satisfied)

# End of day: Leave work
# Tomorrow: New session, requirement needs to be satisfied again
```

**Key Points**:
- Requirement prompts on first edit attempt
- Once satisfied, no more prompts for that session
- GitHub ticket auto-extracted from branch name
- Fresh requirement check each session (forces planning habit)

**Time**: 2-3 minutes overhead per session (planning time)

---

### Use Case 3: Team Member Onboarding

**Actor**: New team member joining project with requirements enabled

**Scenario**: Sarah joins the team, clones solarmonkey-app

**Steps**:

```bash
# Day 1: Clone repo
git clone git@github.com:company/solarmonkey-app.git
cd solarmonkey-app

# Notice .claude/requirements.yaml in repo
cat .claude/requirements.yaml
# version: "1.0"
# enabled: true
# requirements:
#   commit_plan:
#     enabled: true

# Check if framework is installed
req status
# Error: command not found

# Sarah asks team: "What's req?"
# Team: "It's the requirements framework, here's the setup guide"

# Sarah installs framework (Use Case 1)
# ... installs framework in ~/.claude ...

# Now test
req status
# Branch: master
# Session: xyz789
# Project: /Users/sarah/Work/solarmonkey-app
#
# Requirements:
#   ⊘ commit_plan (disabled on master branch)

# Create feature branch
git checkout -b sarah/test-requirements

req status
# Requirements:
#   ❌ commit_plan (session)

# Start Claude, try to edit
# Hook prompts for commit_plan
# Sarah: "Ah, I need to plan my commits first"

# Sarah creates plan, satisfies requirement
req satisfy commit_plan

# Continue working...
```

**Key Points**:
- Config file is committed, Sarah sees requirements immediately
- Framework installation is separate (one-time per developer)
- Requirements are self-documenting (prompts explain what's needed)
- Team consistency without blocking new members

**Time**: 30 minutes onboarding (15 min framework install, 15 min understanding)

---

### Use Case 4: Temporarily Disabling Requirements

**Actor**: Developer needs to quickly fix production bug

**Scenario**: Urgent hotfix needed, no time for planning

**Option A: Local Override (Preserves for future)**

```bash
cd /Users/harm/Work/solarmonkey-app

# Create local override (gitignored)
cat > .claude/requirements.local.yaml <<'EOF'
version: "1.0"
requirements:
  commit_plan:
    enabled: false
EOF

# Test
req status
# Requirements:
#   ⊘ commit_plan (disabled)

# Make hotfix without requirements
# ... edit files ...

# After hotfix deployed, re-enable
rm .claude/requirements.local.yaml

# Or keep disabled permanently for yourself
```

**Option B: Environment Variable (Session-only)**

```bash
# Disable for this terminal session only
export CLAUDE_SKIP_REQUIREMENTS=1

# Start Claude
claude

# All requirements skipped
# ... make hotfix ...

# Close terminal - requirements re-enabled next session
```

**Option C: Disable Specific Requirement**

```bash
# Just disable commit_plan, keep others
cat > .claude/requirements.local.yaml <<'EOF'
version: "1.0"
requirements:
  commit_plan:
    enabled: false
  # github_ticket still enabled
EOF
```

**Key Points**:
- Multiple disable options for different needs
- Local overrides don't affect team
- Environment variable is session-temporary
- Easy to re-enable

**Time**: < 1 minute to disable

---

### Use Case 5: Adding a New Requirement to Project

**Actor**: Tech lead wants to enforce ADR reviews in cclv2 project

**Scenario**: Add ADR review requirement to cclv2

**Steps**:

```bash
# 1. Update project config
cd /Users/harm/Work/cclv2
vim .claude/requirements.yaml

# Add new requirement:
# requirements:
#   adr_reviewed:
#     enabled: true
#     type: blocking
#     scope: session
#     trigger_tools: [Edit, Write, MultiEdit]
#     message: |
#       📚 **Working in cclv2 - Have you reviewed relevant ADRs?**
#
#       ADRs are in: /Users/harm/Work/cclv2/ADR/
#
#       Review relevant ADRs before proceeding.
#
#       To satisfy: `req satisfy adr_reviewed`

# 2. Test locally
git checkout -b test-adr-requirement

req status
# Requirements:
#   ❌ commit_plan (session)
#   ❌ adr_reviewed (session)  # NEW REQUIREMENT

# Start Claude, try to edit
# Hook prompts for both requirements

# Satisfy after reviewing ADRs
req satisfy adr_reviewed

# 3. Commit config change
git add .claude/requirements.yaml
git commit -m "Add ADR review requirement for cclv2"
git push origin test-adr-requirement

# 4. Create PR
gh pr create --title "Add ADR review requirement" --body "
## Summary
- Adds adr_reviewed requirement to cclv2 project
- Ensures developers review ADRs before making changes

## Rationale
We've had several PRs that violated ADR decisions because developers
weren't aware of them. This requirement prompts for review.

## Testing
- [x] Tested locally - prompts correctly
- [x] Can be satisfied with req satisfy adr_reviewed
- [x] Sessions remain satisfied after first review
"

# 5. Team reviews PR
# Team sees the new requirement in config file
# Team approves or suggests changes

# 6. Merge
# All team members get new requirement on next git pull
```

**Key Points**:
- New requirements added via config (code-reviewed)
- Team sees and discusses requirements
- No code changes needed (just config)
- Immediate effect after merge

**Time**: 15 minutes (config + PR + review)

---

### Use Case 6: Multi-Project Workflow

**Actor**: Developer working across multiple projects in one day

**Scenario**: Work on solarmonkey-app (has requirements) and personal-project (no requirements)

**Steps**:

```bash
# Morning: Work on solarmonkey-app
cd /Users/harm/Work/solarmonkey-app
git checkout -b feature/new-dashboard

req status
# Requirements:
#   ❌ commit_plan (session)

# Start Claude, plan work, satisfy requirement
claude
# ... work on dashboard ...

req satisfy commit_plan

# ... continue working ...

# Afternoon: Switch to personal project
cd /Users/harm/personal-project

req status
# No requirements configured for this project.

# Start Claude - no requirements check
claude
# ... make quick changes, no planning needed ...

# No prompts, no requirements - framework skipped

# Evening: Back to solarmonkey-app
cd /Users/harm/Work/solarmonkey-app
git checkout feature/new-dashboard

req status
# Branch: feature/new-dashboard
# Session: xyz789  # NEW SESSION ID
# Requirements:
#   ❌ commit_plan (session)  # NOT SATISFIED (new session)

# Need to satisfy again (new session)
req satisfy commit_plan
```

**Key Points**:
- Framework only active when project has config
- Session scope requires re-satisfaction per session
- No interference with personal projects
- Per-project independence

**Time**: No overhead for projects without requirements

---

### Use Case 7: Debugging When Requirements Aren't Working

**Actor**: Developer experiencing issues with requirements framework

**Scenario**: Requirements not prompting when expected

**Troubleshooting Steps**:

```bash
# 1. Check if framework is installed
req --help
# If "command not found" → Framework not installed

# 2. Check project has config
cd /Users/harm/Work/solarmonkey-app
ls .claude/requirements.yaml
# If "No such file" → No requirements configured

cat .claude/requirements.yaml
# Check if enabled: true

# 3. Check requirement is enabled
req status
# Shows all requirements and their enabled state

# 4. Check hook is registered
cat ~/.claude/settings.json | grep check-requirements
# Should see: "command": "python3 ~/.claude/hooks/check-requirements.py"

# 5. Check for errors
tail -f ~/.claude/requirements-errors.log
# Framework logs errors here

# 6. Test hook manually
cd /Users/harm/Work/solarmonkey-app
echo '{"tool_name":"Edit"}' | python3 ~/.claude/hooks/check-requirements.py
# Should output JSON or error

# 7. Check Python version
python3 --version
# Should be 3.9+

# 8. Check git branch
git branch --show-current
# Requirements skip main/master

# 9. Check session ID
python3 -c "from lib.session import get_session_id; print(get_session_id())"
# Should output session ID

# 10. Enable debug mode
export REQUIREMENTS_DEBUG=1
python3 ~/.claude/hooks/check-requirements.py
# Shows verbose output

# Common Issues:

# Issue: "PyYAML not available" warning
# Solution: Install PyYAML or convert config to JSON
pip install pyyaml
# Or use JSON config instead

# Issue: Hook times out
# Solution: Increase timeout in settings.json
# "timeout": 10  # Increase from 5

# Issue: State file corrupted
# Solution: Delete state file
rm .git/requirements/feature-branch.json

# Issue: Requirements satisfied but still prompting
# Solution: Check session ID consistency
req status  # Note session ID
# Compare with what hook sees

# Issue: Framework completely broken
# Solution: Quick disable
export CLAUDE_SKIP_REQUIREMENTS=1
# Or remove hook from settings.json temporarily
```

**Key Points**:
- Framework has built-in error logging
- Multiple diagnostic commands
- Fail-open design prevents blocking work
- Clear error messages in logs

**Time**: 5-15 minutes troubleshooting

---

### Use Case 8: Upgrading Framework After New Features

**Actor**: Framework maintainer adding auto-satisfy feature

**Scenario**: Upgrade framework to support auto-extracting ticket from branch name

**Steps**:

```bash
# 1. Update framework code in ~/.claude
cd ~/.claude/hooks

# Update lib/requirements.py with new auto-satisfy logic
vim lib/requirements.py
# ... add auto_satisfy_from_branch_name() ...

# Update check-requirements.py to call auto-satisfy
vim check-requirements.py
# ... add try_auto_satisfy() before prompting ...

# 2. Update global config with new feature
vim ~/.claude/requirements.yaml
# Add auto_satisfy section to github_ticket requirement

# 3. Test with existing project
cd /Users/harm/Work/solarmonkey-app
git checkout -b feature/5678-test-auto-extract

req status
# Requirements:
#   ❌ commit_plan (session)
#   ✅ github_ticket (branch)  # AUTO-SATISFIED from "5678"

# Start Claude, try to edit
# Hook: Auto-extracts #5678, satisfies github_ticket
# Hook: Prompts only for commit_plan (not github_ticket)

# 4. Roll out to team
# Update shared documentation
# Team gets new features on next framework update
# No project config changes needed (unless customizing)

# 5. Projects can customize auto-satisfy rules
cd /Users/harm/Work/solarmonkey-app
vim .claude/requirements.yaml

# Add project-specific pattern:
# requirements:
#   github_ticket:
#     auto_satisfy:
#       - type: branch_name_pattern
#         pattern: 'SM-(\d+)'  # JIRA-style tickets
#         extract: ticket
#         prefix: 'SM-'
```

**Key Points**:
- Framework updates don't require project changes
- New features work automatically
- Projects can customize behavior in their config
- Backwards compatible (old configs still work)

**Time**: 1-2 hours for framework update, instant rollout

---

### Use Case 9: Code Review - Reviewing Requirements Changes

**Actor**: Reviewer checking PR that adds/modifies requirements

**Scenario**: PR adds new branch_size requirement

**Review Checklist**:

```yaml
# PR changes .claude/requirements.yaml:
# +  branch_size:
# +    enabled: true
# +    type: blocking
# +    scope: session
# +    message: |
# +      Branch has 400+ changes - consider splitting

# Reviewer checks:

# 1. Is message clear and actionable?
✓ Yes - explains what's wrong and what to do

# 2. Is scope appropriate?
✓ Yes - session scope means per-session check
  (Could be branch scope if warning should persist)

# 3. Is type appropriate?
⚠️  blocking might be too strict - suggest "warning"
  Comment: "Should this be blocking? Seems harsh for first offense"

# 4. Are trigger_tools correct?
✓ Yes - Edit/Write/MultiEdit are appropriate

# 5. Does this affect all branches?
✓ Yes - check if should skip certain branches
  Comment: "Should we skip release branches?"

# 6. Can developers bypass if needed?
✓ Yes - local override always available

# 7. Is this documented?
❌ No - request docs update
  Comment: "Please update team wiki with this new requirement"

# Reviewer feedback:
"Overall good addition, but:
1. Change type: blocking → warning
2. Add exception for release/* branches
3. Update team documentation
4. Add example to PR description showing the prompt"

# Author updates:
# type: warning  # Changed
# branches:      # Added
#   skip: ["release/*", "hotfix/*"]
```

**Key Points**:
- Config changes are code-reviewed like any code
- Team discusses impact and wording
- Requirements are visible and transparent
- Easy to iterate and improve

**Time**: 10-15 minutes review, 5 minutes updates

---

### Use Case 10: Emergency Override During Incident

**Actor**: On-call engineer during production incident

**Scenario**: Critical bug needs immediate fix, requirements blocking

**Steps**:

```bash
# 2:30 AM: Pager goes off
# Critical bug in production

# 1. Quick disable (fastest)
export CLAUDE_SKIP_REQUIREMENTS=1

# Start Claude
claude

# User: "Critical bug - payment processing is down"
# Claude: Immediately starts editing (no requirement prompts)
# ... makes fix ...
# ... tests fix ...
# ... deploys ...

# 3:45 AM: Incident resolved

# 2. Document override in incident report
cat >> incident-report.md <<'EOF'
## Actions Taken
- Disabled requirements framework for emergency fix
- Used CLAUDE_SKIP_REQUIREMENTS=1
- Fixed bug in Payment.tsx lines 234-256
- Deployed hotfix to production

## Post-Incident
- [ ] Create proper commit plan retroactively
- [ ] Document fix in ADR
- [ ] Re-enable requirements for future work
EOF

# 3. Clean up next day (when alert)
unset CLAUDE_SKIP_REQUIREMENTS

# Create proper branch with planning
git checkout -b hotfix/payment-bug-proper-docs
git cherry-pick <hotfix-commit>

# Now satisfy requirements properly
req satisfy commit_plan
# ... document properly ...
# ... create PR with full context ...
```

**Key Points**:
- Emergency override is quick and documented
- Framework doesn't block critical work
- Can retroactively satisfy requirements
- Incident response remains fast

**Time**: 0 seconds overhead during incident

---

## Summary of Workflows

| Use Case | Time Impact | Frequency | Value |
|----------|-------------|-----------|-------|
| First-time setup | 30 min | Once per developer | High |
| Daily workflow | 2-3 min/session | Daily | High |
| Team onboarding | 30 min | Once per new member | High |
| Temporary disable | <1 min | Rare | Medium |
| Add requirement | 15 min | Monthly | High |
| Multi-project work | 0 min | Daily | High |
| Debugging | 5-15 min | Rare | Medium |
| Framework upgrade | 1-2 hours | Quarterly | High |
| Code review | 10-15 min | Per requirement PR | High |
| Emergency override | 0 sec | Very rare | Critical |

**Total overhead for typical developer**: 2-3 minutes per work session

**Total value**:
- Enforces best practices (atomic commits, planning)
- Self-documenting (prompts explain requirements)
- Team consistency without meetings
- Flexible (easy to override when needed)
- Transparent (all config visible in git)

---

## 12. Shell Alias Setup

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# Requirements Framework CLI
alias req='python3 ~/.claude/hooks/requirements-cli.py'

# Quick status
alias reqs='req status'

# Quick satisfy
alias reqok='req satisfy'
```

Reload shell:
```bash
source ~/.zshrc  # or ~/.bashrc
```

Usage:
```bash
reqs                    # Show status
req satisfy commit_plan # Satisfy requirement
reqok commit_plan       # Shorthand
```

---

## 13. Quick Start Checklist

**Framework Installation** (one-time):
- [ ] Create `~/.claude/hooks/lib/` directory
- [ ] Implement all library files in `lib/`
- [ ] Create `check-requirements.py` hook
- [ ] Create `requirements-cli.py` CLI tool
- [ ] Create global `~/.claude/requirements.yaml`
- [ ] Add hook to `~/.claude/settings.json`
- [ ] Set up shell alias (`req`)
- [ ] Test CLI: `req --help`

**Per-Project Setup**:
- [ ] Create `.claude/requirements.yaml` in project
- [ ] Add `.git/requirements/` to `.gitignore`
- [ ] Add `.claude/requirements.local.yaml` to `.gitignore`
- [ ] Test: `req status`
- [ ] Commit config files
- [ ] Document for team

**Testing**:
- [ ] Test satisfy/clear commands
- [ ] Test in Claude Code session
- [ ] Test multiple sessions
- [ ] Test cleanup/prune

---

## 14. Architecture Benefits

### ✅ Clean Separation
- Framework code in `~/.claude` (not in repos)
- Projects only have config files (versioned)
- State is local (never committed)

### ✅ Team-Friendly
- Config files are code-reviewed
- Team sees what requirements apply
- Easy to disable per-developer

### ✅ Maintainable
- Update framework once (affects all projects)
- No code duplication
- Clear upgrade path

### ✅ Flexible
- Global defaults with project overrides
- Per-developer local overrides
- Easy to opt-in/opt-out

---

**End of Implementation Plan v2.0**

This plan provides a complete, standalone requirements framework with zero hookify dependencies and clean project integration.
