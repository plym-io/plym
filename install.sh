#!/bin/sh
set -e

REPO_URL="${PLYM_REPO_URL:-https://github.com/plym-io/plym.git}"
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
fail() { printf "%s✗%s %s\n" "$ACCENT" "$RESET" "$1" >&2; exit 1; }

on_exit() {
    code=$?
    trap - EXIT
    [ "$code" -eq 0 ] && exit 0
    printf "\n%s✗%s Installation failed (exit %s) — the actual error is shown above.\n" "$ACCENT" "$RESET" "$code" >&2
    if [ -n "$REINSTALL_AVAILABLE" ]; then
        printf "  Wipe this attempt and reinstall from source:  %splym reinstall%s\n" "$BOLD" "$RESET" >&2
    else
        printf "  Fix the problem above, then run the installer again.\n" >&2
    fi
    [ "$VERBOSE" = "1" ] || printf "  Re-run with %sPLYM_VERBOSE=1%s to stream the full logs.\n" "$BOLD" "$RESET" >&2
    exit "$code"
}
trap on_exit EXIT

[ -e /dev/tty ] && SPIN_OUT=/dev/tty || SPIN_OUT=/dev/stdout
spin() {
    msg="$1"; shift
    if [ "$VERBOSE" = "1" ]; then
        printf "%s→%s %s\n" "$ACCENT" "$RESET" "$msg"
        "$@"
        return $?
    fi
    log=$(mktemp)
    "$@" >"$log" 2>&1 &
    pid=$!
    while kill -0 "$pid" 2>/dev/null; do
        for frame in ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏; do
            kill -0 "$pid" 2>/dev/null || break
            printf "\r%s%s%s %s " "$ACCENT" "$frame" "$RESET" "$msg" > "$SPIN_OUT"
            sleep 0.08
        done
    done
    rc=0; wait "$pid" || rc=$?
    if [ "$rc" -eq 0 ]; then
        printf "\r%s✓%s %s\n" "$ACCENT" "$RESET" "$msg" > "$SPIN_OUT"
    else
        printf "\r%s✗%s %s\n" "$ACCENT" "$RESET" "$msg" > "$SPIN_OUT"
        if [ -s "$log" ]; then cat "$log" >&2
        else printf "  (the command produced no output — re-run with PLYM_VERBOSE=1 for live logs)\n" >&2; fi
    fi
    rm -f "$log"
    return "$rc"
}

install_cli() {
    PATH_NOTE=""
    CLI_TARGET="/usr/local/bin/plym"
    if [ -w "$(dirname "$CLI_TARGET")" ] || [ "$(id -u)" = 0 ]; then
        ln -sf "$(pwd)/bin/plym" "$CLI_TARGET"
        CLI_INSTALLED_AT="$CLI_TARGET"
    else
        mkdir -p "$HOME/.local/bin"
        CLI_TARGET="$HOME/.local/bin/plym"
        ln -sf "$(pwd)/bin/plym" "$CLI_TARGET"
        CLI_INSTALLED_AT="$CLI_TARGET"
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) : ;;
            *) PATH_NOTE="  ${DIM}Add this to your shell profile to use 'plym' globally:${RESET}
    ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}
" ;;
        esac
    fi
}

port_in_use() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    elif command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$1" >/dev/null 2>&1
    else
        return 1
    fi
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
        -v|--verbose) VERBOSE=1; shift ;;
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

for tool in docker git openssl curl; do
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

spin "Fetching plym" git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR" \
    || fail "Could not clone $REPO_URL (see output above)."
cd "$INSTALL_DIR"

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
rm -f .env.bak

cp config.yaml.example config.yaml
sed -i.bak "s|^name:.*|name: $NAME|" config.yaml
rm -f config.yaml.bak

spin "Building images — first run takes about a minute" docker compose up -d --build \
    || fail "docker compose failed (see message above)."

wait_for_app() {
    tries=0
    until curl -fsS $BASE_URL/health >/dev/null 2>&1; do
        tries=$((tries + 1))
        [ "$tries" -gt 120 ] && { docker compose logs api 2>&1 | tail -20; return 1; }
        sleep 1
    done
}
spin "Starting plym" wait_for_app \
    || fail "App did not come up within 120 seconds (last log lines above)."

api_call() {
    method="$1"; path="$2"; shift 2
    RESP=$(curl -sS -w '\n%{http_code}' -X "$method" "$BASE_URL$path" "$@" 2>&1)
    CODE=$(printf '%s\n' "$RESP" | tail -n1)
    BODY=$(printf '%s\n' "$RESP" | sed '$d')
}

api_ok() {
    case "$CODE" in 2*) return 0 ;; *) return 1 ;; esac
}

show_request_error() {
    case "${CODE:-}" in
        ""|000) echo "  could not reach $BASE_URL — is the api container running?" >&2 ;;
        *)      echo "  server returned HTTP $CODE" >&2 ;;
    esac
    [ -n "$BODY" ] && printf '%s\n' "$BODY" | sed 's/^/  /' >&2
    return 0
}

seed_welcome() {
    api_call POST /api/auth/login \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}"
    token=$(printf '%s' "$BODY" | grep -o '"access_token":"[^"]*"' | sed 's/^"access_token":"//;s/"$//')
    [ -z "$token" ] && {
        echo "Login failed for $ADMIN_EMAIL." >&2
        show_request_error
        echo "  A leftover database volume may still hold an old password — run 'docker compose down -v' and reinstall." >&2
        return 1
    }

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
        echo "Could not build the welcome post — 'docker compose exec api' failed:" >&2
        [ -s "$exec_err" ] && sed 's/^/  /' "$exec_err" >&2
        rm -f "$exec_err"
        return 1
    fi
    rm -f "$exec_err"

    api_call POST /api/posts \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d "$payload"
    post_id=$(printf '%s' "$BODY" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
    [ -z "$post_id" ] && {
        echo "Could not create the welcome post." >&2
        show_request_error
        return 1
    }

    api_call PATCH "/api/posts/$post_id" \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d '{"status":"published"}'
    api_ok || {
        echo "Publishing the post failed (PATCH /api/posts/$post_id)." >&2
        show_request_error
        return 1
    }

    api_call POST "/api/posts/$post_id/refresh" -H "Authorization: Bearer $token"
    api_ok || {
        echo "Rendering the post failed (POST /api/posts/$post_id/refresh)." >&2
        show_request_error
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

  ${DIM}docker compose logs -f api  •  docker compose down${RESET}

EOF
