# Skill Authoring Best Practices

> Practical authoring decisions to help you write Skills that Claude can discover and use effectively.

Good Skills are concise, well-structured, and tested with real usage. This reference consolidates official best practices from Anthropic's documentation with requirements-framework-specific conventions.

## Core Principles

### Concise is Key

The context window is a public good. Your Skill shares the context window with everything else Claude needs to know, including:

* The system prompt
* Conversation history
* Other Skills' metadata
* Your actual request

At startup, only the metadata (name and description) from all Skills is pre-loaded. Claude reads SKILL.md only when the Skill becomes relevant, and reads additional files only as needed. However, being concise in SKILL.md still matters: once Claude loads it, every token competes with conversation history and other context.

**Default assumption**: Claude is already very smart.

Only add context Claude doesn't already have. Challenge each piece of information:

* "Does Claude really need this explanation?"
* "Can I assume Claude knows this?"
* "Does this paragraph justify its token cost?"

**Good example: Concise** (~50 tokens):

```markdown
## Extract PDF text

Use pdfplumber for text extraction:

```python
import pdfplumber

with pdfplumber.open("file.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

**Bad example: Too verbose** (~150 tokens):

```markdown
## Extract PDF text

PDF (Portable Document Format) files are a common file format that contains
text, images, and other content. To extract text from a PDF, you'll need to
use a library. There are many libraries available for PDF processing, but we
recommend pdfplumber because it's easy to use and handles most cases well.
First, you'll need to install it using pip. Then you can use the code below...
```

The concise version assumes Claude knows what PDFs are and how libraries work.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability.

**High freedom** (text-based instructions):

Use when:
* Multiple approaches are valid
* Decisions depend on context
* Heuristics guide the approach

**Medium freedom** (pseudocode or scripts with parameters):

Use when:
* A preferred pattern exists
* Some variation is acceptable
* Configuration affects behavior

**Low freedom** (specific scripts, few or no parameters):

Use when:
* Operations are fragile and error-prone
* Consistency is critical
* A specific sequence must be followed

**Analogy**: Think of Claude as a robot exploring a path:
* **Narrow bridge with cliffs**: Only one safe way forward. Exact instructions (low freedom).
* **Open field**: Many paths lead to success. General direction (high freedom).

### Test With All Models You Plan to Use

Skills act as additions to models, so effectiveness depends on the underlying model.

**Testing considerations by model**:

* **Claude Haiku** (fast, economical): Does the Skill provide enough guidance?
* **Claude Sonnet** (balanced): Is the Skill clear and efficient?
* **Claude Opus** (powerful reasoning): Does the Skill avoid over-explaining?

What works perfectly for Opus might need more detail for Haiku.

## Skill Structure

### Requirements Framework Conventions

Our framework extends the standard skill structure with:

```yaml
---
name: Skill-Name-With-Hyphens       # Letters, numbers, hyphens only
description: Use when [triggers]      # Third person, max 1024 chars
git_hash: uncommitted                 # Version tracking (updated by script)
---
```

**Directory layout:**
```
skills/
  skill-name/
    SKILL.md                          # Main reference (required, <500 lines)
    references/                       # Supporting files subdirectory
      supporting-file.md              # Only if needed
```

Key differences from flat structure:
- Supporting files go in `references/` subdirectory (not flat alongside SKILL.md)
- `git_hash` field enables version tracking and A/B testing
- Skills that satisfy requirements include a "Requirements Integration" section

### Naming Conventions

Use **gerund form** (verb + -ing) for Skill names:

* GOOD: "writing-skills", "systematic-debugging", "dispatching-parallel-agents"
* ACCEPTABLE: "test-driven-development" (noun phrase)
* AVOID: "Helper", "Utils", "Tools" (vague)

### Writing Effective Descriptions

The `description` field enables Skill discovery. Include both what the Skill does and when to use it.

**Always write in third person.** The description is injected into the system prompt.

* **Good:** "Use when creating new skills, editing existing skills, or verifying skills work before deployment"
* **Avoid:** "I can help you create skills"
* **Avoid:** "You can use this to create skills"

### Progressive Disclosure Patterns

SKILL.md serves as an overview that points Claude to detailed materials as needed.

**Practical guidance:**
* Keep SKILL.md body under 500 lines for optimal performance
* Split content into separate files when approaching this limit
* Use the patterns below to organize instructions, code, and resources

#### Pattern 1: High-level guide with references

```markdown
# PDF Processing

## Quick start
[Inline code example]

## Advanced features
**Form filling**: See [references/forms.md](references/forms.md) for complete guide
**API reference**: See [references/api.md](references/api.md) for all methods
```

Claude loads reference files only when needed.

#### Pattern 2: Domain-specific organization

For Skills with multiple domains, organize content by domain:

```
bigquery-skill/
  SKILL.md (overview and navigation)
  references/
    finance.md (revenue, billing metrics)
    sales.md (opportunities, pipeline)
    product.md (API usage, features)
```

#### Pattern 3: Conditional details

Show basic content, link to advanced content:

```markdown
## Creating documents
Use docx-js for new documents. See [references/docx-js.md](references/docx-js.md).

## Editing documents
For simple edits, modify XML directly.
**For tracked changes**: See [references/redlining.md](references/redlining.md)
```

### Avoid Deeply Nested References

Claude may partially read files when they're referenced from other referenced files. **Keep references one level deep from SKILL.md.**

## Workflows and Feedback Loops

### Use Workflows for Complex Tasks

Break complex operations into clear, sequential steps. For particularly complex workflows, provide a checklist:

```markdown
## Research synthesis workflow

Copy this checklist and track your progress:

- [ ] Step 1: Read all source documents
- [ ] Step 2: Identify key themes
- [ ] Step 3: Cross-reference claims
- [ ] Step 4: Create structured summary
- [ ] Step 5: Verify citations
```

### Implement Feedback Loops

**Common pattern**: Run validator -> fix errors -> repeat

```markdown
## Document editing process

1. Make your edits
2. **Validate immediately**: `python scripts/validate.py`
3. If validation fails: fix issues, run validation again
4. **Only proceed when validation passes**
```

The validation loop catches errors early.

## Content Guidelines

### Avoid Time-Sensitive Information

Don't include information that will become outdated. Use "old patterns" sections:

```markdown
## Current method
Use the v2 API endpoint: `api.example.com/v2/messages`

## Old patterns
<details>
<summary>Legacy v1 API (deprecated)</summary>
The v1 API used: `api.example.com/v1/messages`
</details>
```

### Use Consistent Terminology

Choose one term and use it throughout the Skill:

* **Good:** Always "API endpoint", always "field", always "extract"
* **Bad:** Mix "API endpoint"/"URL"/"API route"/"path"

## Common Patterns

### Template Pattern

Provide templates for output format. Match strictness to your needs.

**For strict requirements** (like API responses):
```markdown
ALWAYS use this exact template structure:
[exact template]
```

**For flexible guidance** (when adaptation is useful):
```markdown
Here is a sensible default format, but use your best judgment:
[flexible template]
```

### Examples Pattern

For Skills where output quality depends on seeing examples, provide input/output pairs:

```markdown
## Commit message format

**Example 1:**
Input: Added user authentication with JWT tokens
Output: `feat(auth): implement JWT-based authentication`
```

### Conditional Workflow Pattern

Guide Claude through decision points:

```markdown
1. Determine the modification type:
   **Creating new content?** -> Follow "Creation workflow" below
   **Editing existing content?** -> Follow "Editing workflow" below
```

## Evaluation and Iteration

### Build Evaluations First

**Create evaluations BEFORE writing extensive documentation.** This ensures your Skill solves real problems rather than documenting imagined ones.

**Evaluation-driven development:**

1. **Identify gaps**: Run Claude on representative tasks without a Skill
2. **Create evaluations**: Build three scenarios that test these gaps
3. **Establish baseline**: Measure Claude's performance without the Skill
4. **Write minimal instructions**: Create just enough content to address the gaps
5. **Iterate**: Execute evaluations, compare against baseline, and refine

### Develop Skills Iteratively with Claude

Work with one instance of Claude ("Claude A") to create a Skill that will be used by other instances ("Claude B"):

1. **Complete a task without a Skill**: Notice what information you repeatedly provide
2. **Identify the reusable pattern**: What context would be useful for similar future tasks?
3. **Ask Claude A to create a Skill**: It understands the format natively
4. **Review for conciseness**: Remove unnecessary explanations
5. **Improve information architecture**: Organize content effectively
6. **Test on similar tasks**: Use the Skill with Claude B (a fresh instance)
7. **Iterate based on observation**: If Claude B struggles, refine with Claude A

### Observe How Claude Navigates Skills

Watch for:
* **Unexpected exploration paths**: Structure might not be intuitive
* **Missed connections**: Links might need to be more explicit
* **Overreliance on certain sections**: Consider promoting that content
* **Ignored content**: Might be unnecessary or poorly signaled

## Anti-Patterns to Avoid

* **Windows-style paths**: Always use forward slashes (`reference/guide.md`)
* **Too many options**: Provide a default, with escape hatch for alternatives
* **Deeply nested references**: Keep one level deep from SKILL.md
* **Magic numbers**: Justify all configuration values
* **Punting to Claude**: Handle errors explicitly in scripts

## Requirements Framework Integration Checklist

When creating skills for this framework, also consider:

- [ ] Add `satisfied_by_skill` mapping to `hooks/auto-satisfy-skills.py` (if skill satisfies a requirement)
- [ ] Create message YAML in `~/.claude/messages/` (if new requirement type)
- [ ] Add requirement definition to `examples/global-requirements.yaml`
- [ ] Document auto-satisfy behavior in skill's "Requirements Integration" section
- [ ] Run `./update-plugin-versions.sh` to set `git_hash`
- [ ] Run `./sync.sh deploy` to deploy to runtime location

## Checklist for Effective Skills

Before sharing a Skill, verify:

### Core quality
* [ ] Description is specific and includes key terms
* [ ] Description includes both what the Skill does and when to use it
* [ ] SKILL.md body is under 500 lines
* [ ] Additional details are in separate `references/` files (if needed)
* [ ] No time-sensitive information
* [ ] Consistent terminology throughout
* [ ] Examples are concrete, not abstract
* [ ] File references are one level deep
* [ ] Progressive disclosure used appropriately
* [ ] Workflows have clear steps

### Code and scripts
* [ ] Scripts solve problems rather than punt to Claude
* [ ] Error handling is explicit and helpful
* [ ] No "voodoo constants" (all values justified)
* [ ] Required packages listed in instructions
* [ ] No Windows-style paths (all forward slashes)
* [ ] Validation/verification steps for critical operations

### Testing
* [ ] At least three evaluations created
* [ ] Tested with real usage scenarios
* [ ] Team feedback incorporated (if applicable)
