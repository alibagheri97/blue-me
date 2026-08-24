#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
[[ -f "$ENV_FILE" ]] || { echo "Blue Me: missing .env" >&2; exit 1; }

database_mode="$(sed -n 's/^DATABASE_MODE=//p' "$ENV_FILE" | tail -n 1)"
[[ "$database_mode" == "external" ]] || { echo "Blue Me: native systemd mode requires DATABASE_MODE=external" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "Blue Me: python3 is required" >&2; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "Blue Me: Node.js and npm are required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "Blue Me: curl is required" >&2; exit 1; }

deploy_id="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' "$ENV_FILE" | tail -n 1)"
deploy_id="${deploy_id:-blue-me-local}"
deploy_id="$(printf '%s' "$deploy_id" | tr -cs 'A-Za-z0-9_.@-' '-')"
service_name="$deploy_id.service"
run_user="${SUDO_USER:-$USER}"
run_group="$(id -gn "$run_user")"
web_port="$(sed -n 's/^WEB_PORT=//p' "$ENV_FILE" | tail -n 1)"
web_port="${web_port:-3100}"

echo "Installing Python dependencies…"
if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  python3 -m venv "$PROJECT_DIR/.venv"
fi
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"

echo "Building Persian dashboard…"
npm ci --prefix "$PROJECT_DIR/frontend"
npm run build --prefix "$PROJECT_DIR/frontend"
mkdir -p "$PROJECT_DIR/uploads"

echo "Applying database migrations and creating the root account…"
(
  cd "$PROJECT_DIR/backend"
  "$PROJECT_DIR/.venv/bin/dotenv" -f "$ENV_FILE" run -- "$PROJECT_DIR/.venv/bin/alembic" -c alembic.ini upgrade head
  "$PROJECT_DIR/.venv/bin/dotenv" -f "$ENV_FILE" run -- "$PROJECT_DIR/.venv/bin/python" -m app.cli bootstrap
)

unit_header="[Unit]
Description=Blue Me business management ($deploy_id)
After=network-online.target mariadb.service mysqld.service mysql.service
Wants=network-online.target

[Service]
Type=simple"
unit_runtime="WorkingDirectory=$PROJECT_DIR/backend
EnvironmentFile=$ENV_FILE
Environment=UPLOAD_DIR=$PROJECT_DIR/uploads
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn app.deployment:app --host 0.0.0.0 --port $web_port --workers 2 --proxy-headers --forwarded-allow-ips=*
Restart=always
RestartSec=3
TimeoutStopSec=25
NoNewPrivileges=true"
unit_install="
[Install]
WantedBy=default.target"

if [[ "$EUID" -eq 0 ]]; then
  unit_file="/etc/systemd/system/$service_name"
  unit_content="$unit_header
User=$run_user
Group=$run_group
WorkingDirectory=$PROJECT_DIR/backend
EnvironmentFile=$ENV_FILE
Environment=UPLOAD_DIR=$PROJECT_DIR/uploads
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn app.deployment:app --host 0.0.0.0 --port $web_port --workers 2 --proxy-headers --forwarded-allow-ips=*
Restart=always
RestartSec=3
TimeoutStopSec=25
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$PROJECT_DIR/uploads

[Install]
WantedBy=multi-user.target"
  printf '%s\n' "$unit_content" >"$unit_file"
  systemctl daemon-reload
  systemctl enable --now "$service_name"
  printf '%s' "system" >"$PROJECT_DIR/.systemd-scope"
  systemctl_command=(systemctl)
  journal_command=(journalctl -u "$service_name")
else
  unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  unit_file="$unit_dir/$service_name"
  mkdir -p "$unit_dir"
  printf '%s\n' "$unit_header" "$unit_runtime" "$unit_install" >"$unit_file"
  systemctl --user daemon-reload
  systemctl --user enable --now "$service_name"
  printf '%s' "user" >"$PROJECT_DIR/.systemd-scope"
  systemctl_command=(systemctl --user)
  journal_command=(journalctl --user-unit "$service_name")
fi

echo "Waiting for $service_name…"
for attempt in $(seq 1 45); do
  if curl --fail --silent --max-time 3 "http://127.0.0.1:$web_port/api/ready" >/dev/null 2>&1; then
    echo "Blue Me is ready: http://127.0.0.1:$web_port"
    exit 0
  fi
  sleep 2
done

"${systemctl_command[@]}" status "$service_name" --no-pager || true
"${journal_command[@]}" -n 80 --no-pager || true
echo "Blue Me: service did not become healthy" >&2
exit 1
