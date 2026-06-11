# Visual Bot Builder Design

**Date:** 2026-06-11
**Status:** Approved for implementation planning

## 1. Goal

Build a single-admin web dashboard that replaces duplicated Python screenshot
scripts and per-bot crontab entries with centrally managed, configuration-driven
automation.

The MVP supports one workflow:

```text
Public Google Sheet -> Playwright screenshot/crop -> WAHA image delivery
```

The application runs continuously on an Ubuntu VPS managed through aaPanel.

## 2. Project Grounding

The repository currently contains 27 primary Python scripts. Most screenshot
senders repeat the same implementation with different values for:

- Google Sheet URL, GID, range, or screenshot coordinates.
- Browser viewport and wait time.
- Image crop and resize settings.
- WhatsApp group destinations and captions.
- Schedule and retry behavior.

The dominant existing workflow families are:

1. Public Google Sheet to screenshot to WhatsApp.
2. Google Sheet data to formatted WhatsApp text.
3. Telegram listener to transformed state, WhatsApp, or Google Sheet.

The MVP only generalizes the first family. Existing text and Telegram bots remain
unchanged.

The repository also contains hardcoded WAHA and Telegram credentials in tracked
Python files. Those credentials must be rotated before production migration.
The new application must never store secrets in source code or bot
configuration.

## 3. Product Decisions

- Product foundation: configuration-driven builder, not generated Python.
- User model: one admin account.
- Hosting: one always-on Ubuntu VPS with aaPanel.
- Source: publicly accessible Google Sheets only.
- Output: one WAHA server/session with one or more destination groups per bot.
- Screenshot: one visual crop area per bot.
- Scheduling: daily times and fixed intervals.
- AI provider: OpenAI.
- Default model: `gpt-5.4`, configurable through `OPENAI_MODEL`.
- AI features: configuration drafting and failure analysis.
- Activation: test screenshot and test delivery must succeed first.

## 4. Architecture

```text
Browser
  |
  v
FastAPI web application
  |-- Server-rendered dashboard and wizard
  |-- Authentication and session handling
  |-- Bot configuration/version management
  |-- Preview and test-run endpoints
  |-- OpenAI configuration and analysis endpoints
  |
  +--> PostgreSQL
  |      Bots, versions, schedules, runs, deliveries, audit events
  |
  +--> Redis / RQ
         Job queue, per-bot locks, retry dispatch

Scheduler service
  |-- Finds due schedules
  |-- Creates deduplicated run records
  +-- Enqueues run IDs

Worker service
  |-- Loads immutable bot version
  |-- Captures and crops with Playwright
  |-- Optimizes image
  |-- Sends per destination through WAHA
  +-- Writes structured run results
```

The web process does not perform production screenshots or WhatsApp sends
inline. Heavy or retryable work runs in the worker.

## 5. Technology Stack

- Python 3.12.
- FastAPI for HTTP routes and backend services.
- Jinja templates with HTMX for the dashboard and wizard.
- Small dedicated JavaScript module for visual crop selection.
- PostgreSQL for durable application state.
- Redis and RQ for asynchronous jobs and locks.
- Playwright Chromium for preview and production capture.
- Pillow for optional image resizing and format optimization.
- SQLAlchemy and Alembic for persistence and migrations.
- Argon2 password hashing and server-side secure sessions.
- Pytest for unit, integration, browser-fixture, and end-to-end tests.

React and a node-based workflow editor are intentionally excluded from the MVP.

## 6. Dashboard Information Architecture

Primary navigation:

- Dashboard
- My Bots
- Run History
- Integrations
- AI Assistant
- Settings

The dashboard displays:

- Active, paused, and attention-required bot counts.
- Success, partial-success, and failed runs for the current day.
- Next scheduled run.
- Last-run status and duration per bot.
- Direct links to failure details and AI analysis.

Each bot detail page provides:

- Current status and schedule.
- Source, crop, caption, and destination summary.
- Last successful screenshot preview.
- Configuration version history.
- Test, run now, pause, resume, duplicate, and edit actions.
- Recent run and destination delivery history.

## 7. Bot Creation Wizard

The wizard has six steps:

1. **Source**
   - Bot name.
   - Public Google Sheet URL.
   - Optional Indonesian instruction for AI draft generation.
2. **Area**
   - Load a preview using the production browser configuration.
   - Drag a rectangle over the preview.
   - Store `x`, `y`, `width`, `height`, viewport, and device scale factor.
3. **Message**
   - Caption template.
   - Preview resolved date/time placeholders.
4. **Destinations**
   - Select one or more registered WAHA groups.
5. **Schedule**
   - One or more daily times, or one fixed interval.
   - Display timezone `Asia/Jakarta`.
6. **Test**
   - Capture a real preview.
   - Send to a selected test destination.
   - Show exact image, caption, timing, and response.

The bot remains `DRAFT` until both capture and delivery tests succeed.
Activation is always an explicit admin action.

## 8. Screenshot Configuration

Each bot version stores:

- Canonical public Sheet URL.
- Target GID when present.
- Viewport width and height.
- Device scale factor.
- Page navigation timeout.
- Post-load stabilization wait.
- Crop rectangle in viewport pixels.
- Output type, defaulting to PNG.
- Maximum image dimension and compression policy.
- Caption template.

Preview and production runs use the same browser and screenshot configuration.
This prevents the selected crop from shifting between the wizard and worker.

Only one crop is allowed per bot in the MVP. Multiple reports should be created
by duplicating the bot and selecting another crop.

## 9. Public URL Security

The screenshot worker is a server-side browser and therefore creates an SSRF
risk. The application must:

- Accept only HTTPS URLs.
- Allowlist public Google Sheet hosts and supported URL forms.
- Reject IP literals, localhost, private network ranges, and unsupported ports.
- Revalidate every redirect and limit redirect count.
- Normalize the URL before storing it.
- Prevent browser access to local files and internal service addresses.
- Apply navigation, page-size, and execution time limits.

Arbitrary website screenshot automation is outside the MVP.

## 10. Data Model

### `users`

- Admin identity.
- Argon2 password hash.
- Last login and password-change timestamps.

### `bots`

- Stable bot identity.
- Name and description.
- Status: `DRAFT`, `ACTIVE`, `PAUSED`, or `ARCHIVED`.
- Current version ID.

### `bot_versions`

- Immutable version number.
- Complete validated screenshot and caption configuration.
- Creator and creation timestamp.
- Test-capture and test-delivery evidence.

### `destinations`

- Friendly group name.
- WAHA chat ID.
- Enabled status.

The WAHA API key is not stored here.

### `bot_version_destinations`

- Ordered destinations for a bot version.

### `schedules`

- Trigger type: `DAILY_TIMES` or `FIXED_INTERVAL`.
- Time values or interval duration.
- Timezone.
- Next due time in UTC.
- Enabled status.

### `runs`

- Run ID and bot version snapshot.
- Trigger type: scheduled, manual, or test.
- Scheduled time and actual timestamps.
- State and final result.
- Unique schedule occurrence key.
- Capture artifact metadata and sanitized error.

### `run_deliveries`

- One row per run and destination.
- Attempt count.
- Status and timestamps.
- Sanitized WAHA response metadata.

### `run_events`

- Structured chronological events for diagnostics and audit.

## 11. Scheduling and Idempotency

The scheduler evaluates due schedules using UTC internally and
`Asia/Jakarta` for user input and display.

For every due occurrence:

1. Lock or claim the schedule row.
2. Create a run using a unique key derived from bot ID and scheduled time.
3. Advance `next_run_at`.
4. Enqueue only the run ID.

The unique key prevents duplicate jobs if the scheduler restarts or two
scheduler loops overlap.

Only one production run may execute per bot at a time. A Redis lock protects
the worker. If the next occurrence arrives while the prior run is active, the
new occurrence is recorded as `SKIPPED_OVERLAP`; it is not silently lost.

Arbitrary cron expressions are outside the MVP.

## 12. Run State Machine

Run states:

```text
QUEUED
  -> CAPTURING
  -> SENDING
  -> SUCCESS | PARTIAL_SUCCESS | FAILED | DELIVERY_UNKNOWN
```

Additional terminal states:

- `SKIPPED_OVERLAP`
- `CANCELLED`

The worker loads the immutable bot version referenced by the run. Editing a bot
while it is queued cannot change that run.

## 13. Retry and Duplicate-Delivery Protection

Capture and source loading may retry up to three times with bounded backoff.

Delivery is tracked independently for every destination:

- A successful destination is never sent again during the same run.
- Validation and authentication failures are not retried.
- Explicit transient responses such as rate limiting or service unavailable may
  retry within the configured limit.
- Connection reset, read timeout, or other failures after a request may have
  reached WAHA are marked `DELIVERY_UNKNOWN`.
- `DELIVERY_UNKNOWN` is never automatically retried because WAHA does not
  provide an application-level idempotency guarantee.
- The admin may inspect WhatsApp and choose a manual retry for that destination.

This is more conservative than the current scripts, some of which treat an
ambiguous disconnect as success.

## 14. Error Handling

Deterministic application error codes include:

- `SOURCE_INVALID`
- `SOURCE_BLOCKED`
- `SHEET_TIMEOUT`
- `SHEET_RENDER_FAILED`
- `CROP_OUT_OF_BOUNDS`
- `CAPTURE_FAILED`
- `IMAGE_PROCESSING_FAILED`
- `WAHA_AUTH`
- `WAHA_SESSION_UNAVAILABLE`
- `DESTINATION_INVALID`
- `WAHA_RATE_LIMITED`
- `DELIVERY_FAILED`
- `DELIVERY_UNKNOWN`
- `OPENAI_UNAVAILABLE`
- `OPENAI_INVALID_OUTPUT`

Every error records:

- Stage and code.
- User-safe message.
- Sanitized technical detail.
- Attempt number and duration.
- Whether retry is safe.

OpenAI failure never blocks normal screenshot scheduling or delivery.

## 15. OpenAI Integration

The application uses the OpenAI Responses API.

Environment:

```text
OPENAI_API_KEY=<server secret>
OPENAI_MODEL=gpt-5.4
```

### Configuration assistant

Input:

- User instruction, limited in length.
- Supported bot capabilities.
- Existing destination names, not hidden credentials.
- Current timezone and default limits.

Output uses strict Structured Outputs matching `BotDraft`:

- Suggested name.
- Public Sheet URL when provided by the user.
- Caption.
- Selected existing destination names.
- Daily times or fixed interval.
- Assumptions and missing required fields.

The server validates the response again using the same domain model used by the
manual wizard. AI cannot invent a destination ID, activate a bot, select the
final crop, or bypass a test.

### Failure analyst

The deterministic classifier runs first. OpenAI receives only:

- Error code and stage.
- Sanitized structured metadata.
- A small bounded set of relevant sanitized log events.
- Bot capability metadata without secrets.

The structured response contains:

- Plain-language summary.
- Possible causes.
- Confidence.
- Ordered checks.
- Escalation guidance.

It cannot execute shell commands, edit configuration, trigger retries, or send
messages.

Screenshots are not sent to OpenAI by default.

OpenAI is called only when the admin requests a draft or analysis, not on every
scheduled run.

Official design references:

- [OpenAI model selection](https://developers.openai.com/api/docs/models)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Safety best practices](https://developers.openai.com/api/docs/guides/safety-best-practices)
- [API key safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)

## 16. Secrets and Authentication

The browser never receives OpenAI or WAHA API keys.

Production secrets are injected into containers through server environment or
Docker secrets:

- `OPENAI_API_KEY`
- `OPENAI_MODEL=gpt-5.4`
- `WAHA_URL`
- `WAHA_SESSION`
- `WAHA_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- Initial admin setup secret

Secrets are excluded from logs, database bot records, image artifacts, API
responses, and AI requests.

The single admin uses:

- Argon2 password hashing.
- Secure, HTTP-only, same-site session cookies.
- CSRF protection on mutations.
- Login rate limiting.
- Session invalidation after password changes.

Before deployment, rotate all credentials currently hardcoded in tracked
scripts. Do not reuse leaked values in the new application.

## 17. Deployment on aaPanel

Docker Compose services:

- `web`
- `scheduler`
- `worker`
- `postgres`
- `redis`

aaPanel Nginx terminates HTTPS and reverse-proxies only to `web`.
PostgreSQL and Redis are accessible only through the private Compose network.

The worker image includes the supported Playwright Chromium build and required
fonts. Web and scheduler images do not need browser dependencies.

Persistent volumes:

- PostgreSQL data.
- Short-lived screenshot artifacts.
- Application logs when not shipped to another log service.

Health checks cover:

- Web readiness.
- Scheduler heartbeat.
- Worker heartbeat and queue connectivity.
- PostgreSQL and Redis.
- WAHA health/session status.

## 18. Retention and Backup

Defaults:

- Production screenshot artifacts: 7 days.
- Test and debug artifacts: 7 days.
- Structured run logs: 30 days.
- Bot versions and delivery summaries: retained until bot deletion policy is
  introduced.

PostgreSQL is backed up daily through aaPanel or a dedicated backup job.
Restore instructions and a restore test are required before production cutover.

## 19. Testing

### Unit tests

- URL normalization and SSRF rejection.
- Bot configuration validation.
- Crop bounds and viewport consistency.
- Caption rendering.
- Schedule calculations across timezone boundaries.
- Run idempotency keys.
- Retry classification.
- Log and response redaction.
- AI Structured Output validation.

### Integration tests

- PostgreSQL transactions and unique run constraints.
- Redis queue and per-bot locks.
- Scheduler dispatch.
- Worker state transitions.
- Mock WAHA success, partial success, auth failure, rate limit, and ambiguous
  disconnect.
- Mock OpenAI valid, refused, malformed, timeout, and unavailable responses.

### Browser fixture tests

A deterministic local grid page verifies:

- Preview and production crop equality.
- Viewport changes.
- Out-of-bounds handling.
- Screenshot dimensions and image optimization.

### End-to-end tests

- Login.
- Create bot manually.
- Create AI draft.
- Select crop.
- Test capture.
- Test delivery.
- Activate and schedule.
- Inspect successful and failed history.
- Pause, resume, duplicate, and manual retry.

## 20. Migration Plan

Migration is gradual:

1. Deploy the dashboard without changing current cron jobs.
2. Register WAHA and OpenAI secrets with newly rotated values.
3. Convert one representative screenshot script, starting with an OLT-style
   public Sheet bot.
4. Compare the dashboard screenshot against the existing script.
5. Test delivery to a test WhatsApp group.
6. Run the dashboard schedule without production delivery for an observation
   period.
7. Enable production delivery and disable only that bot's cron entry.
8. Keep the old script available as a documented rollback during stabilization.
9. Repeat for other screenshot scripts.

Telegram listeners and text-report bots remain on their current runtime until a
later design cycle.

## 21. MVP Scope

Included:

- Single-admin login.
- Destination registry.
- Public Google Sheet source.
- Visual crop selection.
- Screenshot preview and test delivery.
- Daily-time and fixed-interval schedules.
- Multi-destination WAHA delivery.
- Pause, resume, duplicate, run now, and manual destination retry.
- Run history, delivery history, health status, and sanitized logs.
- OpenAI configuration drafting and failure analysis using `gpt-5.4`.

Excluded:

- Private Google Sheet access.
- Telegram listeners.
- Sheet data parsing and text report generation.
- Multiple crops in one bot.
- Arbitrary website screenshots.
- Free-form cron expressions.
- Node-based workflow editor.
- Multi-user roles.
- AI-generated Python or shell execution.
- Automatic AI remediation.

## 22. Acceptance Criteria

The MVP is ready for pilot when:

- An admin can create and activate a screenshot bot without editing Python or
  crontab.
- Preview and production crop dimensions match for the same configuration.
- A scheduled run starts within one minute of its expected time under normal
  load.
- Scheduler restart does not create duplicate runs for one occurrence.
- A successful destination is not resent when another destination fails.
- Ambiguous WAHA responses never trigger automatic duplicate delivery.
- Every run has a clear state, timeline, destination result, and safe retry
  indication.
- AI output cannot bypass server validation, tests, or explicit activation.
- No production secret appears in source, database bot config, logs, browser
  payloads, or AI requests.
- Database backup and restore have been tested.
- The pilot bot runs reliably for seven consecutive days before broader
  migration.
