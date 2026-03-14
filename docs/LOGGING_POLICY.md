# Logging Policy

This document defines what must never appear in logs, which log levels are
safe for production, and how to sanitize sensitive data before logging.

---

## SENSITIVE Fields — Must Never Appear in Logs

The following field name patterns must never be logged in plaintext:

| Pattern        | Examples                                              |
|----------------|-------------------------------------------------------|
| `DATABASE_URL` | `DATABASE_URL=postgresql://user:pass@host/db`         |
| `API_KEY`      | `NEARBLOCKS_API_KEY`, `COINGECKO_API_KEY`             |
| `SECRET`       | `JWT_SECRET`, `SECRET_KEY`, `APP_SECRET`              |
| `TOKEN`        | `SESSION_TOKEN`, `ACCESS_TOKEN`, `REFRESH_TOKEN`      |
| `PASSWORD`     | `DB_PASSWORD`, `ADMIN_PASSWORD`                       |
| `CREDENTIAL`   | `AWS_CREDENTIALS`, `GCP_CREDENTIAL_FILE`              |

These patterns are enforced case-insensitively. Any dict key whose uppercase
form contains one of the above strings is considered sensitive.

**Rule:** Never log full connection strings, API keys, tokens, passwords, or
any credential directly. Always sanitize first.

---

## Using sanitize_for_log()

`config.py` exports a `sanitize_for_log()` helper that redacts sensitive fields:

```python
from config import sanitize_for_log

# Before logging env vars or config dicts:
safe = sanitize_for_log({"DATABASE_URL": "postgres://secret", "user_id": 42})
logger.info("Config: %s", safe)
# Logs: Config: {'DATABASE_URL': '***REDACTED***', 'user_id': 42}
```

**Always** pass config dicts through `sanitize_for_log()` before any log call.

**Never** use `f"Connecting to {DATABASE_URL}"` directly in a log statement.

---

## Safe Log Levels for Production

| Level     | Safe for production | Notes                                          |
|-----------|---------------------|------------------------------------------------|
| `DEBUG`   | No                  | May contain raw request/response bodies        |
| `INFO`    | Yes (with care)     | Must not include sensitive field values        |
| `WARNING` | Yes                 | Operational warnings; no sensitive data        |
| `ERROR`   | Yes                 | Exception messages; avoid logging stack frames with credentials |
| `CRITICAL`| Yes                 | Reserved for unrecoverable failures            |

**Production log level:** Set `LOG_LEVEL=INFO` or `LOG_LEVEL=WARNING` in the
container environment. `DEBUG` is only for local development.

---

## What IS Safe to Log

- User IDs (integer primary keys, not email or name)
- Wallet addresses (public blockchain addresses are public)
- Job IDs and job types
- Transaction counts and amounts (not connected to identifiable users in isolation)
- Error codes and HTTP status codes
- Timing and performance metrics

---

## What is NEVER Safe to Log

- Full `DATABASE_URL` connection strings (contain password)
- API keys (`NEARBLOCKS_API_KEY`, `COINGECKO_API_KEY`, etc.)
- Session tokens or JWT tokens
- User passwords (even hashed)
- Full HTTP request bodies that may contain credentials
- Private keys or mnemonics

---

## Enforcement

`_SENSITIVE_KEY_PATTERNS` in `config.py` is the canonical list of sensitive
patterns. If you add a new sensitive field type, add its pattern there.

See also: `config.sanitize_for_log()` in `config.py`.
