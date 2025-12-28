---
repo_owner: HarmAalbers
repo_name: claude-requirements-framework
project_number: 2
project_url: https://github.com/users/HarmAalbers/projects/2
custom_fields:
  priority:
    name: Priority
    field_id: PVTSSF_lAHOAnYO9M4BLeovzg7ClOY
    options:
      high:
        id: "13cda666"
        name: "🔴 High"
      medium:
        id: "03ec3ca1"
        name: "🟡 Medium"
      low:
        id: "dd43ae1c"
        name: "🟢 Low"
  type:
    name: Type
    field_id: PVTSSF_lAHOAnYO9M4BLeovzg7CmYg
    options:
      feature:
        id: "d752d1a7"
        name: "✨ Feature"
      bug:
        id: "cf698683"
        name: "🐛 Bug"
      documentation:
        id: "e2862951"
        name: "📚 Documentation"
      infrastructure:
        id: "2a8c318e"
        name: "🏗️ Infrastructure"
      testing:
        id: "97f4e30a"
        name: "🧪 Testing"
  status:
    name: Status
    field_id: PVTSSF_lAHOAnYO9M4BLeovzg7CkI8
    options:
      todo:
        id: "f75ad846"
        name: "Todo"
      in_progress:
        id: "47fc9ee4"
        name: "In Progress"
      in_review:
        id: "728eea1f"
        name: "In Review"
      done:
        id: "98236657"
        name: "Done"
---

# GitHub Issues Plugin Configuration

This file contains the default GitHub configuration for the **claude-requirements-framework** project.

## Purpose

The GitHub Issues plugin reads configuration from this file to:
- Create issues in the correct repository
- Add issues to the correct GitHub Project
- Set custom field values (Priority, Type, Status)

## Configuration Values

- **Repository**: `HarmAalbers/claude-requirements-framework`
- **Project**: #2 (https://github.com/users/HarmAalbers/projects/2)
- **Custom Fields**: Priority, Type, Status with their respective field IDs and option IDs

## Overriding Defaults

To override these settings for your local environment:
1. Create `.claude/github-issues.local.md` (gitignored)
2. Copy the YAML frontmatter structure from this file
3. Modify only the values you want to override

Example `.claude/github-issues.local.md`:
```markdown
---
# Test against a different project
project_number: 3
---

# Local Configuration Override
```

## Custom Field IDs

The field IDs and option IDs in this file are project-specific. To discover field IDs for your project:

### Step 1: List all fields
```bash
gh project field-list YOUR_PROJECT_NUMBER --owner YOUR_OWNER --format json
```

### Step 2: Extract specific field IDs
```bash
# Get Priority field ID and options
gh project field-list 2 --owner HarmAalbers --format json | \
  jq '.fields[] | select(.name=="Priority") | {field_id: .id, options: .options}'

# Get Type field ID and options
gh project field-list 2 --owner HarmAalbers --format json | \
  jq '.fields[] | select(.name=="Type") | {field_id: .id, options: .options}'

# Get Status field ID and options
gh project field-list 2 --owner HarmAalbers --format json | \
  jq '.fields[] | select(.name=="Status") | {field_id: .id, options: .options}'
```

### Step 3: Copy IDs to configuration
Copy the `field_id` and option `id` values into this file's YAML frontmatter.
