#!/usr/bin/env bash
#
# Fails if the commit history carries AI attribution: a tool named as an author,
# a co-author trailer pointing at an assistant, or a "generated with" line.
#
# The check matches the SHAPE of an attribution, never a bare vendor word. An
# earlier version grepped the whole commit body for "anthropic" and failed the
# build on a commit that merely described a documentation fix -- the words a
# project is allowed to write about are not the same as the words a machine
# stamps on its own work. Run locally with `make check-attribution`.
set -uo pipefail

# Assistants that stamp their own name on a commit.
tools='claude|anthropic|copilot|chatgpt|openai|gemini|cursor|codex|devin|windsurf|aider'

fail=0
report() {
  fail=1
  echo "::error::$1"
}

# 1. The commit's own identity fields -- author and committer.
if git log --format='%h %an <%ae>%n%h %cn <%ce>' | grep -iE "$tools"; then
  report "An assistant is named as an author or committer."
fi

# 2. Trailer lines. Only flagged when a tool name follows the trailer, so a
#    human co-author remains legitimate.
if git log --format='%B' |
   grep -inE "^[[:space:]]*(co-authored-by|signed-off-by|assisted-by|generated-by)[[:space:]]*:.*($tools)"; then
  report "A commit trailer attributes the work to an assistant."
fi

# 3. Free-form generation notices, e.g. "Generated with Claude Code".
if git log --format='%B' | grep -inE "generated[[:space:]]+(with|by)[^[:alnum:]]{0,4}($tools)"; then
  report "A commit body carries a generated-with notice."
fi

if [ "$fail" -ne 0 ]; then
  exit 1
fi
echo "Commit history clean: no AI attribution in $(git rev-list --count HEAD) commits."
