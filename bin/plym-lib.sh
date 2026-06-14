#!/bin/sh
# plym-lib.sh — shared helpers for the plym CLI (bin/plym) and the installer (install.sh).
#
# This file is SOURCED, never executed. Callers own `set -e`; nothing here relies on it.
# Every helper that can fail prints a RAW diagnostic (no framing) and returns non-zero —
# the framing (the grey box) is applied once, by spin() around captured output or by fail()
# around its context, so diagnostics are never double-boxed.
#
# Contract the caller provides (with sensible fallbacks here):
#   BASE_URL                 e.g. http://localhost:9173
#   HEALTH_TIMEOUT_SECONDS   seconds to wait for /health   (default 60)
#   PLYM_ADMIN_URL           release download base         (default github plym-io/plym-admin)
#   VERBOSE / PLYM_VERBOSE   1 = stream everything live    (default 0)

: "${PLYM_VERBOSE:=0}"
: "${VERBOSE:=$PLYM_VERBOSE}"
: "${HEALTH_TIMEOUT_SECONDS:=60}"
: "${PLYM_LOG_TAIL:=200}"
: "${PLYM_ADMIN_URL:=https://github.com/plym-io/plym-admin/releases/download}"

# ── palette ──────────────────────────────────────────────────────────────────
# Orange is plym's own voice (→ ✓ ✗ !). Grey frames captured output. Red is never used
# for framing — a wall of red reads as "plym is broken", when it is the upstream that failed.
BOLD=$(printf '\033[1m')
DIM=$(printf '\033[2m')
ACCENT=$(printf '\033[38;5;208m')
GREEN=$(printf '\033[38;5;40m')
FRAME=$(printf '\033[38;5;245m')
RESET=$(printf '\033[0m')

say()  { printf '%s→%s %s\n' "$ACCENT" "$RESET" "$1"; }
note() { printf '%s%s%s\n' "$DIM" "$1" "$RESET"; }
warn() { printf '%s!%s %s\n' "$ACCENT" "$RESET" "$1" >&2; }

# box <title> — frame stdin in a grey, titled box on stderr. Empty stdin prints nothing.
# This is the ONE place captured output (logs, tracebacks, HTTP bodies) gets decorated.
box() {
    _title="$1"
    _body=$(cat)
    [ -n "$_body" ] || return 0
    printf '%s┌─ %s %s%s\n' "$FRAME" "$_title" "──────────────────────────────────" "$RESET" >&2
    printf '%s\n' "$_body" | while IFS= read -r _line; do
        printf '%s│%s %s\n' "$FRAME" "$RESET" "$_line" >&2
    done
    printf '%s└────────────────────────────────────────────────────%s\n' "$FRAME" "$RESET" >&2
}

# fail <msg> [exit_code] [context]
# Prints plym's ✗ message, then frames any context (3rd arg, else $PLYM_CONTEXT) and exits.
# Context is never swallowed: this is how a real traceback reaches the user even without --verbose.
fail() {
    _msg="$1"; _code="${2:-1}"; _ctx="${3:-$PLYM_CONTEXT}"
    printf '%s✗%s %s\n' "$ACCENT" "$RESET" "$_msg" >&2
    [ -n "$_ctx" ] && printf '%s\n' "$_ctx" | box "details"
    exit "$_code"
}

# ── spin <msg> <cmd...> ──────────────────────────────────────────────────────
# Runs cmd. Non-verbose: spinner, then ✓/✗ — and on ✗ the captured output is boxed
# (with an empty-output guard so a silent failure still says something). Verbose:
# announces the step and streams the command live, errors included, no capture.
[ -e /dev/tty ] && SPIN_OUT=/dev/tty || SPIN_OUT=/dev/stdout
spin() {
    _msg="$1"; shift
    if [ "$VERBOSE" = "1" ]; then
        printf '%s→%s %s\n' "$ACCENT" "$RESET" "$_msg"
        "$@"
        return $?
    fi
    _log=$(mktemp)
    "$@" >"$_log" 2>&1 &
    _pid=$!
    while kill -0 "$_pid" 2>/dev/null; do
        for _frame in ⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏; do
            kill -0 "$_pid" 2>/dev/null || break
            printf '\r%s%s%s %s ' "$ACCENT" "$_frame" "$RESET" "$_msg" > "$SPIN_OUT"
            sleep 0.08
        done
    done
    _rc=0; wait "$_pid" || _rc=$?
    if [ "$_rc" -eq 0 ]; then
        printf '\r%s✓%s %s\n' "$ACCENT" "$RESET" "$_msg" > "$SPIN_OUT"
    else
        printf '\r%s✗%s %s\n' "$ACCENT" "$RESET" "$_msg" > "$SPIN_OUT"
        if [ -s "$_log" ]; then
            box "$_msg" < "$_log"
        else
            printf '  (the step produced no output — re-run with %s--verbose%s for live logs)\n' "$BOLD" "$RESET" >&2
        fi
    fi
    rm -f "$_log"
    return "$_rc"
}

# retry <attempts> <cmd...> — run cmd until it succeeds or attempts run out.
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

# ── http <method> <url> [curl args...] ───────────────────────────────────────
# Always captures the result: sets HTTP_CODE and HTTP_BODY (body holds the response, or the
# raw curl error — e.g. "curl: (56) Recv failure" — when the connection never produced one,
# in which case HTTP_CODE is 000). No -f, so a 4xx/5xx body is kept, not discarded. Returns
# 0 only on 2xx. In verbose it echoes the request line, the status, and the body.
http() {
    _method="$1"; _url="$2"; shift 2
    _resp=$(curl -sS -m 30 -w '\n%{http_code}' -X "$_method" "$_url" "$@" 2>&1)
    HTTP_CODE=$(printf '%s\n' "$_resp" | tail -n1)
    HTTP_BODY=$(printf '%s\n' "$_resp" | sed '$d')
    case "$HTTP_CODE" in '' | *[!0-9]*) HTTP_CODE=000 ;; esac
    if [ "$VERBOSE" = "1" ]; then
        printf '%s→%s %s %s  %s(HTTP %s)%s\n' "$ACCENT" "$RESET" "$_method" "$_url" "$DIM" "$HTTP_CODE" "$RESET"
        [ -n "$HTTP_BODY" ] && printf '%s\n' "$HTTP_BODY" | box "response $HTTP_CODE"
    fi
    case "$HTTP_CODE" in 2*) return 0 ;; *) return 1 ;; esac
}

# ── docker compose service introspection ─────────────────────────────────────
svc_cid()   { docker compose ps -aq "$1" 2>/dev/null | head -1; }
svc_state() { _c=$(svc_cid "$1"); [ -n "$_c" ] && docker inspect -f '{{.State.Status}}' "$_c" 2>/dev/null; }
svc_diag()  {
    _c=$(svc_cid "$1")
    [ -n "$_c" ] || { printf 'no container'; return; }
    docker inspect -f 'status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' "$_c" 2>/dev/null
}

# Raw (unboxed) dump of one service: a one-line state header + its recent logs.
dump_service() {
    printf '%s — %s\n\n' "$1" "$(svc_diag "$1")"
    docker compose logs --tail "$PLYM_LOG_TAIL" "$1" 2>&1
}

# Report any of the core services that is NOT running — generic, not memory-specific.
# Catches the case where the host OOM killer reaped a different container than the one
# you were watching (caddy/db), which otherwise looks like a random failure.
dump_unhealthy() {
    for _s in api caddy db; do
        case "$(svc_state "$_s")" in
            running | '') : ;;   # healthy, or not part of this stack
            *) printf '\n'; dump_service "$_s" ;;
        esac
    done
}

# ── wait_for_health ──────────────────────────────────────────────────────────
# Polls /health, but does NOT blindly burn the whole timeout: every iteration it checks the
# api container. If it has exited/died, it reports immediately — the crash, its exit code and
# OOM flag, and the logs — instead of waiting out the clock and printing a generic timeout.
# Prints a raw diagnostic and returns non-zero; the caller (usually via spin) frames it.
wait_for_health() {
    _tries=0
    while ! curl -fsS -m 5 "$BASE_URL/health" >/dev/null 2>&1; do
        case "$(svc_state api)" in
            exited | dead)
                printf 'The api container is not running — it exited during startup.\n'
                printf 'This was not a graceful shutdown (%s).\n\n' "$(svc_diag api)"
                dump_service api
                dump_unhealthy
                return 1 ;;
        esac
        _tries=$((_tries + 1))
        if [ "$_tries" -gt "$HEALTH_TIMEOUT_SECONDS" ]; then
            printf 'API did not answer %s/health within %ss.\n' "$BASE_URL" "$HEALTH_TIMEOUT_SECONDS"
            printf 'The container is up but not serving — still starting, or stuck (%s).\n\n' "$(svc_diag api)"
            dump_service api
            dump_unhealthy
            return 1
        fi
        sleep 1
    done
    # Healthy. Under --verbose, surface the api's own startup logs (migrations, build phases,
    # "now serving") so "stream everything" really includes the application logs.
    if [ "$VERBOSE" = "1" ]; then
        printf '%s→%s api is healthy — recent api logs:\n' "$ACCENT" "$RESET"
        docker compose logs --tail "$PLYM_LOG_TAIL" api 2>&1
    fi
    return 0
}

# ── port_in_use <port> ───────────────────────────────────────────────────────
port_in_use() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
    elif command -v nc >/dev/null 2>&1; then
        nc -z 127.0.0.1 "$1" >/dev/null 2>&1
    else
        return 1
    fi
}

# ── fetch_admin <version> <dest_dir> ─────────────────────────────────────────
# Downloads + extracts the admin bundle into dest. On ANY failure it does NOT wipe dest:
# if a bundle is already there it is kept (the app stays admin-capable) and the reason is
# stated loudly; only a first-ever miss leaves dest empty (admin UI unavailable until retry).
# Returns 0 when dest holds a usable bundle (fresh or reused), 1 only when none exists at all.
fetch_admin() {
    _ver="$1"; _dest="$2"
    [ -n "$_ver" ] || { note "No admin version configured — skipping admin fetch."; return 0; }
    _url="$PLYM_ADMIN_URL/$_ver/dist.tar.gz"
    _had=0; [ -f "$_dest/index.html" ] && _had=1

    _tmp=$(mktemp -d); _tar="$_tmp/dist.tar.gz"; _why=""
    [ "$VERBOSE" = "1" ] && say "Fetching admin bundle: $_url"
    if ! _code=$(curl -sS -L -m 120 -o "$_tar" -w '%{http_code}' "$_url" 2>"$_tmp/curlerr"); then
        _why="download failed — $(cat "$_tmp/curlerr")"
    else
        case "$_code" in
            2*) ;;
            *) _why="server returned HTTP $_code for $_url" ;;
        esac
    fi
    if [ -z "$_why" ]; then
        mkdir -p "$_tmp/x"
        if ! tar -xzf "$_tar" -C "$_tmp/x" 2>"$_tmp/tarerr"; then
            _why="archive did not extract — $(cat "$_tmp/tarerr")"
        elif [ ! -f "$_tmp/x/index.html" ]; then
            _why="archive has no index.html at its root"
        fi
    fi

    if [ -z "$_why" ]; then
        mkdir -p "$(dirname "$_dest")"
        rm -rf "$_dest"
        mv "$_tmp/x" "$_dest"
        rm -rf "$_tmp"
        note "Admin bundle $_ver installed into $_dest."
        return 0
    fi

    rm -rf "$_tmp"
    if [ "$_had" -eq 1 ]; then
        warn "Could not fetch admin $_ver: $_why"
        warn "Keeping the existing admin bundle in $_dest — it was left untouched."
        return 0
    fi
    warn "Could not fetch admin $_ver: $_why"
    warn "No admin bundle is present yet — the admin UI stays unavailable until 'plym admin update' succeeds."
    return 1
}
