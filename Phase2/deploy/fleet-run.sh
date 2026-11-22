#!/usr/bin/env bash
# One experiment at a time on the shared fleet. Installed on the router as
# /usr/local/bin/fleet-run by setup_router.sh.
#
#   fleet-run <your-name> <command...>          run holding the fleet lock; refuse if busy
#   fleet-run --wait <your-name> <command...>   wait for the lock instead of refusing
#   fleet-run status                            lock holder, and each endpoint's health and busy slots
#
# Launch every router-side measurement through this. While a single-node test
# runs over SSH from a laptop, hold the fleet with `fleet-run <name> sleep 1800`.
# The lock is released when the command exits, even if it crashes.
set -euo pipefail
LOCK=/run/lock/cse291-fleet.lock
OWNER=/run/lock/cse291-fleet.owner
EPS=/opt/fleet/endpoints.json

status() {
  if flock -n "$LOCK" true 2>/dev/null; then
    echo "fleet: free"
  else
    echo "fleet: BUSY, $(cat "$OWNER" 2>/dev/null || echo 'owner unknown')"
  fi
  jq -r '.endpoints[] | "\(.name) \(.private_ip) \(.port) \(.instance_type)"' "$EPS" |
  while read -r name ip port type; do
    if curl -sf -m 2 "http://$ip:$port/health" >/dev/null; then
      busy=$(curl -s -m 2 "http://$ip:$port/slots" |
             jq '[.[] | select(.is_processing)] | length' 2>/dev/null || echo "?")
      echo "  $name  $type  $ip  up, busy slots: $busy"
    else
      echo "  $name  $type  $ip  DOWN"
    fi
  done
}

if [ "${1:-}" = "status" ]; then status; exit 0; fi
WAIT=""
if [ "${1:-}" = "--wait" ]; then WAIT=1; shift; fi
NAME=${1:?usage: fleet-run [--wait] <your-name> <command...>  |  fleet-run status}
shift
if [ $# -eq 0 ]; then echo "no command given" >&2; exit 2; fi

exec 9>>"$LOCK"
chmod 666 "$LOCK" 2>/dev/null || true
if ! flock -n 9; then
  if [ -z "$WAIT" ]; then
    echo "fleet busy: $(cat "$OWNER" 2>/dev/null). Re-run with --wait to queue." >&2
    exit 1
  fi
  echo "waiting for fleet: $(cat "$OWNER" 2>/dev/null)"
  flock 9
fi
echo "$NAME: $* (since $(date '+%Y-%m-%d %H:%M:%S %Z'), pid $$)" > "$OWNER"
chmod 666 "$OWNER" 2>/dev/null || true
trap 'rm -f "$OWNER"' EXIT
"$@"
