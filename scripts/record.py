"""Runs every scene against devnet and saves the event stream as the page's replay file
(`/?replay`). Run as `python -m scripts.record`, so the page can be shown and checked without a live chain. Real events only."""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from demo.hub import Hub
from demo.scenes import SCENES
from demo.stage import Stage

OUT = Path(__file__).resolve().parents[1] / "demo" / "static" / "replay.json"


async def main(order: list[str]) -> None:
    hub = Hub(keep=100_000)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Stage(hub, Path(tmp))
        await stage.start()
        hub.publish("chain", height=stage.devnet.height())
        try:
            for name in order:
                await SCENES[name](stage)
        finally:
            await stage.stop()
    OUT.write_text(json.dumps([json.loads(line) for line in hub._history], indent=0))
    print(f"{len(hub._history)} events -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["checkout", "control", "memos", "agent", "cold"]))
