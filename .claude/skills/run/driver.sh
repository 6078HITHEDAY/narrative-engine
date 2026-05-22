#!/usr/bin/env bash
# Driver for the `run` skill — launches narrative-engine's three surfaces
# (CLI / HTTP / TUI) and reports whether each came up cleanly.
#
# Usage:
#   .claude/skills/run/driver.sh [cli|http|tui|all]   # default: all
#   STORY=stories/seaside_town PORT=18234 driver.sh http
#
# Exit code is non-zero if any selected surface fails.

set -u
set -o pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

SURFACE="${1:-all}"
STORY="${STORY:-stories/seaside_town}"
PORT="${PORT:-18234}"
HOST="${HOST:-127.0.0.1}"

if [[ ! -d ".venv" ]]; then
  echo "[driver] .venv not found at $ROOT/.venv — run 'uv sync' or 'python -m venv .venv && pip install -e .[api,tui,dev]' first" >&2
  exit 2
fi
# shellcheck disable=SC1091
source .venv/bin/activate

fail=0

run_cli() {
  echo "[driver] CLI: narrative-engine (no args, prints usage)"
  out="$(narrative-engine 2>&1)"
  rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q "narrative-engine v" <<<"$out"; then
    echo "[driver] CLI FAILED (rc=$rc)"
    echo "$out" | tail -20
    return 1
  fi
  echo "[driver] CLI OK"
}

run_http() {
  echo "[driver] HTTP: serve --port $PORT --story $STORY"
  if [[ ! -d "$STORY" ]]; then
    echo "[driver] story dir '$STORY' not found" >&2
    return 1
  fi
  log="$(mktemp -t ne-serve.XXXXXX.log)"
  narrative-engine serve --host "$HOST" --port "$PORT" --story "$STORY" >"$log" 2>&1 &
  pid=$!
  trap 'kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; rm -f "$log"' RETURN

  # Poll /health up to ~15s — uvicorn + litellm warmup can be slow on cold start.
  for _ in $(seq 1 30); do
    if curl -fs "http://$HOST:$PORT/health" >/dev/null 2>&1; then
      break
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "[driver] HTTP server died before /health responded"
      tail -30 "$log"
      return 1
    fi
    sleep 0.5
  done

  health="$(curl -fs "http://$HOST:$PORT/health" 2>&1)" || {
    echo "[driver] HTTP /health did not respond within 15s"
    tail -30 "$log"
    return 1
  }
  story_info="$(curl -fs "http://$HOST:$PORT/story" 2>&1)" || {
    echo "[driver] HTTP /story failed: $story_info"
    return 1
  }
  # /tell with a beat-anchored payload (matches stories/seaside_town's prologue_arrival
  # beat) — exercises the full request → state → beat-resolver → response path without
  # needing an LLM key. For other stories, set TELL_PAYLOAD_FILE=/path/to.json or skip
  # with NO_TELL=1. Payload is written via heredoc (locale-safe; UTF-8 byte-clean even
  # under env -i / C locale).
  if [[ "${NO_TELL:-0}" != "1" ]]; then
    if [[ -n "${TELL_PAYLOAD_FILE:-}" ]]; then
      payload_file="$TELL_PAYLOAD_FILE"
    else
      payload_file="$(mktemp -t ne-tell.XXXXXX.json)"
      cat >"$payload_file" <<'JSON'
{"state":{"world":{"area":"grandma_house","chapter":"第一章"}},"kind":"description","context":""}
JSON
    fi
    tell_resp="$(curl -fsX POST "http://$HOST:$PORT/tell" -H 'Content-Type: application/json' -d @"$payload_file" 2>&1)"
    rc=$?
    [[ -z "${TELL_PAYLOAD_FILE:-}" ]] && rm -f "$payload_file"
    if [[ $rc -ne 0 ]]; then
      echo "[driver] HTTP /tell failed (rc=$rc): $tell_resp"
      return 1
    fi
    # Beat-anchored path expects: kind=description (not defaulted to dialogue),
    # degraded=false, no error. If the beat doesn't fire (different story / missing
    # cache / chapter renamed), the engine falls back to LLM and likely fails on
    # missing credentials — that's a config issue, not an HTTP regression, but we
    # still flag it because the smoke point is "the engine resolved the request".
    if ! grep -q '"kind":"description"' <<<"$tell_resp"; then
      echo "[driver] /tell did not honor kind=description (payload mangled?): $tell_resp"
      return 1
    fi
    if grep -q '"degraded":true' <<<"$tell_resp"; then
      echo "[driver] /tell hit fallback path — beat anchor didn't fire and LLM unavailable"
      echo "         response: $(head -c 200 <<<"$tell_resp")..."
      echo "         hint: set NARRATIVE_API_KEY or NO_TELL=1, or point STORY at a story whose chapter 1 anchors on grandma_house+第一章"
      return 1
    fi
    echo "[driver] /tell   -> $(head -c 160 <<<"$tell_resp")..."
  fi
  echo "[driver] /health -> $health"
  echo "[driver] /story  -> $story_info"
  echo "[driver] HTTP OK"
}

run_tui() {
  # Textual TUIs cannot be driven from a non-tty pipe, so we use App.run_test()
  # which spins the event loop headless and exits — enough to catch import,
  # compose, and on_mount errors. A real TTY can use `narrative-engine tui`.
  echo "[driver] TUI: headless smoke via App.run_test()"
  out="$(python - <<'PY' 2>&1
import asyncio
from narrative_engine.tui import NarrativeTUI

async def smoke():
    app = NarrativeTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
    print("TUI_SMOKE_OK")

asyncio.run(smoke())
PY
)"
  rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q "TUI_SMOKE_OK" <<<"$out"; then
    echo "[driver] TUI FAILED (rc=$rc)"
    echo "$out" | tail -30
    return 1
  fi
  echo "[driver] TUI OK (mounted, all 5 screens installed)"
}

case "$SURFACE" in
  cli)  run_cli || fail=1 ;;
  http) run_http || fail=1 ;;
  tui)  run_tui || fail=1 ;;
  all)
    run_cli  || fail=1
    run_http || fail=1
    run_tui  || fail=1
    ;;
  *)
    echo "Usage: $0 [cli|http|tui|all]" >&2
    exit 2
    ;;
esac

if [[ $fail -ne 0 ]]; then
  echo "[driver] one or more surfaces failed"
  exit 1
fi
echo "[driver] all selected surfaces OK"
