#!/bin/bash
# Mission HQ backups: Postgres dump + vault push, and a restore drill.
#
#   ops/backup.sh run            pg_dump | gzip -> data/snapshots/missionhq-<date>.sql.gz,
#                                delete dumps older than 14 days, then `git -C vault push`
#                                if the vault has a remote named origin (else skip quietly)
#   ops/backup.sh list           show the dumps on disk
#   ops/backup.sh sync-remote    push the current database AND the learning files
#                                (lessons, course specs, course sources) to
#                                BACKUP_DATABASE_URL
#                                (an off-machine mirror, weekly). Local Postgres
#                                stays the only live database; nothing reads the
#                                mirror while Mission HQ runs.
#   ops/backup.sh restore-drill  restore the newest dump into a scratch database
#                                `missionhq_drill`, count rows in hq.tasks, drop the
#                                scratch database. Proves the dump is usable.
#
# Nightly: the backend makes the dump (hq/backups.py) and pushes the vault
# (hq/memory.py) after the 03:00 reindex. A launchd job running this script
# may not read ~/Desktop (macOS: "Operation not permitted"), so
# ops/backup-schedule.sh install only works with the repo outside ~/Desktop.
#
# Database: DATABASE_URL from backend/.env, or the environment, or the default
# postgresql://localhost:5432/missionhq. pg_dump and psql must be on PATH
# (Postgres.app: /Applications/Postgres.app/Contents/Versions/latest/bin,
# Homebrew: /opt/homebrew/opt/postgresql@16/bin, or /usr/local/bin).
#
# Safe to run while the backend is running: pg_dump takes a consistent
# snapshot and does not block writers.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
SNAP="$ROOT/data/snapshots"
VAULT="$ROOT/vault"
KEEP_DAYS=14
DRILL_DB=missionhq_drill

# --- DATABASE_URL -----------------------------------------------------------
if [ -z "${DATABASE_URL:-}" ] && [ -f "$ROOT/backend/.env" ]; then
  # Only the DATABASE_URL line is read. Quotes around the value are removed.
  DATABASE_URL="$(grep -E '^DATABASE_URL=' "$ROOT/backend/.env" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
DATABASE_URL="${DATABASE_URL:-postgresql://localhost:5432/missionhq}"

# The off-machine mirror. Same file, same rule: the value is never printed.
if [ -z "${BACKUP_DATABASE_URL:-}" ] && [ -f "$ROOT/backend/.env" ]; then
  BACKUP_DATABASE_URL="$(grep -E '^BACKUP_DATABASE_URL=' "$ROOT/backend/.env" | tail -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")"
fi
BACKUP_DATABASE_URL="${BACKUP_DATABASE_URL:-}"

# Same server, different database name. Keeps any ?sslmode=... query string.
drill_url() {
  local base="${DATABASE_URL%%\?*}" query=""
  case "$DATABASE_URL" in *\?*) query="?${DATABASE_URL#*\?}" ;; esac
  printf '%s/%s%s' "${base%/*}" "$DRILL_DB" "$query"
}

log() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

latest_dump() {
  ls -1t "$SNAP"/missionhq-*.sql.gz 2>/dev/null | head -1
}

# --- actions ----------------------------------------------------------------
do_run() {
  mkdir -p "$SNAP"
  local out="$SNAP/missionhq-$(date +%F).sql.gz" tmp
  tmp="$out.part"
  log "dumping $DATABASE_URL -> $out"
  # --no-owner/--no-privileges: restores into any role, including the drill.
  # Pipe failures must fail the script, so pg_dump errors are not hidden by gzip.
  pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip -9 > "$tmp"
  mv "$tmp" "$out"
  log "dump done: $(du -h "$out" | cut -f1)"

  local removed
  removed="$(find "$SNAP" -name 'missionhq-*.sql.gz' -mtime +"$KEEP_DAYS" -print -delete | wc -l | tr -d ' ')"
  log "pruned $removed dump(s) older than $KEEP_DAYS days"

  if git -C "$VAULT" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
     && git -C "$VAULT" remote get-url origin >/dev/null 2>&1; then
    log "pushing vault to origin"
    git -C "$VAULT" push --quiet origin HEAD
    log "vault push done"
  fi
  log "backup finished"
}

# Push everything to the mirror: schema and data, dropping what is there
# first so the mirror equals local rather than accumulating old rows. The
# dump goes through a file, not a pipe, so a failed dump never reaches the
# remote and half-writes it.
do_sync_remote() {
  if [ -z "$BACKUP_DATABASE_URL" ]; then
    echo "no BACKUP_DATABASE_URL in backend/.env or the environment" >&2
    exit 2
  fi
  mkdir -p "$SNAP"
  local tmp="$SNAP/remote-sync.sql"
  log "dumping local database for the mirror"
  # hq.learning_files is the mirror's own table, written by mirror_files.py
  # below. A copy of it in the local database (one restored from the mirror)
  # must not replace it: on 2026-09-29 a local copy without its primary key
  # did, and the file upsert then failed.
  # The vault's memory stays on this machine. hq.memory_chunks and hq.facts
  # are what the agents remember, not what he learns, and he asked for the
  # mirror to carry the courses and the learning, nothing else.
  pg_dump --no-owner --no-privileges --clean --if-exists \
          --schema=hq --schema=public \
          --exclude-table=hq.memory_chunks --exclude-table=hq.facts \
          --exclude-table=hq.learning_files \
          "$DATABASE_URL" > "$tmp"
  log "dump ready: $(du -h "$tmp" | cut -f1); pushing to the mirror"
  # ON_ERROR_STOP is off on purpose: DROP of an object the mirror has never
  # seen is normal on a first run, and must not stop the restore.
  if ! psql -q -v ON_ERROR_STOP=0 "$BACKUP_DATABASE_URL" -f "$tmp" > "$SNAP/remote-sync.log" 2>&1; then
    log "mirror push failed; see $SNAP/remote-sync.log"
    rm -f "$tmp"
    exit 1
  fi
  rm -f "$tmp"

  # The database stores paths; the lessons, course specs and course sources
  # are files. A mirror without them is not a backup of what he learned.
  log "copying the learning files to the mirror"
  BACKUP_DATABASE_URL="$BACKUP_DATABASE_URL" \
    "$ROOT/backend/.venv/bin/python" "$HERE/mirror_files.py"

  # psql runs with ON_ERROR_STOP off, so its exit code says nothing about
  # whether the data arrived. Count every local table on both sides instead.
  local report missing=0
  report="$(
    psql -tA "$DATABASE_URL" -c "SELECT tablename FROM pg_tables WHERE schemaname = 'hq'
          AND tablename NOT IN ('memory_chunks', 'facts', 'learning_files') ORDER BY 1" |
    while read -r t; do
      [ -z "$t" ] && continue
      local_n="$(psql -tA "$DATABASE_URL" -c "SELECT count(*) FROM hq.\"$t\"" 2>/dev/null || echo '?')"
      remote_n="$(psql -tA "$BACKUP_DATABASE_URL" -c "SELECT count(*) FROM hq.\"$t\"" 2>/dev/null || echo 'MISSING')"
      printf '%s\t%s\t%s\n' "$t" "$local_n" "$remote_n"
    done
  )"
  printf '%s\n' "$report" | awk -F'\t' '{printf "  %-22s local %-7s mirror %s\n", $1, $2, $3}'
  missing="$(printf '%s\n' "$report" | awk -F'\t' '$2 != $3' | wc -l | tr -d ' ')"
  if [ "$missing" != "0" ]; then
    log "$missing table(s) do not match; see $SNAP/remote-sync.log"
    echo "REMOTE SYNC INCOMPLETE: $missing table(s) differ"
    exit 1
  fi
  log "mirror matches local on every hq table"
  echo "REMOTE SYNC OK"
}

do_list() {
  ls -lh "$SNAP"/missionhq-*.sql.gz 2>/dev/null || echo "no dumps in $SNAP"
}

do_restore_drill() {
  local dump durl
  dump="$(latest_dump)"
  if [ -z "$dump" ]; then
    echo "no dump found in $SNAP. Run: ops/backup.sh run" >&2
    exit 1
  fi
  durl="$(drill_url)"
  log "restore drill: $dump -> $DRILL_DB"

  # Always drop the scratch database, even if the restore fails half way.
  cleanup() {
    psql -q -v ON_ERROR_STOP=0 "$DATABASE_URL" -c "DROP DATABASE IF EXISTS $DRILL_DB" >/dev/null 2>&1 || true
  }
  trap cleanup EXIT

  cleanup
  psql -q -v ON_ERROR_STOP=1 "$DATABASE_URL" -c "CREATE DATABASE $DRILL_DB"
  # The dump has no CREATE DATABASE (no -C), so it restores into any database.
  gunzip -c "$dump" | psql -q -v ON_ERROR_STOP=1 "$durl" >/dev/null

  local tasks
  tasks="$(psql -tA -v ON_ERROR_STOP=1 "$durl" -c 'SELECT count(*) FROM hq.tasks')"
  log "restore ok: hq.tasks has $tasks row(s) in $DRILL_DB"
  log "dropping $DRILL_DB"
  # trap runs cleanup on exit
  echo "RESTORE DRILL PASSED: $dump ($tasks tasks)"
}

case "${1:-}" in
  run)           do_run ;;
  sync-remote)   do_sync_remote ;;
  list)          do_list ;;
  restore-drill) do_restore_drill ;;
  *)             sed -n '2,20p' "$0"; exit 2 ;;
esac
