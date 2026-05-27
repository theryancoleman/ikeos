# Obsidian Capture

Web app for capturing notes, ideas, and bugs against homelab projects

## Quick Start

1. Copy `.env.example` to `.env` and fill in values
2. Run: `docker compose up -d`
3. Access at: `http://192.168.1.77:5009`

## Development

```bash
docker compose up --build
docker compose logs -f
```

## Environment

See `.env.example` for all required variables.
