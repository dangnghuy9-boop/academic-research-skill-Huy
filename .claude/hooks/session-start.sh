#!/bin/bash
# SessionStart hook: restore the academic-research-skills plugin.
#
# .claude/settings.json declares the marketplace and enables the plugin, but the
# marketplace trust record and the plugin cache both live under $HOME. Claude
# Code on the web starts every container from a clean $HOME, so enabledPlugins
# ends up pointing at a plugin that was never fetched and none of its skills,
# agents or commands load. Re-running the two install steps here restores it.
set -euo pipefail

# Local checkouts keep ~/.claude between runs, so there is nothing to restore.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

MARKETPLACE_REPO="Imbad0202/academic-research-skills"
PLUGIN="academic-research-skills@academic-research-skills"

if ! command -v claude >/dev/null 2>&1; then
  echo "session-start: claude CLI not on PATH, skipping plugin install" >&2
  exit 0
fi

# --scope project resolves against the working directory.
cd "${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Both commands are idempotent and exit 0 when the work is already done. Their
# output goes to stderr so it lands in the hook log rather than the session
# context. A network failure must not stop the session from starting, so warn
# and carry on instead of exiting non-zero.
if ! claude plugin marketplace add "$MARKETPLACE_REPO" >&2; then
  echo "session-start: could not add marketplace $MARKETPLACE_REPO" >&2
  exit 0
fi

if ! claude plugin install "$PLUGIN" --scope project -y >&2; then
  echo "session-start: could not install $PLUGIN" >&2
  exit 0
fi

exit 0
