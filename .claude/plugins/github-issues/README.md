# GitHub Issues Management Plugin

Comprehensive GitHub issues management with deep GitHub Projects v2 integration.

## Overview

This plugin provides an autonomous agent that handles the complete lifecycle of GitHub issues, from creation to closure, with seamless integration into GitHub Projects v2. It leverages findings from recent sessions about GitHub CLI capabilities, custom fields, and automation patterns.

**Key Features**:
- ✨ **Globally installable** - Use across all your projects
- 🔧 **Per-project configuration** - Customize for each repository
- 🔄 **Configuration cascade** - Team defaults with personal overrides
- 📦 **No hard-coded values** - All settings in configuration files

## Features

### 🎯 Core Capabilities

- **Issue Creation**: Create well-structured issues with titles, descriptions, labels, and automatic project board integration
- **Issue Updates**: Modify titles, descriptions, labels, status, and custom fields
- **Issue Retrieval**: List and filter issues by state, labels, custom fields, or search terms
- **Project Integration**: Automatic addition to Project #2 with custom field configuration
- **Batch Operations**: Handle multiple related issues efficiently

### 🏗️ Projects v2 Integration

The agent integrates with **Project #2** (https://github.com/users/HarmAalbers/projects/2) and manages these custom fields:

#### Priority Field
- 🔴 **High** - Critical issues, blockers, security concerns
- 🟡 **Medium** - Important features, moderate bugs (default)
- 🟢 **Low** - Nice-to-haves, minor improvements

#### Type Field
- ✨ **Feature** - New functionality or enhancements
- 🐛 **Bug** - Defects, errors, unexpected behavior
- 📚 **Documentation** - Docs updates, README improvements
- 🏗️ **Infrastructure** - Build, deploy, tooling changes
- 🧪 **Testing** - Test additions, test improvements

#### Status Field
- **Todo** - New issues, backlog items
- **In Progress** - Actively being worked on
- **In Review** - PR created, awaiting review
- **Done** - Completed, merged, closed

## Usage

### Triggering the Agent

The agent triggers automatically when you:

- Ask to create an issue: *"Create an issue for the authentication bug"*
- Want to update an issue: *"Mark issue #15 as done"*
- Need to list issues: *"Show me all open bug issues"*
- Manage project fields: *"Set priority to high for issue #27"*
- Perform batch operations: *"Create issues for the worktree feature"*

### Examples

#### Create a Feature Issue

```
You: "Create an issue for adding git worktree support to the requirements framework"

Agent will:
1. Create issue with title "[Feature] Add git worktree support to requirements framework"
2. Add labels: enhancement
3. Add to Project #2
4. Set Type to ✨ Feature
5. Set Priority to 🟡 Medium (default)
6. Set Status to Todo
7. Return issue URL and summary
```

#### Create a Bug Issue with High Priority

```
You: "Create a high priority bug issue for the TOCTOU race condition in commondir check"

Agent will:
1. Create issue with title "[Bug] Potential TOCTOU race condition in commondir check"
2. Add labels: bug
3. Add to Project #2
4. Set Type to 🐛 Bug
5. Set Priority to 🔴 High
6. Return issue URL and summary
```

#### Update Issue Status

```
You: "Move issue #28 to In Progress"

Agent will:
1. Find the project item for issue #28
2. Update Status field to "In Progress"
3. Confirm update
```

#### List and Filter Issues

```
You: "Show me all open issues with high priority"

Agent will:
1. List all open issues from the repository
2. Cross-reference with project data
3. Filter by Priority: 🔴 High
4. Display formatted table with metadata
```

#### Batch Issue Creation

```
You: "Create issues for the worktree feature: one for git_utils, one for state_storage, and one for documentation"

Agent will:
1. Create three related issues
2. Set consistent Priority and Type
3. Add all to Project #2
4. Return summary with all issue URLs
```

## Installation

### Global Installation (Recommended)

Install the plugin globally to use it across all your projects:

```bash
# When available in a marketplace
claude plugin install github-issues@your-marketplace

# Or install from a local directory
claude plugin install /path/to/github-issues-plugin
```

### Per-Project Installation

Install for a specific project only:

```bash
cd your-project
claude plugin install github-issues@your-marketplace --scope project
```

## Configuration

The plugin uses a **configuration cascade** pattern for flexible, per-project customization:

### Configuration Files

1. **`.claude/github-issues.md`** (Team defaults, checked into git)
   - Shared configuration for all team members
   - Contains repository, project, and custom field settings
   - Version controlled with your project

2. **`.claude/github-issues.local.md`** (Personal overrides, gitignored)
   - Your personal configuration overrides
   - Takes precedence over team defaults
   - Never committed to version control

### Setting Up Configuration

**For the claude-requirements-framework project**, configuration is already included:
- `.claude/github-issues.md` - Contains project defaults
- `.claude/github-issues.local.md` - Template for personal overrides

**For other projects**, create `.claude/github-issues.md`:

```markdown
---
repo_owner: your-org
repo_name: your-repo
project_number: 2
project_url: https://github.com/users/your-org/projects/2
custom_fields:
  priority:
    name: Priority
    field_id: PVTSSF_xxxxxxxxxxxxxxxxxxxxx
    options:
      high:
        id: "abcd1234"
        name: "🔴 High"
      medium:
        id: "efgh5678"
        name: "🟡 Medium"
      low:
        id: "ijkl9012"
        name: "🟢 Low"
  type:
    name: Type
    field_id: PVTSSF_yyyyyyyyyyyyyyyyyyyyy
    options:
      feature:
        id: "mnop3456"
        name: "✨ Feature"
      bug:
        id: "qrst7890"
        name: "🐛 Bug"
  status:
    name: Status
    field_id: PVTSSF_zzzzzzzzzzzzzzzzzzzzz
    options:
      todo:
        id: "uvwx1234"
        name: "Todo"
      in_progress:
        id: "yzab5678"
        name: "In Progress"
---

# GitHub Issues Configuration

Default settings for this project.
```

### Discovering Custom Field IDs

To find your project's custom field IDs:

```bash
# List all fields in your project
gh project field-list YOUR_PROJECT_NUMBER --owner YOUR_OWNER --format json

# Example output shows field_id and option IDs
```

### Overriding Configuration Locally

Create `.claude/github-issues.local.md` to override settings:

```markdown
---
# Test against a different project
project_number: 3
---

# Local Testing Configuration
```

**Add to `.gitignore`**:
```bash
.claude/*.local.md
.claude/settings.local.json
```

## Technical Details

### GitHub CLI Commands Used

The agent uses these `gh` CLI commands:

- `gh issue create` - Create new issues
- `gh issue edit` - Update existing issues
- `gh issue list` - List and filter issues
- `gh issue view` - View issue details
- `gh issue close` - Close issues
- `gh project item-add` - Add issues to project
- `gh project item-list` - List project items
- `gh project item-edit` - Update project custom fields
- `gh project field-list` - Verify field configuration

### Workflow

1. **Issue Creation Flow**:
   ```
   Create issue → Capture URL → Add to project → Set Priority → Set Type → Confirm
   ```

2. **Issue Update Flow**:
   ```
   Identify issue → Get project item ID → Update fields → Confirm
   ```

3. **Issue Listing Flow**:
   ```
   Query issues → Cross-reference project data → Filter → Format → Display
   ```

### Error Handling

The agent handles these edge cases:

- ✅ Issue already in project (checks before adding)
- ✅ Project item not found (graceful fallback)
- ✅ Custom field validation (verifies field IDs)
- ✅ Rate limiting (adds delays for batch operations)
- ✅ Closed issues (can still update project fields)
- ✅ Missing labels (creates if needed)

## Integration with Recent Sessions

This plugin leverages insights from recent development sessions:

1. **GitHub CLI Discovery**: `gh project field-create` for custom fields
2. **Projects v2 API Research**: Understanding GraphQL limitations (no view creation API)
3. **Custom Field Configuration**: Real field IDs from Project #2 setup
4. **Repository Patterns**: Existing label conventions and issue prefixes
5. **Automation Findings**: Auto-add workflows and field automation

## Agent Details

- **Name**: `issue-manager`
- **Color**: Cyan (analysis/review color scheme)
- **Model**: Inherits from parent (Sonnet 4.5)
- **Tools**: Bash, Read, Write, Grep, Glob
- **Autonomy Level**: High - completes operations without step-by-step confirmation

## Common Patterns

### Feature with Sub-issues

Create a parent issue for the overall feature, then create child issues for specific tasks:

```
You: "Create a feature issue for git worktree support with sub-issues for git_utils changes, state_storage updates, and documentation"

Agent creates:
- Parent: [Feature] Add git worktree support
- Child 1: [Worktree] Add get_git_common_dir() to git_utils.py
- Child 2: [Worktree] Update state_storage.py to use common git dir
- Child 3: [Worktree] Add documentation for worktree support
```

### Status Progression

Issues typically flow through statuses:

```
Todo → In Progress → In Review → Done
```

The agent can move issues through this workflow on request.

## Limitations

- **Board View Creation**: Cannot create new project views via CLI (requires GitHub UI)
- **Workflow Automation**: Cannot configure project workflows via CLI (requires GitHub UI)
- **Label Management**: Can add labels but creating new repository labels requires explicit action
- **Assignee Management**: Focuses on issue content and project fields, not assignee workflows

## Future Enhancements

Potential additions for future versions:

- Issue template generation from common patterns
- Automated issue linkage (related issues, dependencies)
- Milestone management integration
- Issue metrics and reporting
- Custom field value suggestions based on issue content
- Integration with pull request creation workflows

## Support

This plugin is designed for the claude-requirements-framework project. For issues or enhancements to the plugin itself, create an issue using the agent:

```
You: "Create an issue for improving the issue-manager agent"
```

## Version History

- **v1.0.0** (2025-12-28) - Initial release with comprehensive GitHub issues management and Projects v2 integration
