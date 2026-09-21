#!/usr/bin/env bash
#
# One command from a fresh clone to the console open in a browser.
#
#     ./run.sh
#
# Every step is skipped when it has already been done, so the second run takes
# seconds. The console opens as soon as it is ready; the model check runs after
# it and reports into the same terminal, because a free tier that is retrying
# should not hold up a page that is ready to look at. Ctrl-C stops the server.
#
#     ./run.sh --no-ai      skip the model check
#     ./run.sh --port 8001  serve somewhere else
#     ./run.sh --no-open    do not open a browser
#
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PORT=8000
CHECK_AI=1
OPEN_BROWSER=1

while [ $# -gt 0 ]; do
  case "$1" in
    --no-ai)    CHECK_AI=0; shift ;;
    --no-open)  OPEN_BROWSER=0; shift ;;
    --port)     PORT="${2:?--port needs a number}"; shift 2 ;;
    -h|--help)  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)          echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

BASE="http://127.0.0.1:${PORT}"
PY=.venv/bin/python

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
step() { printf '\033[36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*"; }
good() { printf '\033[32m  ok\033[0m %s\n' "$*"; }

# Ask the server whether it is up, through the venv's Python so nothing here
# depends on curl being installed.
health() {
  "$PY" - "$BASE" <<'PROBE' 2>/dev/null
import json, sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1] + "/api/health", timeout=3) as r:
        sys.exit(0 if json.loads(r.read()).get("status") == "ok" else 1)
except Exception:
    sys.exit(1)
PROBE
}

open_browser() {
  [ "$OPEN_BROWSER" = 1 ] || return 0
  if command -v open >/dev/null 2>&1; then open "$BASE"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$BASE" >/dev/null 2>&1
  fi
}

# The cache is switched off on purpose. With it on, a stored answer is served
# and the checker reports zero calls, which reads as a failure even though the
# output is correct. Off is the only setting that proves the backend answered.
check_model() {
  step "model"
  local log
  log="$(mktemp -t whychain-ai)"
  if PYTHONPATH=. WHYCHAIN_LLM_CACHE=off "$PY" scripts/verify_ai.py >"$log" 2>&1; then
    if grep -q "Both model stages work" "$log"; then
      good "$(grep -m1 'Backend' "$log" | sed 's/Backend *//')"
      good "extraction and narrative both answered"
    else
      warn "no model backend is configured, so the engine runs its deterministic"
      warn "path and the receipt reports zero model calls. Details: $log"
    fi
  else
    # This check is strict on purpose: a citation whose span does not resolve
    # back into the source is dropped, and a stage that ends with nothing left
    # counts as a failure even though dropping it is the guardrail working.
    # A free hosted model reproduces a quote verbatim only most of the time, so
    # this can fail on one run and pass on the next with nothing changed.
    warn "the model path did not pass the strict check. The console still works:"
    warn "both stages fall back to deterministic code and the receipt says so."
    warn "Run 'make warm-ai' before a demo to fill the cache from a good run."
    sed 's/^/     /' "$log" | tail -20
  fi
  echo
  bold "  $BASE"
  echo "  Ctrl-C to stop."
  echo
}

bold "WhyChain"
echo

# 1. Python environment -------------------------------------------------------
step "environment"
if [ ! -x .venv/bin/uvicorn ]; then
  command -v python3 >/dev/null 2>&1 || { echo "python3 is not installed" >&2; exit 1; }
  warn "building the virtualenv and installing dependencies, about two minutes"
  make setup >/dev/null
fi
good "$("$PY" -V)"

# 2. Configuration ------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  warn ".env created from .env.example; the engine runs deterministically until a backend is configured"
fi

# 3. Synthetic warehouse ------------------------------------------------------
step "data"
if [ ! -s data/warehouse/whychain.duckdb ]; then
  warn "generating the synthetic warehouse, about forty seconds"
  make gen >/dev/null
fi
# Idempotent, and skipped in a second when already done. A warehouse generated
# before this step existed still reads correctly, just slower, so this is a
# speed-up rather than a requirement.
make prepare ARGS=retail >/dev/null 2>&1 || true
good "warehouse present"

# 4. Server -------------------------------------------------------------------
# Before the model check, so the console is on screen while a free tier is
# still backing off.
step "server"
if health; then
  good "already running on port $PORT"
  echo
  bold "  $BASE"
  open_browser
  [ "$CHECK_AI" = 1 ] && check_model
  exit 0
fi

.venv/bin/uvicorn api.main:app --port "$PORT" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT INT TERM

for _ in $(seq 1 60); do
  health && break
  kill -0 "$SERVER_PID" 2>/dev/null || { echo "the server exited during start-up" >&2; exit 1; }
  sleep 1
done

if ! health; then
  echo "the server did not become healthy within sixty seconds" >&2
  exit 1
fi

good "listening on port $PORT"
echo
bold "  $BASE"
echo
open_browser

# 5. The model path -----------------------------------------------------------
if [ "$CHECK_AI" = 1 ]; then
  check_model
else
  echo "  Ctrl-C to stop."
  echo
fi

wait "$SERVER_PID"
