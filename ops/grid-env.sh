#!/bin/bash
# Keeps GRID_API_KEY in the user's launchd environment across reboots.
#
# The Codex Chrome extension and the ChatGPT app are started by Chrome and the
# Dock, not by a shell, so a key exported in ~/.zshrc never reaches them and
# their Grid (juspay) provider fails with "Missing environment variable:
# GRID_API_KEY". `launchctl setenv` fixes that for apps launched afterwards,
# but it is lost on reboot, so a login agent repeats it.
#
#   ops/grid-env.sh install     read the key from backend/.env, set it now and
#                               install the login agent
#   ops/grid-env.sh uninstall   remove the agent and unset the variable
#   ops/grid-env.sh status
#
# Run it from a terminal, not from launchd: the agent itself cannot read this
# checkout when it lives under ~/Desktop (macOS privacy protection), which is
# why the key is written into the agent's plist (mode 600) at install time.
# After rotating the key in backend/.env, run `install` again, then restart
# Chrome and the ChatGPT app: a running app keeps the environment it started with.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${HQ_ENV_FILE:-$ROOT/backend/.env}"
LABEL="com.missionhq.gridenv"
AGENT="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"

xml_escape() { local s="$1"; s="${s//&/&amp;}"; s="${s//</&lt;}"; echo "${s//>/&gt;}"; }

install_agent() {
  local key
  key="$(grep -E '^(export )?GRID_API_KEY=' "$ENV_FILE" | tail -n 1 | cut -d= -f2- || true)"
  key="${key%\"}"; key="${key#\"}"; key="${key%\'}"; key="${key#\'}"
  if [ -z "$key" ]; then
    echo "grid-env: GRID_API_KEY is not set in $ENV_FILE" >&2
    exit 1
  fi

  local template umask_before
  template="$(cat "$ROOT/ops/$LABEL.plist")"
  umask_before="$(umask)"
  umask 077
  mkdir -p "$(dirname "$AGENT")"
  echo "${template//__GRID_API_KEY__/$(xml_escape "$key")}" > "$AGENT"
  umask "$umask_before"
  chmod 600 "$AGENT"
  plutil -lint "$AGENT" > /dev/null

  launchctl bootout "$DOMAIN/$LABEL" 2> /dev/null || true
  launchctl bootstrap "$DOMAIN" "$AGENT"
  launchctl setenv GRID_API_KEY "$key"
  echo "grid-env: installed $AGENT (mode 600) and set GRID_API_KEY for this session"
  echo "grid-env: restart Chrome and the ChatGPT app to pick it up"
}

case "${1:-status}" in
  install) install_agent ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2> /dev/null || true
    rm -f "$AGENT"
    launchctl unsetenv GRID_API_KEY
    echo "grid-env: removed" ;;
  status)
    if [ -f "$AGENT" ]; then echo "agent installed: $AGENT"; else echo "agent not installed"; fi
    if [ -n "$(launchctl getenv GRID_API_KEY)" ]; then echo "GRID_API_KEY is set in launchd"; else echo "GRID_API_KEY is NOT set in launchd"; fi ;;
  *) echo "usage: $0 install|uninstall|status" >&2; exit 2 ;;
esac
