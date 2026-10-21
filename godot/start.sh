#!/usr/bin/env bash
# Launch Godot on this machine, in its own window (the read-only simulation view). Usage: ./godot/start.sh
# Reads ../.env if present. The backend (Docker or local) connects to it on GODOT_LISTEN:GODOT_PORT.
# Closing the window stops the simulation; run this script again to relaunch it (the backend reconnects by itself).
set -euo pipefail
cd "$(dirname "$0")"
if [ -f ../.env ]; then set -a; . ../.env; set +a; fi

want="${GODOT_VERSION:-4.7.2}"   # same version as the Docker image (Dockerfile ARG GODOT_VERSION)
godot=""
for candidate in "${GODOT_BIN:-}" "$(command -v godot || true)" \
                 "/Applications/Godot.app/Contents/MacOS/Godot" "$HOME/Applications/Godot.app/Contents/MacOS/Godot"; do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then godot="$candidate"; break; fi
done
if [ -z "$godot" ]; then
  echo "Godot introuvable : installez Godot $want (brew install --cask godot) ou définissez GODOT_BIN dans .env." >&2
  exit 1
fi
version="$("$godot" --version | head -n 1)"
case "$version" in
  "$want".*) ;;
  *) echo "Godot $version trouvé ($godot), mais $want est attendu (GODOT_VERSION)." >&2; exit 1 ;;
esac

# fresh checkout: class_name scripts are only known after an import
[ -f .godot/global_script_class_cache.cfg ] || "$godot" --headless --path . --import >/dev/null 2>&1 || true

args=("--host=${GODOT_LISTEN:-127.0.0.1}" "--port=${GODOT_PORT:-9876}" "--dashboard-url=http://localhost:${DASHBOARD_PORT:-8000}")
for pair in WORLD_WIDTH:world-width WORLD_HEIGHT:world-height DAY_TICKS:day-ticks \
            FLIGHT_SPEED_FACTOR:flight-speed-factor SWARM_SPEED_MPS:swarm-speed-mps SWARM_CLUSTER_DAYS:swarm-cluster-days; do
  var="${pair%%:*}"
  if [ -n "${!var:-}" ]; then args+=("--${pair#*:}=${!var}"); fi
done
display=()
if [ "${GODOT_DISPLAY:-window}" = "headless" ]; then display=(--headless); fi

echo "Godot $version (${GODOT_DISPLAY:-window}) sur ${GODOT_LISTEN:-127.0.0.1}:${GODOT_PORT:-9876}"
exec "$godot" ${display[@]+"${display[@]}"} --path . -- "${args[@]}"
