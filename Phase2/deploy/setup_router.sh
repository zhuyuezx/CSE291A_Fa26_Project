#!/usr/bin/env bash
# Set up the router node: tools, a Python venv for the harness and router,
# the fleet endpoint list, and the `fleet-run` experiment lock.
#
#   scp -i team.pem Phase2/deploy/{setup_router.sh,fleet-run.sh,endpoints.json} ubuntu@<router>:
#   ssh -i team.pem ubuntu@<router> 'bash setup_router.sh'
#
# Re-running is safe.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)

APT=(sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600)
"${APT[@]}" update -y
"${APT[@]}" install -y git python3-venv python3-pip tmux jq curl
# Background upgrades would add CPU noise to client-side latency measurements.
sudo systemctl disable --now unattended-upgrades 2>/dev/null || true

sudo mkdir -p /opt/fleet && sudo chown "$(id -u):$(id -g)" /opt/fleet
[ -d /opt/fleet/venv ] || python3 -m venv /opt/fleet/venv
/opt/fleet/venv/bin/pip install -q --upgrade pip
/opt/fleet/venv/bin/pip install -q requests numpy pandas matplotlib psutil scikit-learn

cp "$HERE/endpoints.json" /opt/fleet/endpoints.json
sudo install -m 755 "$HERE/fleet-run.sh" /usr/local/bin/fleet-run

echo "python: $(/opt/fleet/venv/bin/python --version)  (activate: source /opt/fleet/venv/bin/activate)"
fleet-run status
