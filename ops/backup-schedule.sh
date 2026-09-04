#!/bin/bash
# Mission HQ nightly backup schedule on macOS (launchd LaunchAgent, 03:30).
#
#   ops/backup-schedule.sh install    copy the plist into ~/Library/LaunchAgents and load it
#   ops/backup-schedule.sh uninstall  unload it and remove the plist
#   ops/backup-schedule.sh status     is it loaded, when did it last run, newest dump
#   ops/backup-schedule.sh run-now    run one backup right now through launchd
#   ops/backup-schedule.sh logs       tail the backup log
#
# The job runs `ops/backup.sh run`. Test a restore with `ops/backup.sh restore-drill`.
set -euo pipefail

LABEL=com.missionhq.backup
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SRC="$HERE/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
DOMAIN="gui/$(id -u)"
LOG="$ROOT/data/logs/backup.log"

case "${1:-status}" in
  install)
    mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/data/logs" "$ROOT/data/snapshots"
    cp "$SRC" "$DST"
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$DST"
    echo "installed $LABEL (runs nightly at 03:30)"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$DST"
    echo "removed $LABEL"
    ;;
  run-now)
    launchctl kickstart "$DOMAIN/$LABEL"
    echo "started $LABEL; follow with: ops/backup-schedule.sh logs"
    ;;
  status)
    if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
      echo "launchd: loaded (03:30 nightly)"
      launchctl print "$DOMAIN/$LABEL" | grep -E "state|last exit" | sed 's/^/  /'
    else
      echo "launchd: not loaded (run: ops/backup-schedule.sh install)"
    fi
    newest="$(ls -1t "$ROOT"/data/snapshots/missionhq-*.sql.gz 2>/dev/null | head -1)"
    if [ -n "$newest" ]; then
      echo "newest:  $(basename "$newest") ($(du -h "$newest" | cut -f1), $(date -r "$newest" '+%Y-%m-%d %H:%M'))"
    else
      echo "newest:  no dumps yet"
    fi
    [ -f "$LOG" ] && { echo "last log lines:"; tail -3 "$LOG" | sed 's/^/  /'; }
    ;;
  logs)
    tail -f "$LOG"
    ;;
  *)
    sed -n '2,10p' "$0"; exit 2
    ;;
esac
