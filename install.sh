#!/bin/sh
# plym one-line installer
#   curl -fsSL https://raw.githubusercontent.com/plym-io/plym/main/install.sh | sh
#   curl -fsSL https://raw.githubusercontent.com/plym-io/plym/main/install.sh | sh -s "My Blog"

set -e

REPO_URL="${PLYM_REPO_URL:-https://github.com/plym-io/plym.git}"
INSTALL_DIR="${PLYM_DIR:-plym}"

BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
ACCENT=$(printf '\033[38;5;208m')
RESET=$(printf '\033[0m')

say()  { printf "%s→%s %s\n" "$ACCENT" "$RESET" "$1"; }
fail() { printf "%s✗%s %s\n" "$ACCENT" "$RESET" "$1" >&2; exit 1; }

# Blog name — arg or interactive prompt
NAME="$1"
if [ -z "$NAME" ]; then
    if [ -e /dev/tty ]; then
        printf "%sName your blog%s " "$BOLD" "$RESET" > /dev/tty
        read NAME < /dev/tty || true
    fi
fi
[ -z "$NAME" ] && fail "Blog name is required. Try: curl … | sh -s \"My Blog\""

# Prereqs
for tool in docker git openssl curl; do
    command -v "$tool" >/dev/null 2>&1 || fail "$tool is required and not in PATH"
done
docker compose version >/dev/null 2>&1 || fail "docker compose v2 is required"
[ -e "$INSTALL_DIR" ] && fail "Directory '$INSTALL_DIR' already exists. Remove it or set PLYM_DIR=somewhere-else"

say "Fetching plym"
git clone --quiet --depth 1 "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

say "Generating credentials"
JWT_SECRET=$(openssl rand -base64 48 | tr -d '\n')
ADMIN_PASSWORD=$(openssl rand -hex 12 | tr -d '\n')

cp .env.example .env
sed -i.bak "s|^PLYM_JWT_SECRET=.*|PLYM_JWT_SECRET=$JWT_SECRET|" .env
sed -i.bak "s|^PLYM_SUPERUSER_PASSWORD=.*|PLYM_SUPERUSER_PASSWORD=$ADMIN_PASSWORD|" .env
rm -f .env.bak

cp config.yaml.example config.yaml
sed -i.bak "s|^name:.*|name: $NAME|" config.yaml
rm -f config.yaml.bak

say "Building images (first run takes ~1 minute)"
docker compose up -d --build >/dev/null 2>&1

say "Waiting for app to come up"
tries=0
until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 120 ]; then
        printf "\n"
        docker compose logs api 2>&1 | tail -20
        fail "App did not come up within 120 seconds"
    fi
    sleep 1
done

# Seed a welcome post so / isn't empty
say "Creating welcome post"
TOKEN=$(curl -fsS -X POST http://localhost:8000/api/auth/login \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"root@plym.local\",\"password\":\"$ADMIN_PASSWORD\"}" \
    | grep -o '"access_token":"[^"]*"' | sed 's/^"access_token":"//;s/"$//')

WELCOME_CONTENT="# Welcome\n\n**$NAME** is live. This is your first post — open \`/docs\` to edit it or create another."

POST_ID=$(curl -fsS -X POST http://localhost:8000/api/posts \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    -d "{\"title\":\"Hello from $NAME\",\"slug\":\"hello\",\"content\":\"$WELCOME_CONTENT\",\"excerpt\":\"Your blog is up and running.\"}" \
    | grep -o '"id":[0-9]*' | head -1 | sed 's/"id"://')

curl -fsS -X PATCH "http://localhost:8000/api/posts/$POST_ID" \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"status":"published"}' >/dev/null
curl -fsS -X POST "http://localhost:8000/api/posts/$POST_ID/refresh" \
    -H "Authorization: Bearer $TOKEN" >/dev/null

# Save credentials
cat > .plym-credentials <<EOF
plym admin credentials for "$NAME"
─────────────────────────────────
Email:    root@plym.local
Password: $ADMIN_PASSWORD
EOF
chmod 600 .plym-credentials

# Install the CLI symlink (prefer /usr/local/bin when writable, fall back to ~/.local/bin)
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

# Success banner
cat <<EOF

  ${ACCENT}${BOLD}plym${RESET} is live.

  ${BOLD}$NAME${RESET}
  ${DIM}────────────────────────────────────────${RESET}
  Blog       ${ACCENT}http://localhost:8000${RESET}
  API docs   ${ACCENT}http://localhost:8000/docs${RESET}
  Hello post ${ACCENT}http://localhost:8000/blog/hello${RESET}

  Sign in:
    Email      ${BOLD}root@plym.local${RESET}
    Password   ${BOLD}$ADMIN_PASSWORD${RESET}

  ${DIM}Credentials saved to $(pwd)/.plym-credentials${RESET}

  ${BOLD}plym${RESET} CLI installed to ${ACCENT}$CLI_INSTALLED_AT${RESET}
${PATH_NOTE}    ${BOLD}plym template install <name>${RESET} — fetch a template from plym-io/plym-templates
    ${BOLD}plym rebuild${RESET}                   — restart the api and re-render every published post

  ${DIM}docker compose logs -f api  •  docker compose down${RESET}

EOF
