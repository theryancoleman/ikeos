---
paths:
  - "**/*.py"
---
# Python Project Structure

## Layer Separation

Organize by domain module with clear layers:

```
project_name/
├── app/
│   ├── __init__.py          # App factory
│   ├── routes/              # API endpoints — thin handlers only
│   ├── services/            # Business logic — no framework imports
│   ├── db/
│   │   ├── connection.py    # Connection pool setup
│   │   └── queries/         # All SQL/ORM access by domain
│   ├── templates/           # Jinja2 templates (if applicable)
│   └── static/              # CSS, JS, images
├── workflows/               # Orchestration only — calls services, no logic
├── tests/
│   ├── conftest.py          # Shared fixtures
│   └── test_{module}/       # Mirror source structure
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env                     # Never committed
```

## Layer Responsibilities
- **routes/**: Parse request, call service, return response. No business logic.
- **services/**: Pure Python business logic. No framework objects (`request`, `g`, `current_app`).
- **db/queries/**: All database access. No raw SQL in routes or services.
- **workflows/**: Orchestrate service calls. Contain no logic themselves.

## Rules
- One responsibility per file. Keep modules focused.
- Place shared utilities in a `common/` package.
- Use `conftest.py` for shared test fixtures.
- Prefer `pyproject.toml` over `setup.py` for project metadata.
- Mirror source structure under `tests/`.
