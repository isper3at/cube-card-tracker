#!/usr/bin/env bash
# ============================================================
# dev.sh — Start the Cube Card Tracker for local development
#
# Usage:
#   ./dev.sh              # start both backend + frontend
#   ./dev.sh --backend    # backend only
#   ./dev.sh --frontend   # frontend only
#   ./dev.sh --setup      # install deps only, don't run servers
#
# Ctrl+C will gracefully terminate both servers.
# ============================================================
set -euo pipefail

# ── Colours ─────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Config ───────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
BACKEND_PORT=5000
FRONTEND_PORT=5173
LOG_DIR="$SCRIPT_DIR/.dev-logs"

# PIDs of background processes (populated at runtime)
BACKEND_PID=""
FRONTEND_PID=""

# ── Helpers ──────────────────────────────────────────────────
log()    { echo -e "${BOLD}[dev]${RESET} $*"; }
info()   { echo -e "${CYAN}[dev]${RESET} $*"; }
ok()     { echo -e "${GREEN}[dev]${RESET} ✓ $*"; }
warn()   { echo -e "${YELLOW}[dev]${RESET} ⚠ $*"; }
err()    { echo -e "${RED}[dev]${RESET} ✗ $*" >&2; }

require() {
    if ! command -v "$1" &>/dev/null; then
        err "Required tool not found: $1  →  $2"
        return 1
    fi
}

port_in_use() { lsof -ti tcp:"$1" &>/dev/null; }

# ── Cleanup / signal handling ─────────────────────────────────
cleanup() {
    echo ""
    log "Shutting down servers…"

    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        info "Stopping backend  (PID $BACKEND_PID)"
        kill -TERM "$BACKEND_PID" 2>/dev/null || true
    fi

    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        info "Stopping frontend (PID $FRONTEND_PID)"
        kill -TERM "$FRONTEND_PID" 2>/dev/null || true
    fi

    # Give processes a moment to exit cleanly, then force-kill
    sleep 1
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill -KILL "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill -KILL "$FRONTEND_PID" 2>/dev/null || true
    fi

    ok "All servers stopped."
}

trap cleanup EXIT INT TERM

# ── Dependency checks ─────────────────────────────────────────
check_deps() {
    local missing=0

    require python3   "https://www.python.org/" || missing=1
    require node      "https://nodejs.org/"      || missing=1
    require npm       "https://nodejs.org/"      || missing=1
    require poetry    "pip install poetry  OR  https://python-poetry.org/docs/#installation" || missing=1

    if (( missing )); then
        err "Please install the missing tools above and re-run."
        exit 1
    fi

    # Optional but recommended
    if ! command -v tesseract &>/dev/null; then
        warn "tesseract not found — OCR will be disabled."
        warn "Install: brew install tesseract  OR  apt install tesseract-ocr"
    fi

    ok "All required tools found."
}

# ── Backend setup ─────────────────────────────────────────────
setup_backend() {
    log "Setting up backend…"

    if ! [[ -f "$BACKEND_DIR/pyproject.toml" ]]; then
        err "backend/pyproject.toml not found. Is BACKEND_DIR correct? ($BACKEND_DIR)"
        exit 1
    fi

    pushd "$BACKEND_DIR" > /dev/null

    # Create .env from example if it doesn't exist
    if [[ ! -f ".env" && -f ".env.example" ]]; then
        cp .env.example .env
        info "Created backend/.env from .env.example"
    fi

    # Create data directories
    mkdir -p data/uploads data/annotated data/cards

    info "Installing Python dependencies via Poetry…"
    poetry install --no-interaction --no-ansi

    ok "Backend ready."
    popd > /dev/null
}

# ── Frontend setup ────────────────────────────────────────────
setup_frontend() {
    log "Setting up frontend…"

    if ! [[ -f "$FRONTEND_DIR/package.json" ]]; then
        err "frontend/package.json not found. Is FRONTEND_DIR correct? ($FRONTEND_DIR)"
        exit 1
    fi

    pushd "$FRONTEND_DIR" > /dev/null

    # Create .env from example if it doesn't exist.
    # Edit frontend/.env to change API_URL if your backend runs on a different port.
    if [[ ! -f ".env" && -f ".env.example" ]]; then
        cp .env.example .env
        info "Created frontend/.env from .env.example"
    fi

    # Install if node_modules is missing OR package-lock.json is newer than node_modules
    if [[ ! -d "node_modules" ]] || [[ ! -f "package-lock.json" ]] || \
       [[ "package.json" -nt "node_modules" ]] || [[ "package-lock.json" -nt "node_modules" ]]; then
        info "Installing Node dependencies…"
        npm install
    else
        info "node_modules is up to date — skipping npm install."
    fi

    ok "Frontend ready."
    popd > /dev/null
}

# ── Start backend ─────────────────────────────────────────────
start_backend() {
    if port_in_use "$BACKEND_PORT"; then
        warn "Port $BACKEND_PORT is already in use — skipping backend start."
        warn "Kill the existing process first:  lsof -ti tcp:$BACKEND_PORT | xargs kill"
        return
    fi

    mkdir -p "$LOG_DIR"
    local log_file="$LOG_DIR/backend.log"

    info "Starting backend on http://localhost:$BACKEND_PORT"
    info "  Logs → $log_file"

    pushd "$BACKEND_DIR" > /dev/null

    # Load .env manually so poetry run inherits variables
    set -o allexport
    [[ -f ".env" ]] && source ".env"
    set +o allexport

    poetry run flask --app wsgi:app run \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --debug \
        >> "$log_file" 2>&1 &

    BACKEND_PID=$!
    popd > /dev/null

    # Wait briefly to catch immediate crash
    sleep 2
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        err "Backend failed to start. Check logs: $log_file"
        tail -20 "$log_file" >&2
        exit 1
    fi

    ok "Backend running (PID $BACKEND_PID)"
}

# ── Start frontend ────────────────────────────────────────────
start_frontend() {
    if port_in_use "$FRONTEND_PORT"; then
        warn "Port $FRONTEND_PORT is already in use — skipping frontend start."
        return
    fi

    mkdir -p "$LOG_DIR"
    local log_file="$LOG_DIR/frontend.log"

    info "Starting frontend on http://localhost:$FRONTEND_PORT  (Parcel)"
    info "  Logs → $log_file"

    pushd "$FRONTEND_DIR" > /dev/null

    npm run dev \
        >> "$log_file" 2>&1 &

    FRONTEND_PID=$!
    popd > /dev/null

    # Wait briefly to catch immediate crash
    sleep 3
    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        err "Frontend failed to start. Check logs: $log_file"
        tail -20 "$log_file" >&2
        exit 1
    fi

    ok "Frontend running (PID $FRONTEND_PID)"
}

# ── Wait and stream logs ──────────────────────────────────────
stream_logs() {
    mkdir -p "$LOG_DIR"

    echo ""
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}  Cube Card Tracker is running!${RESET}"
    echo ""
    echo -e "  ${BOLD}Frontend:${RESET}  http://localhost:$FRONTEND_PORT"
    echo -e "  ${BOLD}Backend:${RESET}   http://localhost:$BACKEND_PORT"
    echo -e "  ${BOLD}API docs:${RESET}  http://localhost:$BACKEND_PORT/api/health"
    echo ""
    echo -e "  Press ${BOLD}Ctrl+C${RESET} to stop both servers."
    echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""

    # Tail both log files in parallel, prefixing each line
    (
        tail -F "$LOG_DIR/backend.log"  2>/dev/null | sed "s/^/${BLUE}[backend] ${RESET}/"  &
        TAIL_BACKEND_PID=$!

        tail -F "$LOG_DIR/frontend.log" 2>/dev/null | sed "s/^/${YELLOW}[frontend]${RESET} /" &
        TAIL_FRONTEND_PID=$!

        # Monitor the server PIDs — if either crashes, we exit
        while true; do
            sleep 2

            if [[ -n "$BACKEND_PID" ]] && ! kill -0 "$BACKEND_PID" 2>/dev/null; then
                err "Backend process exited unexpectedly!"
                kill $TAIL_BACKEND_PID $TAIL_FRONTEND_PID 2>/dev/null || true
                exit 1
            fi

            if [[ -n "$FRONTEND_PID" ]] && ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
                err "Frontend process exited unexpectedly!"
                kill $TAIL_BACKEND_PID $TAIL_FRONTEND_PID 2>/dev/null || true
                exit 1
            fi
        done
    )
}

# ── Argument parsing ──────────────────────────────────────────
RUN_BACKEND=true
RUN_FRONTEND=true
SETUP_ONLY=false

for arg in "$@"; do
    case "$arg" in
        --backend)  RUN_FRONTEND=false ;;
        --frontend) RUN_BACKEND=false  ;;
        --setup)    SETUP_ONLY=true    ;;
        --help|-h)
            echo "Usage: $0 [--backend | --frontend | --setup | --help]"
            echo ""
            echo "  (no args)    Start both backend and frontend"
            echo "  --backend    Start backend only"
            echo "  --frontend   Start frontend only"
            echo "  --setup      Install dependencies only, do not start servers"
            echo "  --help       Show this message"
            exit 0
            ;;
        *)
            err "Unknown argument: $arg  (use --help)"
            exit 1
            ;;
    esac
done

# ── Main ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  🎴  Cube Card Tracker — Dev Server${RESET}"
echo ""

check_deps

if $RUN_BACKEND || $SETUP_ONLY; then
    setup_backend
fi

if $RUN_FRONTEND || $SETUP_ONLY; then
    setup_frontend
fi

if $SETUP_ONLY; then
    ok "Setup complete. Run './dev.sh' to start the servers."
    exit 0
fi

if $RUN_BACKEND; then
    start_backend
fi

if $RUN_FRONTEND; then
    start_frontend
fi

# Block here — cleanup trap fires on Ctrl+C
stream_logs