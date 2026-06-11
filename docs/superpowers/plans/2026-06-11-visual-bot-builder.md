# Visual Bot Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved single-admin Visual Bot Builder in a new top-level `automation_hub/` folder without modifying the behavior of existing automation scripts.

**Architecture:** A FastAPI/Jinja web process manages immutable bot configuration versions in PostgreSQL. A scheduler creates idempotent run records and enqueues them through Redis/RQ; a separate Playwright worker captures public Google Sheets and delivers images to WAHA per destination. OpenAI Responses API calls are optional, structured, backend-only helpers for configuration drafts and sanitized failure analysis.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, HTMX, SQLAlchemy 2, Alembic, PostgreSQL, Redis, RQ, Playwright Chromium, Pillow, httpx, OpenAI Python SDK, Argon2, Pytest, Docker Compose.

---

## Scope And Execution Notes

- All application code lives under `automation_hub/`.
- Existing root scripts such as `kirim_olt.py`, `mirror_isp.py`, and their current cron jobs remain untouched until the pilot cutover task.
- Run commands from `C:\Users\anant\Downloads\OLT\automation_hub` unless a task says otherwise.
- Use TDD for every domain rule and integration boundary.
- Unit tests must not require network access.
- PostgreSQL/Redis integration tests use the Compose test services.
- Never use the currently hardcoded credentials from the legacy scripts. Generate test-only values and require rotated production values at deployment.

## Planned File Map

```text
automation_hub/
├── .dockerignore
├── .env.example
├── README.md
├── pyproject.toml
├── alembic.ini
├── compose.yaml
├── Dockerfile
├── docker/
│   ├── entrypoint-web.sh
│   ├── entrypoint-worker.sh
│   └── nginx-aaPanel.example.conf
├── scripts/
│   ├── bootstrap_admin.py
│   ├── backup_postgres.sh
│   ├── restore_postgres.sh
│   └── import_legacy_bot.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── src/automation_hub/
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── logging.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── session.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── bots.py
│   │       └── runs.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── enums.py
│   │   ├── bot_config.py
│   │   ├── ai.py
│   │   └── scheduling.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── bots.py
│   │   ├── destinations.py
│   │   ├── runs.py
│   │   └── sessions.py
│   ├── security/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── csrf.py
│   │   ├── rate_limit.py
│   │   └── redaction.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── artifacts.py
│   │   ├── bot_versions.py
│   │   ├── caption.py
│   │   ├── capture.py
│   │   ├── health.py
│   │   ├── openai_service.py
│   │   ├── run_executor.py
│   │   ├── scheduler.py
│   │   ├── url_policy.py
│   │   └── waha.py
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── queue.py
│   │   ├── scheduler_main.py
│   │   ├── tasks.py
│   │   └── worker_main.py
│   └── web/
│       ├── __init__.py
│       ├── app.py
│       ├── dependencies.py
│       ├── forms.py
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── auth.py
│       │   ├── bots.py
│       │   ├── dashboard.py
│       │   ├── integrations.py
│       │   └── runs.py
│       ├── static/
│       │   ├── app.css
│       │   ├── crop-selector.js
│       │   └── vendor/htmx.min.js
│       └── templates/
│           ├── base.html
│           ├── auth/login.html
│           ├── dashboard/index.html
│           ├── bots/
│           │   ├── detail.html
│           │   ├── list.html
│           │   └── wizard.html
│           ├── integrations/index.html
│           └── runs/detail.html
└── tests/
    ├── conftest.py
    ├── fixtures/grid.html
    ├── unit/
    ├── integration/
    └── e2e/
```

## Phase 1: Foundation And Security Boundaries

### Task 1: Scaffold The Isolated Application

**Files:**
- Create: `automation_hub/pyproject.toml`
- Create: `automation_hub/.env.example`
- Create: `automation_hub/.dockerignore`
- Create: `automation_hub/README.md`
- Create: `automation_hub/src/automation_hub/__init__.py`
- Create: `automation_hub/src/automation_hub/web/__init__.py`
- Create: `automation_hub/src/automation_hub/web/app.py`
- Create: `automation_hub/tests/unit/test_app.py`

- [ ] **Step 1: Write the failing application smoke test**

```python
# automation_hub/tests/unit/test_app.py
from fastapi.testclient import TestClient

from automation_hub.web.app import create_app


def test_health_live_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Create `pyproject.toml` and install the development environment**

```toml
[project]
name = "automation-hub"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "alembic",
  "argon2-cffi",
  "fastapi",
  "httpx",
  "jinja2",
  "openai",
  "pillow",
  "playwright",
  "psycopg[binary]",
  "pydantic-settings",
  "python-multipart",
  "redis",
  "rq",
  "sqlalchemy",
  "uvicorn[standard]",
]

[project.optional-dependencies]
dev = [
  "freezegun",
  "mypy",
  "pytest",
  "pytest-asyncio",
  "pytest-cov",
  "respx",
  "ruff",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/automation_hub"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
markers = [
  "integration: requires PostgreSQL and Redis",
  "e2e: exercises the full web flow",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["automation_hub"]
```

Run:

```powershell
uv sync --extra dev
uv run pytest tests/unit/test_app.py -v
```

Expected: FAIL because `automation_hub.web.app` does not exist yet.

- [ ] **Step 3: Implement the minimal application factory**

```python
# automation_hub/src/automation_hub/web/app.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Automation Hub")

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Add environment documentation**

```dotenv
# automation_hub/.env.example
APP_ENV=development
APP_BASE_URL=http://localhost:8000
APP_SECRET_KEY=replace-with-at-least-32-random-bytes
DATABASE_URL=postgresql+psycopg://automation:automation@postgres:5432/automation
REDIS_URL=redis://redis:6379/0
ARTIFACT_ROOT=/data/artifacts
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4
WAHA_URL=
WAHA_SESSION=
WAHA_API_KEY=
TZ=Asia/Jakarta
```

- [ ] **Step 5: Run the foundation checks**

Run:

```powershell
uv run pytest tests/unit/test_app.py -v
uv run ruff check .
uv run mypy src
```

Expected: 1 test passes; Ruff and mypy exit 0.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: scaffold automation hub"
```

### Task 2: Add Typed Settings, Error Codes, Logging, And Redaction

**Files:**
- Create: `automation_hub/src/automation_hub/config.py`
- Create: `automation_hub/src/automation_hub/errors.py`
- Create: `automation_hub/src/automation_hub/logging.py`
- Create: `automation_hub/src/automation_hub/security/redaction.py`
- Modify: `automation_hub/src/automation_hub/web/app.py`
- Test: `automation_hub/tests/unit/test_config.py`
- Test: `automation_hub/tests/unit/test_redaction.py`

- [ ] **Step 1: Write failing settings and redaction tests**

```python
# automation_hub/tests/unit/test_config.py
from automation_hub.config import Settings


def test_default_openai_model_is_gpt_5_4() -> None:
    settings = Settings(
        app_secret_key="x" * 32,
        database_url="postgresql+psycopg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
    )

    assert settings.openai_model == "gpt-5.4"
    assert settings.timezone == "Asia/Jakarta"
```

```python
# automation_hub/tests/unit/test_redaction.py
from automation_hub.security.redaction import redact


def test_redact_removes_authorization_and_api_keys() -> None:
    value = {
        "Authorization": "Bearer secret-token",
        "X-Api-Key": "waha-secret",
        "message": "request failed",
    }

    assert redact(value) == {
        "Authorization": "[REDACTED]",
        "X-Api-Key": "[REDACTED]",
        "message": "request failed",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/unit/test_config.py tests/unit/test_redaction.py -v
```

Expected: FAIL because settings and redaction modules do not exist.

- [ ] **Step 3: Implement typed settings and deterministic errors**

```python
# automation_hub/src/automation_hub/config.py
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    app_secret_key: str = Field(min_length=32)
    database_url: str
    redis_url: str
    artifact_root: Path = Path("./data/artifacts")
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"
    waha_url: str | None = None
    waha_session: str | None = None
    waha_api_key: str | None = None
    timezone: str = "Asia/Jakarta"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# automation_hub/src/automation_hub/errors.py
from enum import StrEnum


class ErrorCode(StrEnum):
    SOURCE_INVALID = "SOURCE_INVALID"
    SOURCE_BLOCKED = "SOURCE_BLOCKED"
    SHEET_TIMEOUT = "SHEET_TIMEOUT"
    SHEET_RENDER_FAILED = "SHEET_RENDER_FAILED"
    CROP_OUT_OF_BOUNDS = "CROP_OUT_OF_BOUNDS"
    CAPTURE_FAILED = "CAPTURE_FAILED"
    IMAGE_PROCESSING_FAILED = "IMAGE_PROCESSING_FAILED"
    WAHA_AUTH = "WAHA_AUTH"
    WAHA_SESSION_UNAVAILABLE = "WAHA_SESSION_UNAVAILABLE"
    DESTINATION_INVALID = "DESTINATION_INVALID"
    WAHA_RATE_LIMITED = "WAHA_RATE_LIMITED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    OPENAI_UNAVAILABLE = "OPENAI_UNAVAILABLE"
    OPENAI_INVALID_OUTPUT = "OPENAI_INVALID_OUTPUT"
```

- [ ] **Step 4: Implement recursive redaction and JSON logging**

```python
# automation_hub/src/automation_hub/security/redaction.py
from collections.abc import Mapping, Sequence
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "x-api-key",
    "api_key",
    "openai_api_key",
    "waha_api_key",
    "password",
    "secret",
    "token",
}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if key.casefold() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    return value
```

Configure `automation_hub.logging.configure_logging()` to emit one JSON object per
line with timestamp, level, event, run ID, bot ID, and redacted context.

- [ ] **Step 5: Run focused and full checks**

Run:

```powershell
uv run pytest tests/unit/test_config.py tests/unit/test_redaction.py -v
uv run ruff check .
uv run mypy src
```

Expected: all tests pass; static checks exit 0.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add typed settings and safe logging"
```

### Task 3: Enforce The Public Google Sheet URL Policy

**Files:**
- Create: `automation_hub/src/automation_hub/services/url_policy.py`
- Test: `automation_hub/tests/unit/test_url_policy.py`

- [ ] **Step 1: Write the URL policy matrix**

```python
# automation_hub/tests/unit/test_url_policy.py
import pytest

from automation_hub.errors import ErrorCode
from automation_hub.services.url_policy import SourcePolicyError, normalize_sheet_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://docs.google.com/spreadsheets/d/abc123/edit?gid=42#gid=42",
            "https://docs.google.com/spreadsheets/d/abc123/edit?gid=42",
        ),
        (
            "https://docs.google.com/spreadsheets/d/e/pub-token/pubhtml?gid=7",
            "https://docs.google.com/spreadsheets/d/e/pub-token/pubhtml?gid=7",
        ),
    ],
)
def test_normalize_sheet_url_accepts_supported_public_urls(raw: str, expected: str) -> None:
    assert normalize_sheet_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "http://docs.google.com/spreadsheets/d/abc/edit",
        "https://localhost/sheet",
        "https://127.0.0.1/sheet",
        "https://10.0.0.5/sheet",
        "https://example.com/sheet",
        "file:///etc/passwd",
        "https://docs.google.com:8443/spreadsheets/d/abc/edit",
    ],
)
def test_normalize_sheet_url_rejects_unsafe_sources(raw: str) -> None:
    with pytest.raises(SourcePolicyError) as exc:
        normalize_sheet_url(raw)

    assert exc.value.code in {ErrorCode.SOURCE_INVALID, ErrorCode.SOURCE_BLOCKED}
```

- [ ] **Step 2: Run the test to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_url_policy.py -v
```

Expected: FAIL because `normalize_sheet_url` is missing.

- [ ] **Step 3: Implement strict parsing and canonicalization**

```python
# automation_hub/src/automation_hub/services/url_policy.py
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from automation_hub.errors import ErrorCode

ALLOWED_HOSTS = {"docs.google.com"}
ALLOWED_PREFIXES = ("/spreadsheets/d/", "/spreadsheets/d/e/")


@dataclass(frozen=True)
class SourcePolicyError(ValueError):
    code: ErrorCode
    message: str


def normalize_sheet_url(raw: str) -> str:
    parsed = urlsplit(raw.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise SourcePolicyError(ErrorCode.SOURCE_INVALID, "Only HTTPS Sheet URLs are allowed")
    if parsed.hostname not in ALLOWED_HOSTS or parsed.port not in (None, 443):
        raise SourcePolicyError(ErrorCode.SOURCE_BLOCKED, "Source host is not allowed")
    if not parsed.path.startswith(ALLOWED_PREFIXES):
        raise SourcePolicyError(ErrorCode.SOURCE_INVALID, "Unsupported Google Sheet URL")

    query = parse_qs(parsed.query)
    gid = query.get("gid", [None])[0]
    safe_query = urlencode({"gid": gid}) if gid and gid.isdigit() else ""
    return urlunsplit(("https", parsed.hostname, parsed.path, safe_query, ""))
```

The capture task must later revalidate every redirect target with the same host,
scheme, port, and IP-range policy before continuing.

- [ ] **Step 4: Run tests and static checks**

Run:

```powershell
uv run pytest tests/unit/test_url_policy.py -v
uv run ruff check src tests
uv run mypy src
```

Expected: policy matrix passes.

- [ ] **Step 5: Commit**

```powershell
git add automation_hub
git commit -m "feat: enforce public sheet source policy"
```

## Phase 2: Persistence And Authentication

### Task 4: Add PostgreSQL Models And Initial Migration

**Files:**
- Create: `automation_hub/src/automation_hub/db/base.py`
- Create: `automation_hub/src/automation_hub/db/session.py`
- Create: `automation_hub/src/automation_hub/db/models/auth.py`
- Create: `automation_hub/src/automation_hub/db/models/bots.py`
- Create: `automation_hub/src/automation_hub/db/models/runs.py`
- Create: `automation_hub/src/automation_hub/db/models/__init__.py`
- Create: `automation_hub/alembic.ini`
- Create: `automation_hub/alembic/env.py`
- Create: `automation_hub/alembic/versions/0001_initial_schema.py`
- Create: `automation_hub/compose.yaml`
- Create: `automation_hub/tests/conftest.py`
- Test: `automation_hub/tests/integration/test_schema.py`

- [ ] **Step 1: Write the schema integration test**

```python
# automation_hub/tests/integration/test_schema.py
import sqlalchemy as sa


def test_initial_schema_contains_core_tables(database_engine: sa.Engine) -> None:
    inspector = sa.inspect(database_engine)

    assert {
        "users",
        "user_sessions",
        "bots",
        "bot_versions",
        "destinations",
        "bot_version_destinations",
        "schedules",
        "runs",
        "run_deliveries",
        "run_events",
    }.issubset(set(inspector.get_table_names()))
```

- [ ] **Step 2: Start PostgreSQL and verify the test fails**

Add a Compose `postgres` service with database/user/password `automation`.
Add `database_engine`, transactional `session`, and migration fixtures in
`tests/conftest.py`; each integration test runs inside an isolated transaction
or truncates all application tables after completion.

Run:

```powershell
docker compose up -d postgres
uv run alembic upgrade head
uv run pytest tests/integration/test_schema.py -v -m integration
```

Expected: FAIL because migration metadata is not defined.

- [ ] **Step 3: Implement focused SQLAlchemy model modules**

Use UUID primary keys and timezone-aware timestamps. Define:

```python
class BotStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    CAPTURING = "CAPTURING"
    SENDING = "SENDING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    DELIVERY_UNKNOWN = "DELIVERY_UNKNOWN"
    SKIPPED_OVERLAP = "SKIPPED_OVERLAP"
    CANCELLED = "CANCELLED"
```

Store immutable bot configuration as PostgreSQL `JSONB` in `bot_versions.config`,
with explicit relational rows for destinations, schedules, runs, and deliveries.
The initial schema must include these fields used by later tasks:

```text
user_sessions.token_digest
user_sessions.csrf_token
user_sessions.data_json JSONB
user_sessions.expires_at
bot_versions.test_capture_passed_at
bot_versions.test_capture_sha256
bot_versions.test_delivery_passed_at
bot_versions.test_delivery_destination_id
runs.artifact_relative_path
runs.artifact_sha256
runs.artifact_expires_at
```

Add these required constraints:

```python
sa.UniqueConstraint("bot_id", "version_number", name="uq_bot_version")
sa.UniqueConstraint("occurrence_key", name="uq_run_occurrence")
sa.UniqueConstraint("run_id", "destination_id", name="uq_run_destination")
```

- [ ] **Step 4: Generate and review the initial migration**

Run:

```powershell
uv run alembic revision --autogenerate -m "initial schema"
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

Expected: upgrade, downgrade, and second upgrade all exit 0. Rename the generated
revision file to `0001_initial_schema.py` and keep its revision ID stable.

- [ ] **Step 5: Run integration and unit suites**

Run:

```powershell
uv run pytest tests/integration/test_schema.py -v -m integration
uv run pytest tests/unit -v
```

Expected: schema test and prior unit tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add automation hub database schema"
```

### Task 5: Implement Single-Admin Authentication And CSRF

**Files:**
- Create: `automation_hub/src/automation_hub/security/auth.py`
- Create: `automation_hub/src/automation_hub/security/csrf.py`
- Create: `automation_hub/src/automation_hub/security/rate_limit.py`
- Create: `automation_hub/src/automation_hub/repositories/sessions.py`
- Create: `automation_hub/src/automation_hub/web/dependencies.py`
- Create: `automation_hub/src/automation_hub/web/routes/auth.py`
- Create: `automation_hub/src/automation_hub/web/templates/auth/login.html`
- Create: `automation_hub/scripts/bootstrap_admin.py`
- Modify: `automation_hub/src/automation_hub/web/app.py`
- Test: `automation_hub/tests/unit/test_auth.py`
- Test: `automation_hub/tests/integration/test_auth_flow.py`

- [ ] **Step 1: Write password and session token tests**

```python
def test_password_hash_round_trip() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert verify_password(hashed, "correct horse battery staple") is True
    assert verify_password(hashed, "wrong") is False


def test_session_cookie_stores_only_opaque_token_hash() -> None:
    raw, digest = new_session_token()

    assert raw != digest
    assert digest == hash_session_token(raw)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_auth.py -v
```

Expected: FAIL because authentication helpers are missing.

- [ ] **Step 3: Implement Argon2 passwords and server-side sessions**

```python
from argon2 import PasswordHasher

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(encoded: str, password: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except Exception:
        return False
```

Generate a 32-byte URL-safe session token, store only its SHA-256 digest in
`user_sessions`, and send the raw token in an `HttpOnly`, `Secure` in production,
`SameSite=Lax` cookie.

- [ ] **Step 4: Implement login rate limiting and CSRF**

Use Redis key `login:{client_ip}:{username}` with a five-attempt limit over
15 minutes. Store a CSRF token in each session row and require it for every
state-changing form:

```python
def require_csrf(session_token: str, submitted_token: str) -> None:
    if not secrets.compare_digest(session_token, submitted_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
```

- [ ] **Step 5: Add bootstrap and end-to-end auth flow**

`scripts/bootstrap_admin.py` must:

1. Refuse to print or accept a password through command arguments.
2. Read the password with `getpass.getpass()`.
3. Refuse to create a second admin.
4. Commit the Argon2 hash.

Integration flow:

```python
def test_login_protects_dashboard(client, admin_user) -> None:
    assert client.get("/").status_code == 303

    response = client.post(
        "/login",
        data={"username": admin_user.username, "password": "test-password"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "automation_session=" in response.headers["set-cookie"]
```

- [ ] **Step 6: Run auth checks**

Run:

```powershell
uv run pytest tests/unit/test_auth.py -v
uv run pytest tests/integration/test_auth_flow.py -v -m integration
uv run ruff check .
uv run mypy src
```

Expected: auth tests and static checks pass.

- [ ] **Step 7: Commit**

```powershell
git add automation_hub
git commit -m "feat: add single admin authentication"
```

## Phase 3: Bot Configuration And Builder

### Task 6: Define Validated Bot, Crop, Caption, And Schedule Schemas

**Files:**
- Create: `automation_hub/src/automation_hub/domain/enums.py`
- Create: `automation_hub/src/automation_hub/domain/bot_config.py`
- Create: `automation_hub/src/automation_hub/domain/scheduling.py`
- Create: `automation_hub/src/automation_hub/services/caption.py`
- Test: `automation_hub/tests/unit/test_bot_config.py`
- Test: `automation_hub/tests/unit/test_scheduling.py`
- Test: `automation_hub/tests/unit/test_caption.py`

- [ ] **Step 1: Write failing domain tests**

```python
def test_crop_must_fit_viewport() -> None:
    with pytest.raises(ValidationError):
        ScreenshotConfig(
            source_url="https://docs.google.com/spreadsheets/d/abc/edit",
            viewport_width=1200,
            viewport_height=800,
            crop=CropRect(x=1100, y=20, width=200, height=100),
        )


def test_daily_schedule_calculates_next_utc_occurrence() -> None:
    schedule = DailyTimesSchedule(times=[time(8, 0)], timezone="Asia/Jakarta")

    next_run = calculate_next_run(schedule, datetime(2026, 6, 10, 23, 30, tzinfo=UTC))

    assert next_run == datetime(2026, 6, 11, 1, 0, tzinfo=UTC)


def test_caption_supports_only_approved_placeholders() -> None:
    assert render_caption("Laporan {date}", now=fixed_now) == "Laporan 2026-06-11"
    with pytest.raises(InvalidCaption):
        render_caption("{__class__}", now=fixed_now)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_bot_config.py tests/unit/test_scheduling.py tests/unit/test_caption.py -v
```

Expected: FAIL because schemas and services do not exist.

- [ ] **Step 3: Implement the complete configuration contract**

```python
class CropRect(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ScreenshotConfig(BaseModel):
    source_url: str
    viewport_width: int = Field(default=1920, ge=800, le=3840)
    viewport_height: int = Field(default=1500, ge=600, le=4000)
    device_scale_factor: float = Field(default=1.0, ge=1.0, le=2.0)
    navigation_timeout_seconds: int = Field(default=90, ge=10, le=120)
    stabilization_wait_seconds: int = Field(default=15, ge=0, le=30)
    crop: CropRect
    output_format: Literal["png"] = "png"
    max_dimension: int = Field(default=2500, ge=500, le=4000)


class BotVersionConfig(BaseModel):
    screenshot: ScreenshotConfig
    caption_template: str = Field(min_length=1, max_length=4096)
    destination_ids: list[UUID] = Field(min_length=1)
    schedule: DailyTimesSchedule | FixedIntervalSchedule
```

Add a model validator that normalizes the source URL and rejects crop rectangles
outside the viewport.

- [ ] **Step 4: Implement schedule and caption services**

Daily schedules accept one or more unique local times. Fixed intervals accept
5 minutes through 24 hours. `calculate_next_run()` returns UTC and never emits a
past timestamp.

Caption placeholders are exactly:

```python
ALLOWED_PLACEHOLDERS = {
    "date": "%Y-%m-%d",
    "date_id": "%d-%m-%Y",
    "time": "%H:%M",
    "datetime": "%Y-%m-%d %H:%M",
}
```

- [ ] **Step 5: Run domain verification**

Run:

```powershell
uv run pytest tests/unit/test_bot_config.py tests/unit/test_scheduling.py tests/unit/test_caption.py -v
uv run ruff check .
uv run mypy src
```

Expected: all domain tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: define validated bot configuration"
```

### Task 7: Add Destination Registry And Immutable Bot Version Service

**Files:**
- Create: `automation_hub/src/automation_hub/repositories/destinations.py`
- Create: `automation_hub/src/automation_hub/repositories/bots.py`
- Create: `automation_hub/src/automation_hub/services/bot_versions.py`
- Create: `automation_hub/src/automation_hub/web/routes/integrations.py`
- Create: `automation_hub/src/automation_hub/web/templates/integrations/index.html`
- Test: `automation_hub/tests/integration/test_bot_versions.py`
- Test: `automation_hub/tests/integration/test_destinations.py`

- [ ] **Step 1: Write failing version and destination tests**

```python
def test_create_version_increments_and_preserves_previous_config(session, bot, destination) -> None:
    first = create_bot_version(session, bot.id, config_for(destination.id, caption="First"))
    second = create_bot_version(session, bot.id, config_for(destination.id, caption="Second"))

    assert first.version_number == 1
    assert second.version_number == 2
    assert first.config["caption_template"] == "First"
    assert second.config["caption_template"] == "Second"


def test_disabled_destination_cannot_be_added_to_new_version(session, disabled_destination) -> None:
    with pytest.raises(DestinationUnavailable):
        create_bot_version(
            session,
            bot_id=uuid4(),
            config=config_for(disabled_destination.id),
        )
```

- [ ] **Step 2: Run integration tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_bot_versions.py tests/integration/test_destinations.py -v -m integration
```

Expected: FAIL because repositories and service are missing.

- [ ] **Step 3: Implement transaction-safe version creation**

`create_bot_version()` must:

1. Lock the bot row.
2. Load and validate enabled destinations.
3. Calculate `max(version_number) + 1`.
4. Store `BotVersionConfig.model_dump(mode="json")`.
5. Insert ordered destination links.
6. Update `bots.current_version_id`.
7. Commit once.

Never update a `bot_versions.config` row after creation.
When the wizard creates its final draft version, copy capture and delivery
evidence from `user_sessions.data_json["wizard_bot_draft"]` into the explicit
`bot_versions.test_*` columns. Do not trust timestamps or hashes submitted by
the browser.

- [ ] **Step 4: Add destination management routes**

Implement authenticated, CSRF-protected routes:

```text
GET  /integrations
POST /integrations/destinations
POST /integrations/destinations/{id}/toggle
```

Validate WAHA chat IDs with `^\d+@g\.us$`. The UI may display chat IDs but must
never display the WAHA API key.

- [ ] **Step 5: Run integration and web tests**

Run:

```powershell
uv run pytest tests/integration/test_bot_versions.py tests/integration/test_destinations.py -v -m integration
uv run pytest tests/unit -v
```

Expected: versioning and destination tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add destinations and immutable bot versions"
```

### Task 8: Build The Six-Step Server-Rendered Wizard Shell

**Files:**
- Create: `automation_hub/src/automation_hub/web/forms.py`
- Create: `automation_hub/src/automation_hub/web/routes/bots.py`
- Create: `automation_hub/src/automation_hub/web/templates/base.html`
- Create: `automation_hub/src/automation_hub/web/templates/bots/list.html`
- Create: `automation_hub/src/automation_hub/web/templates/bots/wizard.html`
- Create: `automation_hub/src/automation_hub/web/static/app.css`
- Add: `automation_hub/src/automation_hub/web/static/vendor/htmx.min.js`
- Modify: `automation_hub/src/automation_hub/web/app.py`
- Test: `automation_hub/tests/integration/test_bot_wizard.py`

- [ ] **Step 1: Write wizard navigation and persistence tests**

```python
def test_wizard_source_step_saves_normalized_url(authenticated_client) -> None:
    response = authenticated_client.post(
        "/bots/new/source",
        data={
            "name": "Funneling OLT",
            "source_url": "https://docs.google.com/spreadsheets/d/abc/edit?gid=42#gid=42",
            "csrf_token": authenticated_client.csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/area")


def test_wizard_cannot_skip_required_steps(authenticated_client) -> None:
    response = authenticated_client.get("/bots/new/test")

    assert response.status_code == 303
    assert response.headers["location"].endswith("/source")
```

- [ ] **Step 2: Run the tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_bot_wizard.py -v -m integration
```

Expected: FAIL because wizard routes and templates do not exist.

- [ ] **Step 3: Implement a server-side wizard draft**

Store wizard state in the authenticated server session as a validated partial
dictionary under `wizard_bot_draft`. Implement:

```text
GET/POST /bots/new/source
GET/POST /bots/new/area
GET/POST /bots/new/message
GET/POST /bots/new/destinations
GET/POST /bots/new/schedule
GET      /bots/new/test
POST     /bots/new/reset
```

Each POST validates only its step, persists safe fields, and redirects to the
next step. The final test page builds `BotVersionConfig` and displays all
validation errors.

- [ ] **Step 4: Add local HTMX and accessible templates**

Vendor the minified HTMX asset under `static/vendor/` rather than loading it from
a CDN. Base template requirements:

```html
<meta name="csrf-token" content="{{ csrf_token }}">
<script src="{{ url_for('static', path='vendor/htmx.min.js') }}" defer></script>
<nav aria-label="Primary">...</nav>
<main id="main-content">{% block content %}{% endblock %}</main>
```

Use ordinary form POSTs as the functional baseline; HTMX only improves partial
updates.

- [ ] **Step 5: Verify the wizard**

Run:

```powershell
uv run pytest tests/integration/test_bot_wizard.py -v -m integration
uv run pytest tests/unit -v
uv run ruff check .
```

Expected: required-step and persistence tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add bot creation wizard"
```

## Phase 4: Capture And WAHA Delivery

### Task 9: Implement The Playwright Capture Engine And Visual Crop Selection

**Files:**
- Create: `automation_hub/src/automation_hub/services/artifacts.py`
- Create: `automation_hub/src/automation_hub/services/capture.py`
- Create: `automation_hub/src/automation_hub/web/static/crop-selector.js`
- Create: `automation_hub/tests/fixtures/grid.html`
- Test: `automation_hub/tests/unit/test_artifacts.py`
- Test: `automation_hub/tests/integration/test_capture.py`
- Modify: `automation_hub/src/automation_hub/web/routes/bots.py`
- Modify: `automation_hub/src/automation_hub/web/templates/bots/wizard.html`

- [ ] **Step 1: Write artifact and capture contract tests**

```python
@pytest.mark.asyncio
async def test_capture_returns_exact_crop_dimensions(grid_route, artifact_store) -> None:
    config = ScreenshotConfig(
        source_url="https://docs.google.com/spreadsheets/d/test-sheet/edit?gid=0",
        viewport_width=1200,
        viewport_height=800,
        stabilization_wait_seconds=0,
        crop=CropRect(x=100, y=80, width=500, height=300),
    )

    result = await capture_screenshot(
        config,
        artifact_store,
        page_setup=grid_route,
    )

    assert result.width == 500
    assert result.height == 300
    assert result.path.exists()


def test_artifact_path_cannot_escape_root(tmp_path) -> None:
    store = ArtifactStore(tmp_path)

    with pytest.raises(InvalidArtifactPath):
        store.resolve("../secret.txt")
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run playwright install chromium
uv run pytest tests/unit/test_artifacts.py tests/integration/test_capture.py -v
```

Expected: FAIL because capture and artifact services are missing.

- [ ] **Step 3: Implement artifact storage and capture**

```python
@dataclass(frozen=True)
class CaptureResult:
    relative_path: str
    width: int
    height: int
    bytes_size: int
    sha256: str


async def capture_screenshot(
    config: ScreenshotConfig,
    store: ArtifactStore,
    *,
    page_setup: PageSetup | None = None,
) -> CaptureResult:
    normalized_url = normalize_sheet_url(config.source_url)
    relative_path, absolute_path = store.allocate(".png")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={
                "width": config.viewport_width,
                "height": config.viewport_height,
            },
            device_scale_factor=config.device_scale_factor,
        )
        page = await context.new_page()
        if page_setup is None:
            await install_request_guard(page)
        else:
            await page_setup(page)

        try:
            await page.goto(
                normalized_url,
                wait_until="networkidle",
                timeout=config.navigation_timeout_seconds * 1000,
            )
            normalize_sheet_url(page.url)
            await page.wait_for_timeout(config.stabilization_wait_seconds * 1000)
            validate_crop(config.crop, config.viewport_width, config.viewport_height)
            await page.screenshot(
                path=str(absolute_path),
                clip=config.crop.model_dump(),
                type="png",
            )
        except PlaywrightTimeoutError as exc:
            raise CaptureError(ErrorCode.SHEET_TIMEOUT, "Sheet timed out") from exc
        finally:
            await context.close()
            await browser.close()

    width, height = optimize_png(absolute_path, config.max_dimension)
    payload = absolute_path.read_bytes()
    return CaptureResult(
        relative_path=relative_path,
        width=width,
        height=height,
        bytes_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )
```

Use `page.route("**/*", handler)` to abort requests that violate the URL policy.
Map Playwright timeout and navigation failures to deterministic `ErrorCode`
values. `page_setup` exists only for deterministic tests; production callers
always leave it `None`. The `grid_route` fixture fulfills the exact allowed
Google URL with `tests/fixtures/grid.html`, so tests do not weaken the source
validation contract or require external network access.

Define the test hook type in `capture.py`:

```python
from collections.abc import Awaitable, Callable
from playwright.async_api import Page

PageSetup = Callable[[Page], Awaitable[None]]
```

Top-level navigation and redirects may target only `docs.google.com`. Subresource
requests may additionally target the explicit set
`docs.googleusercontent.com`, `ssl.gstatic.com`, `www.gstatic.com`,
`fonts.googleapis.com`, and `fonts.gstatic.com`; all other hosts are aborted.

- [ ] **Step 4: Implement the browser crop selector**

`crop-selector.js` must:

1. Render the preview at its natural aspect ratio.
2. Track pointer-down/move/up.
3. Clamp selection to preview bounds.
4. Convert rendered CSS pixels back to natural screenshot pixels.
5. Populate hidden `crop_x`, `crop_y`, `crop_width`, and `crop_height` inputs.
6. Reject selections smaller than 20x20 pixels.

Test the conversion as a pure exported function:

```javascript
export function toNaturalRect(rect, rendered, natural) {
  const scaleX = natural.width / rendered.width;
  const scaleY = natural.height / rendered.height;
  return {
    x: Math.round(rect.x * scaleX),
    y: Math.round(rect.y * scaleY),
    width: Math.round(rect.width * scaleX),
    height: Math.round(rect.height * scaleY),
  };
}
```

- [ ] **Step 5: Add preview endpoint**

```text
POST /bots/new/preview
```

The route enqueues or directly invokes a dedicated preview capture with a
strict 120-second request timeout, saves a short-lived artifact, and returns the
preview URL plus natural dimensions. It must not create a production run or send
WhatsApp.

- [ ] **Step 6: Run capture verification**

Run:

```powershell
uv run pytest tests/unit/test_artifacts.py -v
uv run pytest tests/integration/test_capture.py -v
uv run pytest tests/integration/test_bot_wizard.py -v -m integration
```

Expected: exact crop, path safety, and preview flow pass.

- [ ] **Step 7: Commit**

```powershell
git add automation_hub
git commit -m "feat: add visual sheet capture"
```

### Task 10: Add The WAHA Client And Safe Test Delivery

**Files:**
- Create: `automation_hub/src/automation_hub/services/waha.py`
- Modify: `automation_hub/src/automation_hub/web/routes/bots.py`
- Modify: `automation_hub/src/automation_hub/web/templates/bots/wizard.html`
- Test: `automation_hub/tests/unit/test_waha.py`
- Test: `automation_hub/tests/integration/test_test_delivery.py`

- [ ] **Step 1: Write response-classification tests**

```python
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, DeliveryOutcome.SUCCESS),
        (201, DeliveryOutcome.SUCCESS),
        (401, DeliveryOutcome.AUTH_FAILED),
        (404, DeliveryOutcome.DESTINATION_INVALID),
        (429, DeliveryOutcome.RETRYABLE),
        (503, DeliveryOutcome.RETRYABLE),
    ],
)
def test_classify_waha_response(status: int, expected: DeliveryOutcome) -> None:
    assert classify_waha_response(status) is expected


def test_read_timeout_after_request_is_delivery_unknown() -> None:
    assert classify_transport_error(httpx.ReadTimeout("late")) is DeliveryOutcome.UNKNOWN
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_waha.py -v
```

Expected: FAIL because the WAHA client is missing.

- [ ] **Step 3: Implement an injected asynchronous WAHA client**

```python
class WahaClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def send_image(
        self,
        destination_chat_id: str,
        artifact: Path,
        caption: str,
    ) -> DeliveryResult:
        payload = {
            "session": self._settings.waha_session,
            "chatId": destination_chat_id,
            "file": {
                "mimetype": "image/png",
                "filename": artifact.name,
                "data": base64.b64encode(artifact.read_bytes()).decode("ascii"),
            },
            "caption": caption,
        }
        try:
            response = await self._client.post(
                f"{self._settings.waha_url.rstrip('/')}/api/sendImage",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Connection": "close",
                    "X-Api-Key": self._settings.waha_api_key,
                },
                json=payload,
                timeout=60,
            )
        except (httpx.ReadTimeout, httpx.ReadError) as exc:
            return DeliveryResult(
                outcome=DeliveryOutcome.UNKNOWN,
                status_code=None,
                safe_detail=type(exc).__name__,
            )
        except httpx.ConnectError as exc:
            return DeliveryResult(
                outcome=DeliveryOutcome.RETRYABLE,
                status_code=None,
                safe_detail=type(exc).__name__,
            )

        return DeliveryResult(
            outcome=classify_waha_response(response.status_code),
            status_code=response.status_code,
            safe_detail=sanitize_response_body(response.text),
        )
```

Use one new request per attempt with `Connection: close`, matching the reliable
pattern in the legacy scripts.

- [ ] **Step 4: Implement test delivery**

`POST /bots/new/test-delivery` must require:

- A successful preview artifact owned by the current session.
- One enabled destination.
- A rendered caption.
- CSRF token.

Record test evidence in the wizard session:

```python
{
    "capture_test": {"sha256": "...", "passed_at": "..."},
    "delivery_test": {"destination_id": "...", "passed_at": "..."},
}
```

- [ ] **Step 5: Verify all delivery outcomes**

Run:

```powershell
uv run pytest tests/unit/test_waha.py -v
uv run pytest tests/integration/test_test_delivery.py -v -m integration
```

Expected: success, auth failure, retryable failure, and ambiguous timeout cases
all pass without making a real WAHA request.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add safe WAHA image delivery"
```

### Task 11: Enforce Activation Evidence And Bot Lifecycle

**Files:**
- Modify: `automation_hub/src/automation_hub/services/bot_versions.py`
- Modify: `automation_hub/src/automation_hub/web/routes/bots.py`
- Create: `automation_hub/src/automation_hub/web/templates/bots/detail.html`
- Test: `automation_hub/tests/integration/test_bot_lifecycle.py`

- [ ] **Step 1: Write lifecycle tests**

```python
def test_bot_cannot_activate_without_capture_and_delivery_evidence(session, draft_bot) -> None:
    with pytest.raises(ActivationBlocked):
        activate_bot(session, draft_bot.id)


def test_activating_bot_sets_current_version_and_schedule(session, tested_bot_version) -> None:
    activate_bot(session, tested_bot_version.bot_id)

    bot = session.get(Bot, tested_bot_version.bot_id)
    assert bot.status is BotStatus.ACTIVE
    assert bot.current_version_id == tested_bot_version.id


def test_duplicate_bot_creates_draft_without_test_evidence(session, active_bot) -> None:
    duplicate = duplicate_bot(session, active_bot.id)

    assert duplicate.status is BotStatus.DRAFT
    assert duplicate.current_version.test_capture_passed_at is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_bot_lifecycle.py -v -m integration
```

Expected: FAIL because lifecycle functions are missing.

- [ ] **Step 3: Implement lifecycle transitions**

Allowed transitions:

```text
DRAFT -> ACTIVE
ACTIVE -> PAUSED
PAUSED -> ACTIVE
DRAFT|PAUSED -> ARCHIVED
ACTIVE -> ARCHIVED only after explicit confirmation
```

Editing an active bot creates a new draft version. The active version continues
to run until the new version passes both tests and is explicitly promoted.

- [ ] **Step 4: Add authenticated lifecycle routes**

```text
GET  /bots
GET  /bots/{id}
POST /bots/{id}/activate
POST /bots/{id}/pause
POST /bots/{id}/resume
POST /bots/{id}/duplicate
POST /bots/{id}/archive
```

Every mutation requires CSRF and writes an audit event.

- [ ] **Step 5: Run lifecycle and regression tests**

Run:

```powershell
uv run pytest tests/integration/test_bot_lifecycle.py -v -m integration
uv run pytest tests/integration/test_bot_wizard.py -v -m integration
```

Expected: lifecycle tests pass and wizard behavior remains green.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: enforce tested bot activation"
```

## Phase 5: Scheduler, Queue, And Production Runs

### Task 12: Implement Idempotent Scheduler Dispatch

**Files:**
- Create: `automation_hub/src/automation_hub/repositories/runs.py`
- Create: `automation_hub/src/automation_hub/jobs/queue.py`
- Create: `automation_hub/src/automation_hub/services/scheduler.py`
- Create: `automation_hub/src/automation_hub/jobs/scheduler_main.py`
- Test: `automation_hub/tests/integration/test_scheduler.py`

- [ ] **Step 1: Write scheduler idempotency tests**

```python
def test_dispatch_due_schedule_creates_one_run_for_one_occurrence(
    session, queue, due_schedule
) -> None:
    dispatch_due_schedules(session, queue, now=due_schedule.next_run_at)
    dispatch_due_schedules(session, queue, now=due_schedule.next_run_at)

    runs = session.scalars(select(Run)).all()
    assert len(runs) == 1
    assert queue.enqueued_run_ids == [runs[0].id]


def test_dispatch_advances_next_run_in_same_transaction(session, queue, due_schedule) -> None:
    previous = due_schedule.next_run_at

    dispatch_due_schedules(session, queue, now=previous)

    assert due_schedule.next_run_at > previous
```

- [ ] **Step 2: Run scheduler tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_scheduler.py -v -m integration
```

Expected: FAIL because scheduler and queue adapter are missing.

- [ ] **Step 3: Implement transaction-safe dispatch**

Use PostgreSQL row locking:

```python
due = session.scalars(
    select(Schedule)
    .where(Schedule.enabled.is_(True), Schedule.next_run_at <= now)
    .with_for_update(skip_locked=True)
).all()
```

For each schedule, calculate:

```python
occurrence_key = f"{schedule.bot_id}:{schedule.next_run_at.isoformat()}"
```

Insert `Run(status=QUEUED, occurrence_key=...)`, advance `next_run_at`, commit,
then enqueue the committed run ID with deterministic RQ job ID `run:{run_id}`.
If enqueue fails, leave the run queued for the reconciliation loop.

- [ ] **Step 4: Add reconciliation and scheduler heartbeat**

Every scheduler cycle:

1. Dispatch due schedules.
2. Re-enqueue `QUEUED` runs older than 30 seconds that have no RQ job.
3. Write heartbeat timestamp to Redis key `heartbeat:scheduler` with 90-second TTL.
4. Sleep 10 seconds.

- [ ] **Step 5: Run scheduler verification**

Run:

```powershell
docker compose up -d postgres redis
uv run pytest tests/integration/test_scheduler.py -v -m integration
```

Expected: idempotency, advancement, and reconciliation tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add idempotent schedule dispatch"
```

### Task 13: Implement Run Execution, Per-Bot Locking, And Per-Destination Retry

**Files:**
- Create: `automation_hub/src/automation_hub/services/run_executor.py`
- Create: `automation_hub/src/automation_hub/jobs/tasks.py`
- Create: `automation_hub/src/automation_hub/jobs/worker_main.py`
- Test: `automation_hub/tests/unit/test_retry_policy.py`
- Test: `automation_hub/tests/integration/test_run_executor.py`

- [ ] **Step 1: Write the retry policy and partial-success tests**

```python
def test_unknown_delivery_is_never_auto_retried() -> None:
    decision = retry_decision(
        outcome=DeliveryOutcome.UNKNOWN,
        attempts=1,
        max_attempts=3,
    )

    assert decision.retry is False
    assert decision.final_status is DeliveryStatus.UNKNOWN


@pytest.mark.asyncio
async def test_executor_retries_only_failed_destination(
    run_fixture, fake_capture, fake_waha
) -> None:
    fake_waha.results = {
        "group-a@g.us": [DeliveryOutcome.SUCCESS],
        "group-b@g.us": [DeliveryOutcome.RETRYABLE, DeliveryOutcome.SUCCESS],
    }

    await execute_run(run_fixture.id, deps(run_fixture, fake_capture, fake_waha))

    assert fake_waha.calls == ["group-a@g.us", "group-b@g.us", "group-b@g.us"]
    assert load_run(run_fixture.id).status is RunStatus.SUCCESS
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_retry_policy.py tests/integration/test_run_executor.py -v
```

Expected: FAIL because executor and retry policy are missing.

- [ ] **Step 3: Implement explicit state transitions**

`execute_run(run_id)` must:

1. Acquire Redis lock `lock:bot:{bot_id}` with a bounded TTL.
2. If unavailable, mark the run `SKIPPED_OVERLAP`.
3. Load the immutable bot version and enabled destination snapshots.
4. Transition `QUEUED -> CAPTURING`.
5. Capture with at most three bounded attempts.
6. Create one `run_delivery` row per destination.
7. Transition to `SENDING`.
8. Send only destinations not already terminal-success.
9. Derive final status.
10. Release the lock in `finally`.

Use a transition guard:

```python
ALLOWED_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.CAPTURING, RunStatus.SKIPPED_OVERLAP, RunStatus.CANCELLED},
    RunStatus.CAPTURING: {RunStatus.SENDING, RunStatus.FAILED},
    RunStatus.SENDING: {
        RunStatus.SUCCESS,
        RunStatus.PARTIAL_SUCCESS,
        RunStatus.FAILED,
        RunStatus.DELIVERY_UNKNOWN,
    },
}
```

- [ ] **Step 4: Implement retry classification**

Retry capture errors only for timeout and temporary render failures. Retry WAHA
only for explicit `429` and `5xx` responses. Use delays `2`, `5`, and `10`
seconds. Never retry authentication, invalid destination, validation, or unknown
delivery outcomes.

- [ ] **Step 5: Add worker heartbeat and stale-lock protection**

`worker_main.py` starts an RQ worker and updates `heartbeat:worker` every 30
seconds with 90-second TTL. The per-bot lock uses a 120-second TTL and is renewed
every 30 seconds while the run is active. Lock value contains the run ID;
renewal and release use Lua compare-and-expire/compare-and-delete scripts so one
run cannot modify another run's lock.

- [ ] **Step 6: Run executor verification**

Run:

```powershell
uv run pytest tests/unit/test_retry_policy.py -v
uv run pytest tests/integration/test_run_executor.py -v -m integration
```

Expected: overlap, retry, partial success, unknown delivery, and state transition
tests pass.

- [ ] **Step 7: Commit**

```powershell
git add automation_hub
git commit -m "feat: execute isolated bot runs"
```

### Task 14: Add Run History, Manual Run, And Destination Retry UI

**Files:**
- Create: `automation_hub/src/automation_hub/web/routes/runs.py`
- Create: `automation_hub/src/automation_hub/web/templates/runs/detail.html`
- Modify: `automation_hub/src/automation_hub/web/templates/bots/detail.html`
- Test: `automation_hub/tests/integration/test_run_routes.py`

- [ ] **Step 1: Write run-action authorization and safety tests**

```python
def test_manual_run_creates_unique_run(authenticated_client, active_bot) -> None:
    response = authenticated_client.post(
        f"/bots/{active_bot.id}/run-now",
        data={"csrf_token": authenticated_client.csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert count_runs(trigger="MANUAL") == 1


def test_manual_retry_rejects_successful_destination(authenticated_client, successful_delivery) -> None:
    response = authenticated_client.post(
        f"/runs/{successful_delivery.run_id}/deliveries/{successful_delivery.id}/retry",
        data={"csrf_token": authenticated_client.csrf_token},
    )

    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_run_routes.py -v -m integration
```

Expected: FAIL because run routes are missing.

- [ ] **Step 3: Implement run pages and safe actions**

Routes:

```text
POST /bots/{id}/run-now
GET  /runs/{id}
POST /runs/{id}/cancel
POST /runs/{id}/deliveries/{delivery_id}/retry
```

Manual retry is allowed only for `FAILED` or `UNKNOWN` delivery rows and creates a
new delivery attempt record linked to the same destination. It must display a
confirmation warning for `UNKNOWN`.

- [ ] **Step 4: Render the run timeline**

The detail page shows:

- Bot and immutable version.
- Trigger and timestamps.
- State transitions from `run_events`.
- Artifact metadata and preview when retained.
- One delivery card per destination.
- Attempt history, safe-retry indicator, and sanitized response.

- [ ] **Step 5: Run route regression tests**

Run:

```powershell
uv run pytest tests/integration/test_run_routes.py -v -m integration
uv run pytest tests/integration/test_run_executor.py -v -m integration
```

Expected: manual run and retry safety tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add run history and manual controls"
```

## Phase 6: OpenAI Assistance

### Task 15: Add Structured OpenAI Configuration Drafting

**Files:**
- Create: `automation_hub/src/automation_hub/domain/ai.py`
- Create: `automation_hub/src/automation_hub/services/openai_service.py`
- Modify: `automation_hub/src/automation_hub/web/routes/bots.py`
- Modify: `automation_hub/src/automation_hub/web/templates/bots/wizard.html`
- Test: `automation_hub/tests/unit/test_ai_schemas.py`
- Test: `automation_hub/tests/integration/test_ai_draft.py`

- [ ] **Step 1: Write strict AI schema tests**

```python
def test_bot_draft_rejects_unknown_destination() -> None:
    draft = BotDraft(
        suggested_name="OLT",
        source_url=None,
        caption_template="Report",
        destination_names=["Invented Group"],
        schedule=AiDailySchedule(times=["08:00"]),
        assumptions=[],
        missing_fields=[],
    )

    with pytest.raises(UnknownDestinationName):
        validate_destination_allowlist(draft, ["Testing"])
```

At the service boundary, validate destination names against the exact enabled
allowlist supplied to the request.

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_ai_schemas.py tests/integration/test_ai_draft.py -v
```

Expected: FAIL because AI schemas and service are missing.

- [ ] **Step 3: Implement Responses API Structured Outputs**

```python
class OpenAIService:
    def __init__(self, settings: Settings, client: OpenAI) -> None:
        self._settings = settings
        self._client = client

    def create_bot_draft(
        self,
        instruction: str,
        destination_names: list[str],
    ) -> BotDraft:
        response = self._client.responses.parse(
            model=self._settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Create a screenshot-bot draft only from supported fields. "
                        "Never invent destination names, IDs, secrets, or activation state."
                    ),
                },
                {
                    "role": "user",
                    "content": build_draft_prompt(instruction, destination_names),
                },
            ],
            text_format=BotDraft,
        )
        if response.output_parsed is None:
            raise AppError(ErrorCode.OPENAI_INVALID_OUTPUT, "AI did not return a draft")
        return validate_destination_allowlist(response.output_parsed, destination_names)
```

Limit instruction length to 4,000 characters and output fields through Pydantic.

- [ ] **Step 4: Merge AI output only into editable wizard fields**

`POST /bots/new/ai-draft`:

- Requires auth and CSRF.
- Sends no secret, chat ID, screenshot, or credential.
- Writes name, source URL, caption, selected destination names, and schedule into
  the server-side draft.
- Never sets crop, test evidence, active status, or IDs directly.
- Displays assumptions and missing fields.

- [ ] **Step 5: Verify valid, refused, malformed, and unavailable responses**

Run:

```powershell
uv run pytest tests/unit/test_ai_schemas.py -v
uv run pytest tests/integration/test_ai_draft.py -v -m integration
```

Expected: all response classes map to user-safe results without blocking manual
wizard use.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add structured AI bot drafting"
```

### Task 16: Add Sanitized AI Failure Analysis

**Files:**
- Modify: `automation_hub/src/automation_hub/domain/ai.py`
- Modify: `automation_hub/src/automation_hub/services/openai_service.py`
- Modify: `automation_hub/src/automation_hub/web/routes/runs.py`
- Modify: `automation_hub/src/automation_hub/web/templates/runs/detail.html`
- Test: `automation_hub/tests/unit/test_failure_analysis.py`
- Test: `automation_hub/tests/integration/test_failure_analysis_route.py`

- [ ] **Step 1: Write the sanitization boundary test**

```python
def test_failure_analysis_payload_contains_no_secrets(run_with_secret_like_logs) -> None:
    payload = build_failure_analysis_payload(run_with_secret_like_logs)
    encoded = payload.model_dump_json()

    assert "Bearer " not in encoded
    assert "X-Api-Key" not in encoded
    assert "waha-secret" not in encoded
    assert len(payload.events) <= 20
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/unit/test_failure_analysis.py -v
```

Expected: FAIL because analysis payload and response are missing.

- [ ] **Step 3: Implement bounded analysis schemas**

```python
class FailureAnalysis(BaseModel):
    summary: str = Field(max_length=1000)
    possible_causes: list[str] = Field(max_length=5)
    confidence: Literal["low", "medium", "high"]
    checks: list[str] = Field(max_length=8)
    escalation: str | None = Field(default=None, max_length=1000)
```

The request contains only error code, stage, safe metadata, and the latest 20
redacted run events. The response is advisory text only.

- [ ] **Step 4: Add the explicit analysis action**

```text
POST /runs/{id}/analyze
```

The route:

- Requires auth and CSRF.
- Refuses successful runs.
- Calls OpenAI only on explicit user action.
- Stores the analysis result and model name in a dedicated run event.
- Does not retry, edit, or send anything.

- [ ] **Step 5: Run analysis tests**

Run:

```powershell
uv run pytest tests/unit/test_failure_analysis.py -v
uv run pytest tests/integration/test_failure_analysis_route.py -v -m integration
```

Expected: sanitization and advisory-only route tests pass.

- [ ] **Step 6: Commit**

```powershell
git add automation_hub
git commit -m "feat: add sanitized AI failure analysis"
```

## Phase 7: Operations, Deployment, And Pilot

### Task 17: Add Dashboard Metrics, Health Checks, And Retention Cleanup

**Files:**
- Create: `automation_hub/src/automation_hub/services/health.py`
- Create: `automation_hub/src/automation_hub/web/routes/dashboard.py`
- Create: `automation_hub/src/automation_hub/web/templates/dashboard/index.html`
- Modify: `automation_hub/src/automation_hub/web/app.py`
- Modify: `automation_hub/src/automation_hub/jobs/tasks.py`
- Test: `automation_hub/tests/integration/test_dashboard.py`
- Test: `automation_hub/tests/integration/test_health.py`
- Test: `automation_hub/tests/unit/test_retention.py`

- [ ] **Step 1: Write metrics, health, and retention tests**

```python
def test_dashboard_counts_today_results(authenticated_client, seeded_runs) -> None:
    response = authenticated_client.get("/")

    assert response.status_code == 200
    assert "4 active" in response.text
    assert "1 failed" in response.text


def test_ready_fails_when_worker_heartbeat_is_missing(client, redis_client) -> None:
    redis_client.delete("heartbeat:worker")

    response = client.get("/health/ready")

    assert response.status_code == 503


def test_retention_deletes_expired_artifact_but_keeps_run_record(tmp_path, expired_run) -> None:
    cleanup_expired_artifacts(now=expired_run.expires_at + timedelta(seconds=1))

    assert not expired_run.artifact_path.exists()
    assert load_run(expired_run.id) is not None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
uv run pytest tests/integration/test_dashboard.py tests/integration/test_health.py tests/unit/test_retention.py -v
```

Expected: FAIL because dashboard, readiness, and cleanup are missing.

- [ ] **Step 3: Implement readiness checks**

`/health/live` checks process liveness only. `/health/ready` checks:

- PostgreSQL `SELECT 1`.
- Redis `PING`.
- Scheduler heartbeat younger than 90 seconds.
- Worker heartbeat younger than 90 seconds.
- WAHA session health when WAHA is configured.

Return structured component results and HTTP 503 if any required component fails.

- [ ] **Step 4: Implement dashboard queries**

Return:

- Active/paused/attention-required bot counts.
- Today's success, partial, unknown, and failed run counts.
- Next run across active schedules.
- Latest run per bot.
- Direct links to failed run details.

Keep dashboard queries in one repository method using bounded subqueries rather
than per-bot queries.

- [ ] **Step 5: Implement daily cleanup**

Enqueue `cleanup_expired_artifacts` daily. It deletes files only under
`ARTIFACT_ROOT`, nulls artifact path metadata, preserves hashes and run rows, and
records cleanup events. Default retention is seven days; structured run logs are
pruned after 30 days.

- [ ] **Step 6: Run operations verification**

Run:

```powershell
uv run pytest tests/integration/test_dashboard.py tests/integration/test_health.py -v -m integration
uv run pytest tests/unit/test_retention.py -v
```

Expected: metrics, readiness, and cleanup tests pass.

- [ ] **Step 7: Commit**

```powershell
git add automation_hub
git commit -m "feat: add operations dashboard and retention"
```

### Task 18: Containerize, Document aaPanel Deployment, Add Backup Restore, And Prove The Pilot Flow

**Files:**
- Create: `automation_hub/Dockerfile`
- Create: `automation_hub/docker/entrypoint-web.sh`
- Create: `automation_hub/docker/entrypoint-worker.sh`
- Create: `automation_hub/docker/nginx-aaPanel.example.conf`
- Create: `automation_hub/scripts/backup_postgres.sh`
- Create: `automation_hub/scripts/restore_postgres.sh`
- Create: `automation_hub/scripts/import_legacy_bot.py`
- Create: `automation_hub/tests/e2e/test_bot_pilot.py`
- Modify: `automation_hub/compose.yaml`
- Modify: `automation_hub/README.md`
- Modify: `automation_hub/.env.example`

- [ ] **Step 1: Write the complete pilot E2E test**

```python
@pytest.mark.e2e
def test_admin_can_create_test_activate_and_run_bot(
    browser,
    fake_google_sheet,
    fake_waha,
) -> None:
    login(browser)
    create_destination(browser, name="Testing", chat_id="120363000000000000@g.us")
    start_bot_wizard(browser, name="OLT Pilot", source_url=fake_google_sheet.url)
    select_crop(browser, x=80, y=48, width=360, height=150)
    set_caption(browser, "Funneling OLT {date}")
    set_daily_schedule(browser, "08:00")
    run_capture_test(browser)
    run_delivery_test(browser, destination="Testing")
    activate_bot(browser)
    run_now(browser)

    assert_run_status(browser, "SUCCESS")
    assert fake_waha.received_count == 1
```

- [ ] **Step 2: Run E2E test to verify the environment is incomplete**

Run:

```powershell
docker compose up -d --build
uv run pytest tests/e2e/test_bot_pilot.py -v -m e2e
```

Expected: FAIL until container services and E2E fixtures are wired.

- [ ] **Step 3: Build one multi-stage image with separate commands**

The final Compose services:

```yaml
services:
  web:
    build: .
    command: ["docker/entrypoint-web.sh"]
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    volumes:
      - artifacts:/data/artifacts

  scheduler:
    build: .
    command: ["python", "-m", "automation_hub.jobs.scheduler_main"]
    env_file: .env
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}

  worker:
    build: .
    command: ["docker/entrypoint-worker.sh"]
    env_file: .env
    shm_size: "1gb"
    volumes:
      - artifacts:/data/artifacts

  postgres:
    image: postgres:17
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
```

Expose only the web port to the host. Do not publish PostgreSQL or Redis.

- [ ] **Step 4: Add aaPanel reverse-proxy and secret instructions**

The Nginx example must include:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

client_max_body_size 10m;
```

README deployment sequence:

1. Create a new VPS directory.
2. Copy `.env.example` to `.env`.
3. Generate `APP_SECRET_KEY` with `openssl rand -hex 32`.
4. Add rotated WAHA and OpenAI credentials.
5. Run `docker compose up -d --build`.
6. Run Alembic migration.
7. Bootstrap the admin interactively.
8. Configure aaPanel reverse proxy and HTTPS.
9. Verify `/health/ready`.

- [ ] **Step 5: Implement backup and guarded restore**

`backup_postgres.sh` creates a timestamped compressed custom-format dump and
retains the latest seven files. `restore_postgres.sh` requires:

```text
RESTORE_CONFIRM=I_UNDERSTAND_THIS_REPLACES_AUTOMATION_DATA
```

before dropping/recreating application data. Document and test restore against a
throwaway Compose database, never production.

- [ ] **Step 6: Implement one-way legacy bot import**

`import_legacy_bot.py` accepts explicit command arguments for non-secret values:

```text
--name
--source-url
--crop-x --crop-y --crop-width --crop-height
--viewport-width --viewport-height
--caption
--destination-name
--daily-time
```

It creates a `DRAFT` bot only. It never reads or imports API keys from legacy
scripts and never activates the bot.

- [ ] **Step 7: Run the full quality gate**

Run:

```powershell
uv run ruff check .
uv run mypy src
uv run pytest tests/unit -v
uv run pytest tests/integration -v -m integration
uv run pytest tests/e2e/test_bot_pilot.py -v -m e2e
docker compose config
docker compose build
docker compose up -d
docker compose ps
```

Expected:

- Ruff and mypy exit 0.
- Unit, integration, and pilot E2E suites have zero failures.
- Compose config and build exit 0.
- `web`, `scheduler`, `worker`, `postgres`, and `redis` are healthy/running.

- [ ] **Step 8: Perform the manual pilot checklist**

Use one newly rotated test WAHA credential and a test WhatsApp group:

1. Create the OLT-style bot from the dashboard.
2. Compare preview dimensions and content with the existing script output.
3. Verify one test delivery.
4. Run the dashboard schedule in observation mode without production delivery.
5. Enable production delivery.
6. Disable only the matching cron entry.
7. Keep the legacy script and rollback command documented.
8. Record seven consecutive days of successful scheduled runs before migrating
   another screenshot bot.

- [ ] **Step 9: Commit**

```powershell
git add automation_hub
git commit -m "feat: deploy automation hub pilot"
```

## Final Verification Matrix

| Approved Requirement | Proving Task/Test |
| --- | --- |
| New isolated project folder | Task 1, all paths under `automation_hub/` |
| Single admin authentication | Task 5 auth flow |
| Public Google Sheet only and SSRF controls | Tasks 3 and 9 |
| Visual crop selection | Task 9 capture and JS conversion |
| One crop, multiple WAHA destinations | Tasks 6, 7, 10 |
| Test required before activation | Tasks 10 and 11 |
| Daily times and fixed intervals | Tasks 6 and 12 |
| Idempotent scheduling | Task 12 unique occurrence test |
| No overlapping production runs | Task 13 Redis lock test |
| Per-destination retry without duplicate success sends | Task 13 executor test |
| Ambiguous response never auto-retried | Tasks 10 and 13 |
| Run history and manual retry | Task 14 |
| OpenAI `gpt-5.4` config draft | Task 15 |
| Sanitized advisory-only failure analysis | Task 16 |
| Dashboard and health | Task 17 |
| Seven-day artifact and 30-day log retention | Task 17 |
| aaPanel/Docker deployment | Task 18 |
| Backup and tested restore | Task 18 |
| Gradual pilot migration without changing other bots | Task 18 |

## Completion Gate

Do not call the MVP complete until:

```powershell
uv run ruff check .
uv run mypy src
uv run pytest tests/unit -v
uv run pytest tests/integration -v -m integration
uv run pytest tests/e2e -v -m e2e
docker compose config
docker compose build
```

all exit 0, the backup restore drill succeeds against a disposable database, and
the pilot bot has seven consecutive days of successful scheduled production
runs.
