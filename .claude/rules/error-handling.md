---
paths:
  - "**/*.py"
---
# Python Error Handling

## Exception Hierarchy
- Create a base `ApplicationError(Exception)` for all domain-specific errors.
- Create specific exceptions per domain (e.g., `OrderNotFoundError`). Name with `Error` suffix.
- Keep hierarchy shallow — max 2-3 levels deep.
- Include meaningful messages and relevant context attributes.

## Handling
- Never use bare `except:` — always catch specific types.
- Never silently swallow exceptions (`except: pass`).
- Use `except Exception` only at the top-level error boundary.
- Re-raise with context: `raise NewError("message") from original_error`.
- Use `else` for code that runs only if no exception occurred.
- Use `finally` for cleanup that must always execute.

## Logging
- Use the `logging` module. Never `print()` for error reporting.
- `logger.exception("message")` inside `except` blocks to capture traceback.
- `logger.warning()` for business rule violations.
- `logger.error()` for unexpected failures.
- Include structured context (IDs, parameters) in log messages.

## API Error Responses
- Return standardized error responses with `type`, `title`, and `detail` fields.
- Map domain exceptions to HTTP status codes at the route layer, not in services.

## Validation
- Use Pydantic for input validation at API boundaries.
- Validate at the boundary, not deep inside business logic.
