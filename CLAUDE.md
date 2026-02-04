# OpenClaw Workspace — Project Instructions

## Git Auto-Commit Rule

**CRITICAL: Always auto-commit and push changes immediately after completing any task.**

When you modify, create, or delete files in this workspace:

1. Check for uncommitted changes with `git status`
2. Stage all changes with `git add -A`
3. Commit with a descriptive message
4. Push immediately to remote

### Standard Commit Flow

```bash
cd /home/somnath/.openclaw/workspace
git add -A
git commit -m "Brief description of changes

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push
```

### When to Auto-Commit

- After adding/modifying code files
- After creating new documentation
- After running scripts that generate files
- Before ending the conversation
- **Proactively check `git status` every few minutes**

## Repository Info

- **Remote**: `https://github.com/somnath-habbit/openclaw-projects-and-settings.git`
- **Branch**: `master`
- **Location**: `/home/somnath/.openclaw/workspace/`

## Subprojects

- `Auto_job_application/` - LinkedIn job automation (see its CLAUDE.md)
- `memory/` - Session notes
- `voice-tools/` - Voice input utilities
