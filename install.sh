#!/bin/sh
set -e

IMAGE="${PLYM_IMAGE:-plymio/plym:latest}"
INSTALL_DIR="${PLYM_DIR:-plym}"
INSTALL_URL="${PLYM_INSTALL_URL:-https://raw.githubusercontent.com/plym-io/plym/main/install.sh}"
VERBOSE="${PLYM_VERBOSE:-0}"
REINSTALL_AVAILABLE=""

plym_ui() {
    case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
        *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) PLYM_UTF8=1 ;;
        *) PLYM_UTF8=0 ;;
    esac

    if [ -t 2 ] && [ -z "${NO_COLOR+set}" ] && [ "${TERM:-}" != dumb ]; then
        BOLD=$(printf '\033[1m')
        DIM=$(printf '\033[2m')
        RESET=$(printf '\033[0m')
        case "${COLORTERM:-}" in
            truecolor|24bit) ACCENT=$(printf '\033[38;2;244;61;2m') ;;
            *)               ACCENT=$(printf '\033[38;5;202m') ;;
        esac
        GREEN=$(printf '\033[38;5;40m')
        RED=$(printf '\033[38;5;196m')
        YELLOW=$(printf '\033[38;5;214m')
    else
        BOLD=''; DIM=''; RESET=''; ACCENT=''; GREEN=''; RED=''; YELLOW=''
    fi

    if [ "$PLYM_UTF8" = 1 ]; then
        OK_MARK='✓'; ERR_MARK='✗'; SPIN_FRAMES='▖ ▘ ▝ ▗'
    else
        OK_MARK='+'; ERR_MARK='x'; SPIN_FRAMES='| / - \'
    fi

    say()  { printf '%splym:%s %s\n' "$ACCENT" "$RESET" "$1" >&2; }
    warn() { printf '%splym:%s %swarning:%s %s\n' "$ACCENT" "$RESET" "$YELLOW" "$RESET" "$1" >&2; }
    done_() { printf '%splym:%s %s%s%s %s\n' "$ACCENT" "$RESET" "$GREEN" "$OK_MARK" "$RESET" "$1" >&2; }

    detail() {
        _title="$1"
        _body=$(cat)
        [ -n "$_body" ] || return 0
        printf '%splym: %s:%s\n' "$DIM" "$_title" "$RESET" >&2
        printf '%s\n' "$_body" >&2
    }

    fail() {
        _msg="$1"; _code="${2:-1}"
        printf '%splym:%s %serror:%s %s\n' "$ACCENT" "$RESET" "$RED" "$RESET" "$_msg" >&2
        exit "$_code"
    }

    spin() {
        _msg="$1"; shift
        if [ "$VERBOSE" = "1" ]; then
            printf '%splym:%s %s\n' "$ACCENT" "$RESET" "$_msg" >&2
            _rc=0; "$@" || _rc=$?
            [ "$_rc" -eq 0 ] || printf '%splym:%s %serror:%s %s failed (exit %s)\n' "$ACCENT" "$RESET" "$RED" "$RESET" "$_msg" "$_rc" >&2
            return "$_rc"
        fi
        _log=$(mktemp)
        if [ -t 2 ]; then
            "$@" >"$_log" 2>&1 &
            _pid=$!
            while kill -0 "$_pid" 2>/dev/null; do
                for _frame in $SPIN_FRAMES; do
                    kill -0 "$_pid" 2>/dev/null || break
                    printf '\r%splym:%s %s%s%s %s' "$ACCENT" "$RESET" "$ACCENT" "$_frame" "$RESET" "$_msg" >&2
                    sleep 0.08
                done
            done
            _rc=0; wait "$_pid" || _rc=$?
            if [ "$_rc" -eq 0 ]; then
                printf '\r%splym:%s %s%s%s %s\n' "$ACCENT" "$RESET" "$GREEN" "$OK_MARK" "$RESET" "$_msg" >&2
            else
                printf '\r' >&2
            fi
        else
            printf '%splym:%s %s\n' "$ACCENT" "$RESET" "$_msg" >&2
            _rc=0; "$@" >"$_log" 2>&1 || _rc=$?
        fi
        if [ "$_rc" -ne 0 ]; then
            printf '%splym:%s %s%s%s %s failed (exit %s)\n' "$ACCENT" "$RESET" "$RED" "$ERR_MARK" "$RESET" "$_msg" "$_rc" >&2
            if [ -s "$_log" ]; then
                detail "$_msg" < "$_log"
            else
                say "the failed step produced no output; re-run with --verbose for live logs"
            fi
        fi
        rm -f "$_log"
        return "$_rc"
    }

    normalize_prefix() {
        p="$1"
        while [ "${p%/}" != "$p" ]; do p="${p%/}"; done
        case "$p" in ""|/*) ;; *) p="/$p" ;; esac
        printf '%s' "$p"
    }

    port_in_use() {
        if command -v python3 >/dev/null 2>&1; then
            ! python3 -c 'import socket, sys
port = int(sys.argv[1])
def bindable(family, addr):
    try:
        s = socket.socket(family, socket.SOCK_STREAM)
    except OSError:
        return True
    try:
        if family == socket.AF_INET6:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        s.bind((addr, port))
        return True
    except OSError:
        return False
    finally:
        s.close()
free = bindable(socket.AF_INET, "0.0.0.0") and bindable(socket.AF_INET6, "::")
sys.exit(0 if free else 1)' "$1" 2>/dev/null
        elif command -v lsof >/dev/null 2>&1; then
            lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
        elif command -v nc >/dev/null 2>&1; then
            nc -z 127.0.0.1 "$1" >/dev/null 2>&1
        else
            return 1
        fi
    }

    plym_logo() {
        [ "$PLYM_UTF8" = 1 ] || return 0
        printf '%s' "$ACCENT" >&2
        cat <<'LOGO' >&2
         ▄█████████████▄▄▄▄▄▄▄▄▄
         ███████████████████████
        ███████████████████████
       ███████████████████████▀
      ▄███████████████████████
      ███████████████████████
     ███████████████████████
    ▄█████████▀▀ ██████████▀
   ▄███████▀▀  ▄███████████
   █████▀▀  ▄█████████████
  ███▀▀  ▄███████████████▀
  ▀▀  ▄█████████████████▀
    ████████████████████
LOGO
        printf '%s' "$RESET" >&2
    }
}
plym_ui

on_exit() {
    code=$?
    trap - EXIT
    [ "$code" -eq 0 ] && exit 0
    printf '%splym:%s %serror:%s install failed (exit %s); the error is above\n' "$ACCENT" "$RESET" "$RED" "$RESET" "$code" >&2
    if [ -n "$REINSTALL_AVAILABLE" ]; then
        say "wipe this attempt and reinstall: plym reinstall"
    else
        say "fix the problem above, then run the installer again"
    fi
    [ "$VERBOSE" = "1" ] || say "re-run with --verbose (or PLYM_VERBOSE=1) to stream the full logs"
    exit "$code"
}
trap on_exit EXIT

sed_escape()  { printf '%s' "$1" | sed 's/[\\&|]/\\&/g'; }
yaml_scalar() { printf '"%s"' "$(printf '%s' "$1" | sed 's/[\\"]/\\&/g')"; }

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
            *) PATH_NOTE='export PATH="$HOME/.local/bin:$PATH"' ;;
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
        -*) fail "unknown option: $1 (supported: --verbose)" ;;
        *) break ;;
    esac
done

tty_available() { [ -e /dev/tty ] && ( exec 3>/dev/tty ) 2>/dev/null; }

NAME="$1"
if [ -z "$NAME" ] && tty_available; then
    printf 'plym: name your blog: ' > /dev/tty
    read -r NAME < /dev/tty || true
fi
[ -z "$NAME" ] && fail "blog name is required; run: curl -fsSL $INSTALL_URL | sh -s \"My Blog\""

ADMIN_EMAIL="$2"
if [ -z "$ADMIN_EMAIL" ] && tty_available; then
    printf 'plym: admin email [root@plym.local]: ' > /dev/tty
    read -r ADMIN_EMAIL < /dev/tty || true
fi
[ -z "$ADMIN_EMAIL" ] && ADMIN_EMAIL="root@plym.local"

for tool in docker openssl curl; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required and not in PATH"
done
docker compose version >/dev/null 2>&1 || fail "docker compose v2 is required"

if ! docker info >/dev/null 2>&1; then
    fail "cannot connect to the docker daemon

  Common fixes:
    macOS  -  open -a Docker, wait for it to start, then re-run.
    Linux  -  sudo systemctl start docker
              For permission errors, add your user to the docker group:
                sudo usermod -aG docker \$USER
              Then log out and log back in. Or re-run this installer with sudo."
fi

[ -e "$INSTALL_DIR" ] && fail "directory '$INSTALL_DIR' already exists; remove it or set PLYM_DIR=somewhere-else"

say "pulling $IMAGE from Docker Hub"
if ! docker pull "$IMAGE"; then
    docker image inspect "$IMAGE" >/dev/null 2>&1 \
        || fail "could not pull $IMAGE; see the docker output above"
    warn "pull failed; using the local copy of $IMAGE"
fi

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
CID=$(docker create "$IMAGE") || fail "could not create a container from $IMAGE"
if ! docker cp "$CID:/opt/plym/dist/." .; then
    docker rm -f "$CID" >/dev/null 2>&1 || true
    fail "could not extract the plym files from $IMAGE; is this a plym image?"
fi
docker rm -f "$CID" >/dev/null 2>&1 || true

. "$(pwd)/bin/plym-lib.sh"
HEALTH_TIMEOUT_SECONDS=120

plym_ui

BLOG_PREFIX=$(normalize_prefix "$(grep '^blog_prefix:' config.yaml.example 2>/dev/null | awk '{print $2}' | tr -d '"')")

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
DB_PASSWORD=$(openssl rand -hex 24 | tr -d '\n')

cp .env.example .env
chmod 600 .env
printf 'COMPOSE_PROJECT_NAME=%s\n' "$PROJECT_NAME" >> .env
sed -i.bak "s|^PLYM_PORT=.*|PLYM_PORT=$PORT|" .env
sed -i.bak "s|^PLYM_JWT_SECRET=.*|PLYM_JWT_SECRET=$(sed_escape "$JWT_SECRET")|" .env
sed -i.bak "s|^PLYM_SUPERUSER_EMAIL=.*|PLYM_SUPERUSER_EMAIL=$(sed_escape "$ADMIN_EMAIL")|" .env
sed -i.bak "s|^PLYM_SUPERUSER_PASSWORD=.*|PLYM_SUPERUSER_PASSWORD=$ADMIN_PASSWORD|" .env
sed -i.bak "s|^PLYM_DB_PASSWORD=.*|PLYM_DB_PASSWORD=$DB_PASSWORD|" .env
if grep -q '^PLYM_BLOG_PREFIX=' .env; then
    sed -i.bak "s|^PLYM_BLOG_PREFIX=.*|PLYM_BLOG_PREFIX=$(sed_escape "$BLOG_PREFIX")|" .env
else
    printf 'PLYM_BLOG_PREFIX=%s\n' "$BLOG_PREFIX" >> .env
fi
rm -f .env.bak
if [ -n "${PLYM_IMAGE:-}" ]; then
    printf 'PLYM_IMAGE=%s\n' "$PLYM_IMAGE" >> .env
fi

cp config.yaml.example config.yaml
sed -i.bak "s|^name:.*|name: $(sed_escape "$(yaml_scalar "$NAME")")|" config.yaml
sed -i.bak "s|^blog_home:.*|blog_home: $(sed_escape "$(yaml_scalar "$BASE_URL$BLOG_PREFIX")")|" config.yaml
if grep -q '^blog_prefix:' config.yaml; then
    sed -i.bak "s|^blog_prefix:.*|blog_prefix: $(sed_escape "${BLOG_PREFIX:-/}")|" config.yaml
else
    printf 'blog_prefix: %s\n' "${BLOG_PREFIX:-/}" >> config.yaml
fi
rm -f config.yaml.bak
BLOG_URL="$BASE_URL$BLOG_PREFIX"

ADMIN_VERSION=$(grep '^PLYM_ADMIN_VERSION=' .env 2>/dev/null | cut -d= -f2- | head -1)
mkdir -p admin
fetch_admin "$ADMIN_VERSION" "$(pwd)/admin" || true

spin "starting containers (first run pulls postgres and caddy)" docker compose up -d \
    || fail "docker compose failed; see the message above"

spin "waiting for the api to become healthy" wait_for_health \
    || fail "the app did not come up; see the api logs above"

seed_welcome() {
    http POST "$BASE_URL/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" || {
            printf 'login failed for %s (HTTP %s):\n' "$ADMIN_EMAIL" "$HTTP_CODE"
            [ -n "$HTTP_BODY" ] && printf '%s\n' "$HTTP_BODY"
            printf '\na leftover database volume may still hold an old password; run "docker compose down -v" and reinstall\n\n'
            dump_service api
            return 1
        }
    token=$(printf '%s' "$HTTP_BODY" | grep -o '"access_token":"[^"]*"' | sed 's/^"access_token":"//;s/"$//')
    [ -n "$token" ] || { printf 'login returned no access token:\n%s\n' "$HTTP_BODY"; return 1; }

    excerpt="Your instance is live. Here is how to open the dashboard, put it on your own domain, and change how it looks."
    exec_err=$(mktemp)
    payload=$(
        { [ -f docs/HELLO.md ] && cat docs/HELLO.md \
            || printf '# Welcome\n\n**%s** is live. Open the admin dashboard to edit this post.\n' "$NAME"; } \
        | docker compose exec -T api python3 -c '
import json, sys
name, excerpt, admin_path = sys.argv[1], sys.argv[2], sys.argv[3]
content = sys.stdin.read().replace("__ADMIN_PATH__", admin_path)
print(json.dumps({"title": f"Hello from {name}", "slug": "hello", "content": content, "excerpt": excerpt}))
' "$NAME" "$excerpt" "$BLOG_PREFIX/plym-admin" 2>"$exec_err"
    )
    if [ -z "$payload" ]; then
        printf "could not build the welcome post, 'docker compose exec api' failed:\n"
        [ -s "$exec_err" ] && cat "$exec_err"
        rm -f "$exec_err"
        return 1
    fi
    rm -f "$exec_err"

    http POST "$BASE_URL/api/posts" \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d "$payload" || {
            printf 'could not create the welcome post (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
            return 1
        }
    post_id=$(printf '%s' "$HTTP_BODY" | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')
    [ -n "$post_id" ] || { printf 'welcome post had no id:\n%s\n' "$HTTP_BODY"; return 1; }

    http PATCH "$BASE_URL/api/posts/$post_id" \
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
        -d '{"status":"published"}' || {
            printf 'publishing the post failed (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
            return 1
        }

    http POST "$BASE_URL/api/posts/$post_id/refresh" -H "Authorization: Bearer $token" || {
        printf 'rendering the post failed (HTTP %s):\n%s\n' "$HTTP_CODE" "$HTTP_BODY"
        return 1
    }
}
spin "publishing the welcome post" seed_welcome \
    || fail "could not seed the welcome post; see the message above"

CRED_FILE="$(pwd)/.plym-credentials"
cat > "$CRED_FILE" <<EOF
blog_name=$NAME
blog_url=$BLOG_URL
admin_url=$BLOG_URL/plym-admin
admin_email=$ADMIN_EMAIL
admin_password=$ADMIN_PASSWORD
EOF
chmod 600 "$CRED_FILE"

DEBUG_ON=$(grep '^PLYM_DEBUG=' .env 2>/dev/null | cut -d= -f2- | head -1)
DOCS_URL=""
if [ "$DEBUG_ON" = "true" ] && curl -fsS -m 5 "$BASE_URL/plym-docs" >/dev/null 2>&1; then
    DOCS_URL="$BASE_URL/plym-docs"
fi
if [ "$DEBUG_ON" = "true" ]; then
    MODE_LINE="debug ${DIM}(set PLYM_DEBUG=false in .env before going public)${RESET}"
else
    MODE_LINE="production"
fi

if [ "$PLYM_UTF8" = 1 ]; then
    S_TOP='┌'; S_MID='├'; S_BOT='└'; S_BAR='│'; S_RULE='──'
else
    S_TOP='+'; S_MID='+'; S_BOT='+'; S_BAR='|'; S_RULE='--'
fi

sec() { printf '  %s%s%s%s %s%s%s\n' "$ACCENT" "$1" "$S_RULE" "$RESET" "$BOLD" "$2" "$RESET" >&2; }
row() { printf '  %s%s%s %s%-11s%s %s\n' "$ACCENT" "$S_BAR" "$RESET" "$DIM" "$1" "$RESET" "$2" >&2; }

printf '\n' >&2
plym_logo
printf '\n' >&2
printf '  %s%s%s %s%s is live at %s%s\n\n' "$GREEN" "$OK_MARK" "$RESET" "$BOLD" "$NAME" "$BLOG_URL" "$RESET" >&2
sec "$S_TOP" "your blog"
row "home" "$BLOG_URL"
row "admin" "$BLOG_URL/plym-admin"
row "hello post" "$BLOG_URL/hello"
[ -n "$DOCS_URL" ] && row "api docs" "$DOCS_URL"
sec "$S_MID" "sign in"
row "email" "$ADMIN_EMAIL"
row "password" "${BOLD}$ADMIN_PASSWORD${RESET}"
row "saved to" "$CRED_FILE"
sec "$S_MID" "this install"
row "mode" "$MODE_LINE"
row "folder" "$(pwd)"
row "config" "$(pwd)/config.yaml"
row "cli" "$CLI_INSTALLED_AT"
printf '  %s%s%s%s\n\n' "$ACCENT" "$S_BOT" "$S_RULE" "$RESET" >&2
printf '  %snext steps%s\n' "$BOLD" "$RESET" >&2
printf '    1. open %s/plym-admin and change your password\n' "$BLOG_URL" >&2
printf '    2. plym set url <your-domain>  %s# canonical urls, sitemap and llms.txt point at %s until then%s\n' "$DIM" "$BLOG_URL" "$RESET" >&2
printf '    3. edit config.yaml, then: plym reload\n' >&2
printf '    4. plym help\n' >&2
[ -n "$PATH_NOTE" ] && printf '\n' >&2 && say "add this to your shell profile to run 'plym' from anywhere: $PATH_NOTE"
printf '\n' >&2
say "$(basename "$(pwd)") is now the active blog"
