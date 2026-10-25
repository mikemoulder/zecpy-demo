# ZecPy Live (demo repo)

The demo for ZecPy, the SDK in `/home/coder/zec` (read its CLAUDE.md; its rules apply here).
Scenes in `demo/scenes.py` drive real ZecPy on devnet; `demo/static/` is the page, built to
the design-taste-frontend app rules (style data-terminal, seed 617959318, gold accent).

- Run: `source ../zec/.venv/bin/activate && uvicorn demo.server:app --port 8077`
- Test: `pytest -q` (needs devnet up). Check the page: `inspect.mjs --app "http://127.0.0.1:8077/?replay=instant"`
- Commit as xerodahdev <xero.dev.ai@gmail.com>, HTTPS remote, no AI attribution, no em dashes.
- Never claim the page shows Tor: the proxies are on loopback.
