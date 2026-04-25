# Contributing to NetInspect

Thanks for your interest in contributing! Here's everything you need to get started.

## Before You Start

- Check the [Roadmap](https://github.com/ivillagomez/netinspect/wiki/Roadmap) to see what's already planned
- Search [existing issues](https://github.com/ivillagomez/netinspect/issues) to avoid duplicates
- For larger changes, open an issue first to discuss the approach before writing code

## Development Setup

### Requirements
- Python 3.11+
- Docker (optional, for testing the container build)

### Run locally

```bash
git clone https://github.com/ivillagomez/netinspect.git
cd netinspect
pip install -r requirements.txt
python run.py
```

Open **http://localhost:8080** → Settings → add your devices → Save.

### Project structure

```
backend/
  main.py              # FastAPI app, routes, middleware
  config.py            # Pydantic config models
  connectors/          # One file per vendor integration
  tracer/              # Path-walk algorithm + diagnostics
  discovery/           # CDP/LLDP auto-discovery engine
frontend/
  index.html
  js/app.js            # All UI logic
  css/style.css
docs/                  # Documentation
```

## Adding a New Vendor Integration

1. Create `backend/connectors/<vendor>.py` — implement the standard interface:
   - `async def get_mac_table(mac: str) -> dict`
   - `async def get_neighbors(port: str) -> list`
2. Add a config model in `backend/config.py`
3. Wire it into `backend/tracer/mac_tracer.py`
4. Add it to the Settings UI in `frontend/index.html` + `frontend/js/app.js`
5. Document it in `docs/configuration.md` and the wiki

## Code Style

- Python: follow PEP 8, use type hints where practical
- Keep functions focused — one responsibility per function
- Log with `logger.info/warning/error`, never `print()`
- Never log credential values — only exception class names
- All user-supplied data rendered in `innerHTML` must go through `esc()` (XSS prevention)
- Port/interface names interpolated into SSH commands must go through `_safe_port()` (injection prevention)

## Submitting a Pull Request

1. Fork the repo and create a branch: `git checkout -b feat/your-feature`
2. Make your changes with clear, focused commits
3. Test against real devices if possible, or document what was tested
4. Open a PR against `master` — fill in the PR template
5. Keep PRs focused — one feature or fix per PR

## Sensitive Information

- Never commit credentials, API keys, or real device IPs
- `config.yaml` is gitignored — keep it that way
- If you need to share a config snippet, use placeholder values

## Questions?

Open a discussion in [Q&A](https://github.com/ivillagomez/netinspect/discussions/categories/q-a) rather than an issue.
