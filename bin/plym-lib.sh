: "${PLYM_VERBOSE:=0}"
: "${VERBOSE:=$PLYM_VERBOSE}"
: "${HEALTH_TIMEOUT_SECONDS:=60}"
: "${PLYM_LOG_TAIL:=200}"
: "${PLYM_ADMIN_URL:=https://github.com/plym-io/plym-admin/releases/download}"
: "${PLYM_DEFAULT_IMAGE:=plymio/plym:latest}"

if [ -t 2 ]; then PLYM_TTY=1; else PLYM_TTY=0; fi

case "${LC_ALL:-${LC_CTYPE:-${LANG:-}}}" in
    *[Uu][Tt][Ff]-8* | *[Uu][Tt][Ff]8*) PLYM_UTF8=1 ;;
    *) PLYM_UTF8=0 ;;
esac

BOLD=''
DIM=''
ACCENT=''
GREEN=''
RED=''
YELLOW=''
RESET=''
if [ "$PLYM_TTY" = 1 ] && [ -z "${NO_COLOR+set}" ] && [ "${TERM:-}" != dumb ]; then
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
fi

if [ "$PLYM_UTF8" = 1 ]; then
    OK_MARK='✓'
    ERR_MARK='✗'
    SPIN_FRAMES='▖ ▘ ▝ ▗'
else
    OK_MARK='+'
    ERR_MARK='x'
    SPIN_FRAMES='| / - \'
fi

tty_available() { [ -e /dev/tty ] && ( exec 3>/dev/tty ) 2>/dev/null; }

say()  { printf '%splym:%s %s\n' "$ACCENT" "$RESET" "$1" >&2; }
warn() { printf '%splym:%s %swarning:%s %s\n' "$ACCENT" "$RESET" "$YELLOW" "$RESET" "$1" >&2; }
done_() { printf '%splym:%s %s%s%s %s\n' "$ACCENT" "$RESET" "$GREEN" "$OK_MARK" "$RESET" "$1" >&2; }

normalize_prefix() {
    p="$1"
    while [ "${p%/}" != "$p" ]; do p="${p%/}"; done
    case "$p" in ""|/*) ;; *) p="/$p" ;; esac
    printf '%s' "$p"
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

detail() {
    _title="$1"
    _body=$(cat)
    [ -n "$_body" ] || return 0
    printf '%splym: %s:%s\n' "$DIM" "$_title" "$RESET" >&2
    printf '%s\n' "$_body" >&2
}

fail() {
    _msg="$1"; _code="${2:-1}"; _ctx="${3:-$PLYM_CONTEXT}"
    printf '%splym:%s %serror:%s %s\n' "$ACCENT" "$RESET" "$RED" "$RESET" "$_msg" >&2
    [ -n "$_ctx" ] && printf '%s\n' "$_ctx" | detail details
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
    if [ "$PLYM_TTY" = 1 ]; then
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

retry() {
    _attempts="$1"; shift
    _n=1
    while :; do
        "$@" && return 0
        [ "$_n" -ge "$_attempts" ] && return 1
        _n=$((_n + 1))
        sleep 1
    done
}
http() {
    _method="$1"; _url="$2"; shift 2
    _resp=$(curl -sS -m 30 -w '\n%{http_code}' -X "$_method" "$_url" "$@" 2>&1)
    HTTP_CODE=$(printf '%s\n' "$_resp" | tail -n1)
    HTTP_BODY=$(printf '%s\n' "$_resp" | sed '$d')
    case "$HTTP_CODE" in '' | *[!0-9]*) HTTP_CODE=000 ;; esac
    if [ "$VERBOSE" = "1" ]; then
        printf 'plym: %s %s (HTTP %s)\n' "$_method" "$_url" "$HTTP_CODE" >&2
        [ -n "$HTTP_BODY" ] && printf '%s\n' "$HTTP_BODY" | detail "response $HTTP_CODE"
    fi
    case "$HTTP_CODE" in 2*) return 0 ;; *) return 1 ;; esac
}

plym_image() {
    _img=$(grep '^PLYM_IMAGE=' .env 2>/dev/null | cut -d= -f2- | head -1)
    printf '%s' "${_img:-$PLYM_DEFAULT_IMAGE}"
}

image_id() { docker image inspect -f '{{.Id}}' "$1" 2>/dev/null; }

extract_dist() {
    _img="$1"; _dest="$2"
    _cid=$(docker create "$_img") || return 1
    if docker cp "$_cid:/opt/plym/dist/." "$_dest"; then
        docker rm -f "$_cid" >/dev/null 2>&1 || true
        return 0
    fi
    docker rm -f "$_cid" >/dev/null 2>&1 || true
    return 1
}

seed_bundled_templates() {
    _img="$1"; _dest="$2"
    mkdir -p "$_dest" || return 1
    _cid=$(docker create "$_img") || return 1
    if docker cp "$_cid:/app/plym/templates/." "$_dest"; then
        docker rm -f "$_cid" >/dev/null 2>&1 || true
        return 0
    fi
    docker rm -f "$_cid" >/dev/null 2>&1 || true
    return 1
}

svc_cid()   { docker compose ps -aq "$1" 2>/dev/null | head -1; }
svc_state() { _c=$(svc_cid "$1"); [ -n "$_c" ] && docker inspect -f '{{.State.Status}}' "$_c" 2>/dev/null; }
svc_diag()  {
    _c=$(svc_cid "$1")
    [ -n "$_c" ] || { printf 'no container'; return; }
    docker inspect -f 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' "$_c" 2>/dev/null
}

dump_service() {
    printf '%s: %s\n\n' "$1" "$(svc_diag "$1")" >&2
    { docker compose logs --tail "$PLYM_LOG_TAIL" "$1" 2>&1; } >&2
}

dump_unhealthy() {
    for _s in api caddy db; do
        case "$(svc_state "$_s")" in
            running | '') : ;;
            *) printf '\n' >&2; dump_service "$_s" ;;
        esac
    done
}

wait_for_health() {
    _tries=0
    while ! curl -fsS -m 5 "$BASE_URL/health" >/dev/null 2>&1; do
        case "$(svc_state api)" in
            exited | dead)
                printf 'the api container exited during startup, not a graceful shutdown (%s)\n\n' "$(svc_diag api)" >&2
                dump_service api
                dump_unhealthy
                return 1 ;;
        esac
        _tries=$((_tries + 1))
        if [ "$_tries" -gt "$HEALTH_TIMEOUT_SECONDS" ]; then
            printf 'no answer from %s/health within %ss; the container is up but not serving (%s)\n\n' \
                "$BASE_URL" "$HEALTH_TIMEOUT_SECONDS" "$(svc_diag api)" >&2
            dump_service api
            dump_unhealthy
            return 1
        fi
        sleep 1
    done
    if [ "$VERBOSE" = "1" ]; then
        say "api is healthy; recent api logs:"
        { docker compose logs --tail "$PLYM_LOG_TAIL" api 2>&1; } >&2
    fi
    return 0
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

fetch_admin() {
    _ver="$1"; _dest="$2"
    [ -n "$_ver" ] || { warn "no admin version configured; skipping the admin fetch"; return 0; }
    _url="$PLYM_ADMIN_URL/$_ver/dist.tar.gz"
    _had=0; [ -f "$_dest/index.html" ] && _had=1

    _tmp=$(mktemp -d); _tar="$_tmp/dist.tar.gz"; _why=""
    [ "$VERBOSE" = "1" ] && say "fetching admin bundle $_url"
    if ! _code=$(curl -sS -L -m 120 -o "$_tar" -w '%{http_code}' "$_url" 2>"$_tmp/curlerr"); then
        _why="download failed: $(cat "$_tmp/curlerr")"
    else
        case "$_code" in
            2*) ;;
            *) _why="server returned HTTP $_code for $_url" ;;
        esac
    fi
    if [ -z "$_why" ]; then
        mkdir -p "$_tmp/x"
        if ! tar -xzf "$_tar" -C "$_tmp/x" 2>"$_tmp/tarerr"; then
            _why="archive did not extract: $(cat "$_tmp/tarerr")"
        elif [ ! -f "$_tmp/x/index.html" ]; then
            _why="archive has no index.html at its root"
        fi
    fi

    if [ -z "$_why" ]; then
        mkdir -p "$(dirname "$_dest")"
        rm -rf "$_dest"
        mv "$_tmp/x" "$_dest"
        rm -rf "$_tmp"
        say "admin bundle $_ver installed into $_dest"
        return 0
    fi

    rm -rf "$_tmp"
    if [ "$_had" -eq 1 ]; then
        warn "could not fetch admin $_ver: $_why"
        warn "keeping the existing admin bundle in $_dest"
        return 2
    fi
    warn "could not fetch admin $_ver: $_why"
    warn "no admin bundle is present; the admin UI stays unavailable until 'plym admin update' succeeds"
    return 1
}
