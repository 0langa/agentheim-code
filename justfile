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

# Lint product-owned code and focused tests
lint:
    ruff check src/agentheim_code src/memory src/tools/shell tests/
    ruff format --check src/agentheim_code src/memory src/tools/shell tests/
    mypy src/agentheim_code src/memory src/tools/shell --follow-imports=skip

# Future cleanup target for copied shared/runtime modules
lint-all:
    ruff check src/ tests/
    ruff format --check src/ tests/
    mypy src/ --follow-imports=normal

type-all:
    mypy src/ --follow-imports=normal

# Auto-fix formatting and lint issues
fix:
    ruff check --fix src/agentheim_code src/memory src/tools/shell tests/
    ruff format src/agentheim_code src/memory src/tools/shell tests/

# Build the web frontend
build-web:
    npm --prefix apps/web run build

# Build the desktop app (Windows)
build-desktop:
    npm --prefix apps/desktop run build

# Run the local backend server
serve:
    agentheim-code app --web
