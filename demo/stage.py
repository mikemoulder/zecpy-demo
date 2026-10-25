"""Everything the scenes act on: the regtest chain, the miner that plays every other
participant, and two leak-audit proxies (one in front of ZecPy, one in front of
zcash-devtool) whose every recorded request goes to the browser as it happens.

The SDK checkout supplies `tools.devnet` and `tools.leak_audit`; point ZEC_REPO at it.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

ZEC_REPO = Path(os.environ.get("ZEC_REPO", Path(__file__).resolve().parents[2] / "zec"))
sys.path.insert(0, str(ZEC_REPO))

from tools.devnet import DEV, LWD, Devnet, activation_heights, rpc  # noqa: E402
from tools.leak_audit import AuditProxy  # noqa: E402
from tools.leak_audit.proxy import Record  # noqa: E402

from .hub import Hub  # noqa: E402

UPSTREAM = LWD.removeprefix("http://")


def _detail(record: Record) -> str:
    """One line of what the request asked for, as the server sees it."""
    req = record.request
    if record.method == "GetTransaction" and "hash" in req:
        import base64

        return base64.b64decode(req["hash"])[::-1].hex()
    if record.method == "GetTreeState" and "height" in req:
        return f"height {req['height']}"
    if record.method == "GetBlockRange":
        start = req.get("start", {}).get("height", "?")
        end = req.get("end", {}).get("height", "?")
        return f"blocks {start} to {end}"
    if record.method in ("GetAddressUtxos", "GetAddressUtxosStream", "GetTaddressTxids", "GetTaddressBalance"):
        addresses = req.get("addresses") or [req.get("address")]
        return ", ".join(a for a in addresses if a)[:120]
    if record.method == "SendTransaction":
        return f"{req.get('data_bytes', '?')} bytes"
    return ""


class Stage:
    def __init__(self, hub: Hub, root: Path) -> None:
        self.hub = hub
        self.root = root
        self.devnet = Devnet(server=LWD, heights=activation_heights())
        self.zecpy_proxy = AuditProxy("127.0.0.1:0", UPSTREAM, on_record=self._on("zecpy"))
        self.devtool_proxy = AuditProxy("127.0.0.1:0", UPSTREAM, on_record=self._on("devtool"))
        self.lock = asyncio.Lock()

    def _on(self, actor: str):
        def record(r: Record) -> None:
            self.hub.publish(
                "audit", actor=actor, method=r.method, label=r.label.value, reason=r.reason, detail=_detail(r)
            )

        return record

    async def start(self) -> None:
        rpc("getblockcount")  # fails fast when devnet is down
        self.root.mkdir(parents=True, exist_ok=True)
        await self.zecpy_proxy.start()
        await self.devtool_proxy.start()

    async def stop(self) -> None:
        await self.zecpy_proxy.stop()
        await self.devtool_proxy.stop()

    def wallet_dir(self, name: str) -> Path:
        return self.root / f"{name}-{int(time.time() * 1000)}"

    # Other participants are the devnet miner wallet (zcash-devtool), talking to the
    # server directly: their traffic is not the wallet under test.

    async def pay(self, address: str, zat: int, memo: str | None = None) -> None:
        await asyncio.to_thread(self.devnet.pay, address, zat, memo)

    async def mine(self, n: int = 1) -> int:
        height = await asyncio.to_thread(self.devnet.mine, n)
        self.hub.publish("chain", height=height)
        return height

    @property
    def devtool_bin(self) -> Path:
        return DEV / "bin" / "zcash-devtool"
