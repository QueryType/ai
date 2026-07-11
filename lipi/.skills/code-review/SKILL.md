---
name: code-review
description: |
  Review code changes for bugs, security issues, and style.
  Use when asked to review a PR, diff, or code changes.
metadata:
  author: lipi
  version: "1.0"
---

## Instructions

1. Run `git diff` (or `git diff --staged` if changes are staged) to see the changes.
2. For each changed file, review for:
   - **Bugs**: logic errors, off-by-one, null/None handling, race conditions
   - **Security**: injection, path traversal, hardcoded secrets, unsafe deserialization
   - **Style**: naming, dead code, overly complex logic, missing error handling
3. Report findings grouped by file, with line numbers and severity (critical/warning/nit).
4. If no issues found, say so briefly.
