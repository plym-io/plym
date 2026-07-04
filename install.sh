#!/bin/sh
set -e

IMAGE="${PLYM_IMAGE:-plymio/plym:latest}"
INSTALL_DIR="${PLYM_DIR:-plym}"
INSTALL_URL="${PLYM_INSTALL_URL:-https://raw.githubusercontent.com/plym-io/plym/main/install.sh}"
VERBOSE="${PLYM_VERBOSE:-0}"
REINSTALL_AVAILABLE=""

BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
ACCENT=$(printf '\033[38;5;208m')
RESET=$(printf '\033[0m')
say()  { printf "%s→%s %s\n" "$ACCENT" "$RESET" "$1"; }
note() { printf "%s%s%s\n" "$DIM" "$1" "$RESET"; }
fail() { printf "%s✗%s %s\n" "$ACCENT" "$RESET" "$1" >&2; exit "${2:-1}"; }

on_exit() {
    code=$?
    trap - EXIT
    [ "$code" -eq 0 ] && exit 0
    printf "\n%s✗%s Installation failed (exit %s) — the actual error is shown above.\n" "$ACCENT" "$RESET" "$code" >&2
    if [ -n "$REINSTALL_AVAILABLE" ]; then
        printf "  Wipe this attempt and reinstall:  %splym reinstall%s\n" "$BOLD" "$RESET" >&2
    else
        printf "  Fix the problem above, then run the installer again.\n" >&2
    fi
    [ "$VERBOSE" = "1" ] || printf "  Re-run with %s--verbose%s (or PLYM_VERBOSE=1) to stream the full logs.\n" "$BOLD" "$RESET" >&2
    exit "$code"
}
trap on_exit EXIT

install_cli() {
    PATH_NOTE=""
    CLI_TARGET="/usr/local/bin/plym"
    CLI_DIR="/usr/local/bin"
    if [ ! -w "$CLI_DIR" ] && [ "$(id -u)" != 0 ]; then
        mkdir -p "$HOME/.local/bin"
        CLI_DIR="$HOME/.local/bin"
        CLI_TARGET="$CLI_DIR/plym"
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) : ;;
            *) PATH_NOTE="  ${DIM}Add this to your shell profile to use 'plym' globally:${RESET}
    ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}
" ;;
        esac
    fi
    cp "$(pwd)/bin/plym" "$CLI_DIR/plym" && chmod +x "$CLI_DIR/plym"
    cp "$(pwd)/bin/plym-lib.sh" "$CLI_DIR/plym-lib.sh" && chmod +x "$CLI_DIR/plym-lib.sh"
    CLI_INSTALLED_AT="$CLI_TARGET"
}

project_exists() {
    if [ -n "$(docker ps -a -q --filter "label=com.docker.compose.project=$1" 2>/dev/null)" ]; then
        return 0
    fi
    if docker volume ls -q 2>/dev/null | grep -q "^$1_"; then
        return 0
    fi
    return 1
}

while [ $# -gt 0 ]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; export PLYM_VERBOSE=1; shift ;;
        --) shift; break ;;
        -*) fail "Unknown option: $1 (supported: --verbose)" ;;
        *) break ;;
    esac
done

NAME="$1"
if [ -z "$NAME" ] && [ -e /dev/tty ]; then
    printf "%sName your blog%s " "$BOLD" "$RESET" > /dev/tty
    read NAME < /dev/tty || true
fi
[ -z "$NAME" ] && fail "Blog name is required. Try: curl … | sh -s \"My Blog\""

ADMIN_EMAIL="$2"
if [ -z "$ADMIN_EMAIL" ] && [ -e /dev/tty ]; then
    printf "%sAdmin email%s %s(root@plym.local)%s " "$BOLD" "$RESET" "$DIM" "$RESET" > /dev/tty
    read ADMIN_EMAIL < /dev/tty || true
fi
[ -z "$ADMIN_EMAIL" ] && ADMIN_EMAIL="root@plym.local"

note "Logo, colors and other settings live in config.yaml — change them anytime."

for tool in docker openssl curl; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required and not in PATH"
done
docker compose version >/dev/null 2>&1 || fail "docker compose v2 is required"

if ! docker info >/dev/null 2>&1; then
    fail "Cannot connect to the Docker daemon.

  Common fixes:
    macOS  -  open -a Docker, wait for it to start, then re-run.
    Linux  -  sudo systemctl start docker
              For permission errors, add your user to the docker group:
                sudo usermod -aG docker \$USER
              Then log out and log back in. Or re-run this installer with sudo."
fi

[ -e "$INSTALL_DIR" ] && fail "Directory '$INSTALL_DIR' already exists. Remove it or set PLYM_DIR=somewhere-else"

say "Pulling plym from Docker Hub ($IMAGE)"
if ! docker pull "$IMAGE"; then
    docker image inspect "$IMAGE" >/dev/null 2>&1 \
        || fail "Could not pull $IMAGE — see the docker output above."
    note "Pull failed — using the local copy of $IMAGE."
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
CID=$(docker create "$IMAGE") || fail "Could not create a container from $IMAGE."
if ! docker cp "$CID:/opt/plym/dist/." .; then
    docker rm -f "$CID" >/dev/null 2>&1 || true
    fail "Could not extract the plym files from $IMAGE — is this a plym image?"
fi
docker rm -f "$CID" >/dev/null 2>&1 || true

# From here on, use the shared library (identical to the plym CLI's helpers).
. "$(pwd)/bin/plym-lib.sh"
HEALTH_TIMEOUT_SECONDS=120   # first boot pulls postgres/caddy and runs migrations — give it room

install_cli
PLYM_HOME="${PLYM_CONFIG_HOME:-$HOME/.config/plym}"
mkdir -p "$PLYM_HOME"
pwd > "$PLYM_HOME/active"
REINSTALL_AVAILABLE=1

PORT="${PLYM_PORT:-9173}"
while port_in_use "$PORT"; do
    PORT=$((PORT + 1))
done
BASE_URL="http://localhost:$PORT"

SLUG=$(printf '%s' "$NAME" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-*//;s/-*$//')
[ -n "$SLUG" ] || SLUG=blog
PROJECT_NAME="plym-$SLUG"
if project_exists "$PROJECT_NAME"; then
    PROJECT_NAME="plym-$SLUG-$(openssl rand -hex 3)"
fi

JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')
ADMIN_PASSWORD=$(openssl rand -hex 12 | tr -d '\n')

cp .env.example .env
printf 'COMPOSE_PROJECT_NAME=%s\n' "$PROJECT_NAME" >> .env
sed -i.bak "s|^PLYM_PORT=.*|PLYM_PORT=$PORT|" .env
sed -i.bak "s|^PLYM_JWT_SECRET=.*|PLYM_JWT_SECRET=$JWT_SECRET|" .env
sed -i.bak "s|^PLYM_SUPERUSER_EMAIL=.*|PLYM_SUPERUSER_EMAIL=$ADMIN_EMAIL|" .env
sed -i.bak "s|^PLYM_SUPERUSER_PASSWORD=.*|PLYM_SUPERUSER_PASSWORD=$ADMIN_PASSWORD|" .env
sed -i.bak "s|^PLYM_DB_PASSWORD=.*|PLYM_DB_PASSWORD=$ADMIN_PASSWORD|" .env
rm -f .env.bak
if [ -n "${PLYM_IMAGE:-}" ]; then
    printf 'PLYM_IMAGE=%s\n' "$PLYM_IMAGE" >> .env
fi

cp config.yaml.example config.yaml
sed -i.bak "s|^name:.*|name: $NAME|" config.yaml
rm -f config.yaml.bak

# Admin bundle lives in a bind-mounted ./admin dir, populated here before the stack starts.
# A miss is non-fatal (the app runs without admin until 'plym admin update' succeeds) and loud.
ADMIN_VERSION=$(grep '^PLYM_ADMIN_VERSION=' .env 2>/dev/null | cut -d= -f2- | head -1)
mkdir -p admin
fetch_admin "$ADMIN_VERSION" "$(pwd)/admin" || true

spin "Starting containers — first run downloads postgres and caddy" docker compose up -d \
    || fail "docker compose failed (see message above)."

spin "Starting plym" wait_for_health \
    || fail "App did not come up (see the api logs above)."

seed_welcome() {
    http POST "$BASE_URL/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" || {
            printf 'Login failed for %s (HTTP %s):\n' "$ADMIN_EMAIL" "$HTTP_CODE"
            [ -n "$HTTP_BODY" ] && printf '%s\n' "$HTTP_BODY"
            printf '\nA leftover database volume may still hold an old password — run "docker compose down -v" and reinstall.\n\n'
            dump_service api
            return 1
        }
    token=$(printf '%s' "$HTTP_BODY" | grep -o '"access_token":"[^"]*"' | sed 's/^"access_token":"//;s/"$//')
    [ -n "$token" ] || { printf 'Login returned no access token:\n%s\n' "$HTTP_BODY"; return 1; }

    excerpt="plym is now live on your server. Check out this article to help you complete your setup."
    exec_err=$(mktemp)
    payload=$(
        { [ -f docs/HELLO.md ] && cat docs/HELLO.md \
            || printf '# Welcome\n\n**%s** is live. Open the admin dashboard to edit this post.\n' "$NAME"; } \
        | docker compose exec -T api python3 -c '
import json, sys
name, excerpt = sys.argv[1], sys.argv[2]
print(json.dumps({"title": f"Hello from {name}", "slug": "hello", "content": sys.stdin.read(), "excerpt": excerpt}))
' "$NAME" "$excerpt" 2>"$exec_err"
    )
    if [ -z "$payload" ]; then
        printf "Could not build the welcome post — 'docker compose exec api' failed:\n"
        [ -s "$exec_err" ] && cat "$exec_err"
        rm -f "$exec_err"
        return 1
    fi
    rm -f "$exec_err"

    http POST "$BASE_URL/api/posts" \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d "$payload" || {
            printf 'Could not create the welcome post (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
            return 1
        }
    post_id=$(printf '%s' "$HTTP_BODY" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
    [ -n "$post_id" ] || { printf 'Welcome post had no id:\n%s\n' "$HTTP_BODY"; return 1; }

    http PATCH "$BASE_URL/api/posts/$post_id" \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d '{"status":"published"}' || {
            printf 'Publishing the post failed (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
            return 1
        }

    http POST "$BASE_URL/api/posts/$post_id/refresh" -H "Authorization: Bearer $token" || {
        printf 'Rendering the post failed (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
        return 1
    }
}
spin "Publishing your first post" seed_welcome \
    || fail "Could not seed the welcome post (see message above)."

cat > .plym-credentials <<EOF
plym admin credentials for "$NAME"
─────────────────────────────────
Email:    $ADMIN_EMAIL
Password: $ADMIN_PASSWORD
EOF
chmod 600 .plym-credentials

cat <<EOF

  ${ACCENT}${BOLD}plym${RESET} is live.

  ${BOLD}$NAME${RESET}
  ${DIM}────────────────────────────────────────${RESET}
  Blog       ${ACCENT}$BASE_URL${RESET}
  Admin      ${ACCENT}$BASE_URL/blog/plym-admin${RESET}
  API docs   ${ACCENT}$BASE_URL/docs${RESET}
  Hello post ${ACCENT}$BASE_URL/blog/hello${RESET}

  Sign in:
    Email      ${BOLD}$ADMIN_EMAIL${RESET}
    Password   ${BOLD}$ADMIN_PASSWORD${RESET}

  ${DIM}Credentials saved to $(pwd)/.plym-credentials${RESET}

  ${BOLD}plym${RESET} CLI installed to ${ACCENT}$CLI_INSTALLED_AT${RESET} ${DIM}(this blog is now active)${RESET}
${PATH_NOTE}    ${BOLD}plym list${RESET}                      — show every blog on this machine
    ${BOLD}plym use <name>${RESET}                — switch which blog plym targets
    ${BOLD}plym set url <url> --nginx${RESET}     — serve this blog on your domain (also --caddy, --traefik)
    ${BOLD}plym template install <name>${RESET}   — fetch a template from plym-io/plym-templates
    ${BOLD}plym rebuild${RESET}                   — restart the api and re-render every published post

  ${DIM}plym --verbose update  •  docker compose logs -f api  •  docker compose down${RESET}

EOF
