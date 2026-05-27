---
paths:
  - "**/*.py"
---
# Python Best Practices (3.11+)

## Type Hints
- Annotate all function parameters and return types. Use `-> None` explicitly.
- Use built-in generics: `list[str]`, `dict[str, int]` — not `typing.List`, `typing.Dict`.
- Use `X | None` instead of `Optional[X]`. Use `X | Y` instead of `Union[X, Y]`.

## Data Modeling
- Pydantic `BaseModel` for API request/response schemas with validation.
- `dataclasses` for internal data structures without validation needs.
- `@dataclass(frozen=True)` for immutable records.
- Avoid plain dictionaries for structured data — use typed models.

## Functions
- Keep functions short and focused (~20 lines of logic max).
- Use keyword-only arguments for 3+ parameters: `def func(*, name, age, email)`.
- Prefer returning values over mutating arguments.
- Prefer comprehensions over `map()`/`filter()`.

## Resources
- Always use `with` statements for files, connections, and locks.
- Use `pathlib.Path` instead of `os.path`.
- Use `asyncio.to_thread()` for blocking calls in async code.

## Imports
- Group: stdlib → third-party → local, separated by blank lines.
- Use absolute imports. Avoid wildcard imports.
