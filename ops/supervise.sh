#!/bin/bash
# Mission HQ backend supervision on macOS (launchd LaunchAgent).
#
#   ops/supervise.sh install    copy the plist into ~/Library/LaunchAgents and start it
#   ops/supervise.sh uninstall  stop it and remove the plist
#   ops/supervise.sh status     is it loaded, is the API answering
#   ops/supervise.sh restart    bounce the process (launchd restarts it)
#   ops/supervise.sh logs       tail the backend log
#
# KeepAlive means launchd restarts the backend after any exit, including a
# crash or a kill -9. It does NOT keep the laptop awake: a sleeping Mac runs
# nothing. For an always-on box use `caffeinate -s` or a Mac that stays plugged
# in with "Prevent automatic sleeping" enabled.
set -euo pipefail

LABEL=com.missionhq.backend
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
LOG="$HERE/../data/logs/backend.log"

case "${1:-status}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$HERE/../data/logs"
    # The plist is a template: it must not name a user, because this repo is
    # cloned onto other machines. Fill it in for this one at install time.
    REPO="$(cd "$HERE/.." && pwd)"
    PYTHON="$REPO/backend/.venv/bin/python"
    if [ ! -x "$PYTHON" ]; then
      echo "No virtualenv at $PYTHON. Run 'uv sync' in backend/ first." >&2
      exit 1
    fi
    sed -e "s|__PYTHON__|$PYTHON|g" -e "s|__REPO__|$REPO|g" -e "s|__HOME__|$HOME|g" \
      "$SRC" > "$DST"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DST"
    echo "installed and started $LABEL"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$DST"
    echo "removed $LABEL"
    ;;
  restart)
    before="$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
    launchctl kickstart -k "$DOMAIN/$LABEL"
    # Verify rather than assume. A restart that silently does nothing leaves
    # you testing an old process against new code, which is worse than an
    # error: every result looks like the change did not work.
    # Startup is DBOS init plus agent loading plus Telegram, which takes well
    # over 30s on a cold cache. Too short a wait reports a false failure.
    for _ in $(seq 1 90); do
      sleep 1
      after="$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t 2>/dev/null | head -1 || true)"
      if [ -n "$after" ] && [ "$after" != "$before" ]; then
        echo "restarted $LABEL (pid ${before:-none} -> $after)"
        exit 0
      fi
    done
    echo "WARNING: $LABEL still serving on the old pid (${before:-none})." >&2
    echo "Run: $0 uninstall && $0 install" >&2
    exit 1
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "launchd: loaded"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state|pid|last exit" | sed 's/^/  /'
    else
      echo "launchd: not loaded (run: ops/supervise.sh install)"
    fi
    TOKEN="$(grep '^API_BEARER_TOKEN=' "$HERE/../backend/.env" 2>/dev/null | cut -d= -f2-)"
    printf "api:     %s\n" "$(curl -s -m 3 -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/health || echo 'not answering')"
    ;;
  logs)
    tail -f "$LOG"
    ;;
  *)
    sed -n '2,12p' "$0"; exit 2
    ;;
esac
