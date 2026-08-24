#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

fail() {
  echo "Blue Me: $*" >&2
  exit 1
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1"
  else
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$(( $1 * 2 ))"
  fi
}

safe_slug() {
  local value
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//')"
  printf '%s' "${value:-business}"
}

configure() {
  [[ -t 0 ]] || fail "Interactive configuration needs a terminal. Copy .env.example to .env for unattended setup."
  local business slug app_name tagline primary logo web_port root_username root_password
  local database_mode database_host database_port database_name database_user database_password
  local container_database_host compose_profiles mysql_root_password existing_mysql
  read -r -p "Business name [Blue Me Demo]: " business
  business="${business:-Blue Me Demo}"
  read -r -p "Deployment ID [$(safe_slug "$business")]: " slug
  slug="$(safe_slug "${slug:-$business}")"
  read -r -p "Application name [Blue Me]: " app_name
  app_name="${app_name:-Blue Me}"
  read -r -p "Brand tagline [مدیریت شفاف، تصمیم‌گیری هوشمند]: " tagline
  tagline="${tagline:-مدیریت شفاف، تصمیم‌گیری هوشمند}"
  read -r -p "Primary colour [#2563eb]: " primary
  primary="${primary:-#2563eb}"
  read -r -p "Logo URL or /brand/logo.png [none]: " logo
  read -r -p "Public web port [3100]: " web_port
  web_port="${web_port:-3100}"
  read -r -p "Root username [root]: " root_username
  root_username="${root_username:-root}"
  read -r -s -p "Root password (12+ characters; blank generates one): " root_password
  echo
  if [[ -z "$root_password" ]]; then
    root_password="$(random_secret 10)"
    echo "Generated root password: $root_password"
    echo "Store it securely; this script will not print it again."
  fi
  [[ ${#root_password} -ge 12 ]] || fail "Root password must contain at least 12 characters."
  [[ "$web_port" =~ ^[0-9]+$ ]] && (( web_port >= 1 && web_port <= 65535 )) || fail "Web port must be between 1 and 65535."
  [[ "$primary" =~ ^#[0-9A-Fa-f]{6}$ ]] || fail "Primary colour must use #RRGGBB format."

  read -r -p "Use an existing MySQL server? [y/N]: " existing_mysql
  if [[ "$existing_mysql" =~ ^[Yy]$ ]]; then
    database_mode="external"
    compose_profiles=""
    read -r -p "MySQL host [localhost]: " database_host
    database_host="${database_host:-localhost}"
    read -r -p "MySQL port [3306]: " database_port
    database_port="${database_port:-3306}"
    read -r -p "Database name [blue_me]: " database_name
    database_name="${database_name:-blue_me}"
    read -r -p "MySQL user: " database_user
    [[ -n "$database_user" ]] || fail "MySQL user is required."
    read -r -s -p "MySQL password: " database_password
    echo
    [[ -n "$database_password" ]] || fail "MySQL password is required."
    container_database_host="$database_host"
    if [[ "$database_host" == "localhost" || "$database_host" == "127.0.0.1" ]]; then
      container_database_host="host.docker.internal"
    fi
    mysql_root_password="unused-for-external-mysql"
  else
    database_mode="managed"
    compose_profiles="managed-db"
    database_host="localhost"
    container_database_host="db"
    database_port="3306"
    database_name="blue_me"
    database_user="blue_me"
    database_password="$(random_secret 24)"
    mysql_root_password="$(random_secret 24)"
  fi

  if [[ -f "$ENV_FILE" ]]; then
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date -u +%Y%m%d%H%M%S)"
    echo "Backed up the previous .env before reconfiguration."
  fi

  umask 077
  cat >"$ENV_FILE" <<EOF
COMPOSE_PROJECT_NAME=blue-me-$slug
COMPOSE_PROFILES=$compose_profiles
APP_NAME=$app_name
BUSINESS_NAME=$business
BRAND_TAGLINE=$tagline
BRAND_PRIMARY_COLOR=$primary
BRAND_LOGO_URL=$logo
APP_LOCALE=fa
APP_TIMEZONE=UTC
CURRENCY_LABEL=تومان
APP_ENV=production
APP_SECRET_KEY=$(random_secret 32)
ACCESS_TOKEN_MINUTES=480
API_HOST=0.0.0.0
API_PORT=8100
API_WORKERS=2
WEB_PORT=$web_port
UPLOAD_DIR=$PROJECT_DIR/uploads
MAX_UPLOAD_MB=5
DATABASE_MODE=$database_mode
DATABASE_HOST=$database_host
CONTAINER_DATABASE_HOST=$container_database_host
DATABASE_PORT=$database_port
DATABASE_NAME=$database_name
DATABASE_USER=$database_user
DATABASE_PASSWORD=$database_password
MYSQL_ROOT_PASSWORD=$mysql_root_password
ROOT_USERNAME=$root_username
ROOT_PASSWORD=$root_password
ROOT_FULL_NAME=Root Administrator
VITE_API_BASE_URL=/api
EOF
  chmod 600 "$ENV_FILE"
}

check_configuration() {
  [[ -f "$ENV_FILE" ]] || configure
  if grep -Eq '^(APP_SECRET_KEY|DATABASE_PASSWORD|MYSQL_ROOT_PASSWORD|ROOT_PASSWORD)=replace-' "$ENV_FILE"; then
    fail ".env still contains example passwords. Run ./start.sh --configure."
  fi
  local root_password
  root_password="$(sed -n 's/^ROOT_PASSWORD=//p' "$ENV_FILE" | tail -n 1)"
  [[ ${#root_password} -ge 12 ]] || fail "ROOT_PASSWORD in .env must contain at least 12 characters."
}

cd "$PROJECT_DIR"

has_compose() {
  command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1
}

native_service_name() {
  local value
  value="$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' "$ENV_FILE" | tail -n 1)"
  value="${value:-blue-me-local}"
  printf '%s.service' "$(printf '%s' "$value" | tr -cs 'A-Za-z0-9_.@-' '-')"
}

native_systemctl() {
  if [[ -f "$PROJECT_DIR/.systemd-scope" ]] && grep -q '^system$' "$PROJECT_DIR/.systemd-scope"; then
    systemctl "$@"
  else
    systemctl --user "$@"
  fi
}

case "${1:-start}" in
  --configure)
    configure
    ;;
  --stop)
    [[ -f "$ENV_FILE" ]] || fail "No .env exists for this deployment."
    if has_compose; then
      docker compose down
    else
      native_systemctl stop "$(native_service_name)"
    fi
    echo "Blue Me services stopped. Database data and uploads were preserved."
    exit 0
    ;;
  --status)
    [[ -f "$ENV_FILE" ]] || fail "No .env exists for this deployment."
    if has_compose; then docker compose ps; else native_systemctl status "$(native_service_name)" --no-pager; fi
    exit 0
    ;;
  --logs)
    [[ -f "$ENV_FILE" ]] || fail "No .env exists for this deployment."
    if has_compose; then docker compose logs --tail=200 -f; elif [[ -f "$PROJECT_DIR/.systemd-scope" ]] && grep -q '^system$' "$PROJECT_DIR/.systemd-scope"; then journalctl -u "$(native_service_name)" -n 200 -f; else journalctl --user-unit "$(native_service_name)" -n 200 -f; fi
    exit 0
    ;;
  start) ;;
  *) fail "Usage: ./start.sh [--configure|--stop|--status|--logs]" ;;
esac

check_configuration
if ! has_compose; then
  exec "$PROJECT_DIR/scripts/install-systemd.sh"
fi

echo "Building and starting database, API, and web services…"
docker compose up -d --build --remove-orphans

web_port="$(sed -n 's/^WEB_PORT=//p' "$ENV_FILE" | tail -n 1)"
web_port="${web_port:-3100}"
echo "Waiting for the deployment health check…"
healthy=0
for attempt in $(seq 1 60); do
  if curl --fail --silent --max-time 3 "http://127.0.0.1:$web_port/api/ready" >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "$healthy" != 1 ]]; then
  docker compose ps
  docker compose logs --tail=80 api web db
  fail "Services started but did not become healthy in time."
fi

echo
echo "Blue Me is ready: http://127.0.0.1:$web_port"
echo "The services use restart=unless-stopped and return automatically with the Docker daemon."
echo "Use './start.sh --status' for status and './start.sh --logs' for live logs."
