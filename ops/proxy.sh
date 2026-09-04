#!/bin/bash
# Mission HQ reverse proxy (Caddy) supervision on macOS (launchd LaunchAgent).
#
#   ops/proxy.sh caddy install    copy the plist into ~/Library/LaunchAgents and start it
#   ops/proxy.sh caddy uninstall  stop it and remove the plist
#   ops/proxy.sh caddy status     is it loaded, is 127.0.0.1:8080 answering
#   ops/proxy.sh caddy restart    bounce the process (re-reads ops/Caddyfile)
#   ops/proxy.sh caddy logs       tail the caddy log
#
# Runs `caddy run --config ops/Caddyfile`. Assumes Caddy is installed with
# `brew install caddy`; this script does NOT install it. Tailscale Serve then
# fronts port 8080 (`tailscale serve --bg 8080`), see ops/Caddyfile. Never use
# Funnel.
#
# The `caddy` mode name leaves room for another proxy later. Only caddy exists.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DOMAIN="gui/$(id -u)"

MODE="${1:-caddy}"
ACTION="${2:-status}"

case "$MODE" in
  caddy)
    LABEL=com.missionhq.caddy
    SRC="$HERE/$LABEL.plist"
    DST="$HOME/Library/LaunchAgents/$LABEL.plist"
    LOG="$ROOT/data/logs/caddy.log"
    CADDY="$(command -v caddy || true)"
    ;;
  *)
    sed -n '2,15p' "$0"; exit 2
    ;;
esac

need_caddy() {
  if [ -z "$CADDY" ]; then
    echo "caddy not found on PATH. Install it first: brew install caddy" >&2
    exit 1
  fi
  "$CADDY" validate --config "$HERE/Caddyfile" --adapter caddyfile >/dev/null
}

case "$ACTION" in
  install)
    need_caddy
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs" "$ROOT/data/caddy"
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
    need_caddy
    launchctl kickstart -k "$DOMAIN/$LABEL"
    echo "restarted $LABEL"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "launchd: loaded"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state|pid|last exit" | sed 's/^/  /'
    else
      echo "launchd: not loaded (run: ops/proxy.sh caddy install)"
    fi
    echo "caddy:   ${CADDY:-not installed (brew install caddy)}"
    code="$(curl -s -o /dev/null -w '%{http_code}' -m 3 http://127.0.0.1:8080/ 2>/dev/null || true)"
    [ "$code" = "000" ] || [ -z "$code" ] && code="not answering"
    echo "proxy:   / -> HTTP $code"
    echo "api:     /api/health -> $(curl -s -m 3 http://127.0.0.1:8080/api/health 2>/dev/null || echo 'not answering')"
    ;;
  logs)
    tail -f "$LOG"
    ;;
  *)
    sed -n '2,15p' "$0"; exit 2
    ;;
esac
