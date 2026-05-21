# Agentheim Code — Task Runner

# Default recipe
default:
    @just --list

# Install all dependencies
install:
    pip install -e .[dev]
    npm --prefix apps/web install
    npm --prefix apps/desktop install

# Run all tests
test:
    pytest --cov -q
    npm --prefix apps/web run test
    cd apps/desktop/src-tauri && cargo test

# Run Python tests only
test-py:
    pytest --cov -q

# Run frontend tests only
test-web:
    npm --prefix apps/web run test

# Run Rust tests only
test-rust:
    cd apps/desktop/src-tauri && cargo test

# Lint and type check everything
lint:
    ruff check src/ tests/
    ruff format --check src/ tests/
    mypy src/

# Auto-fix formatting and lint issues
fix:
    ruff check --fix src/ tests/
    ruff format src/ tests/

# Build the web frontend
build-web:
    npm --prefix apps/web run build

# Build the desktop app (Windows)
build-desktop:
    npm --prefix apps/desktop run build

# Run the local backend server
serve:
    agentheim-code app --web
