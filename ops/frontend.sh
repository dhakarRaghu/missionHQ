#!/bin/bash
# Mission HQ frontend supervision on macOS (launchd LaunchAgent).
#
#   ops/frontend.sh install    copy the plist into ~/Library/LaunchAgents and start it
#   ops/frontend.sh uninstall  stop it and remove the plist
#   ops/frontend.sh status     is it loaded, is port 3000 answering
#   ops/frontend.sh restart    bounce the process (launchd restarts it)
#   ops/frontend.sh logs       tail the frontend log
#
# The service runs `npm run start` (= `next start -p 3000 -H 127.0.0.1`) in
# frontend/. `next start` serves the LAST BUILD only. After every frontend
# change run:
#
#   cd frontend && npm run build && ../ops/frontend.sh restart
#
# Without a rebuild the running site keeps the old code. `install` and
# `restart` refuse to run when frontend/.next/BUILD_ID is missing.
#
# The frontend is reached through Caddy (ops/Caddyfile) on 127.0.0.1:8080,
# never directly. It binds to 127.0.0.1 so nothing on the LAN can reach it.
set -euo pipefail

LABEL=com.missionhq.frontend
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC="$HERE/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
LOG="$ROOT/data/logs/frontend.log"
BUILD_ID="$ROOT/frontend/.next/BUILD_ID"

need_build() {
  if [ ! -f "$BUILD_ID" ]; then
    echo "no production build found ($BUILD_ID missing)." >&2
    echo "run: cd $ROOT/frontend && npm run build" >&2
    exit 1
  fi
}

case "${1:-status}" in
  install)
    need_build
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs"
    cp "$SRC" "$DST"
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
    need_build
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "restarted $LABEL (serving build $(cat "$BUILD_ID"))"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "launchd: loaded"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state|pid|last exit" | sed 's/^/  /'
    else
      echo "launchd: not loaded (run: ops/frontend.sh install)"
    fi
    if [ -f "$BUILD_ID" ]; then
      echo "build:   $(cat "$BUILD_ID") ($(date -r "$BUILD_ID" '+%Y-%m-%d %H:%M'))"
    else
      echo "build:   none (run: cd frontend && npm run build)"
    fi
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:3000/ 2>/dev/null || true)"
    [ "$code" = "000" ] || [ -z "$code" ] && code="not answering"
    echo "web:     / -> HTTP $code"
    ;;
  logs)
    tail -f "$LOG"
    ;;
  *)
    sed -n '2,18p' "$0"; exit 2
    ;;
esac
