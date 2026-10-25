"""The demo's scenes. Each runs real ZecPy against the regtest chain, narrates its steps to
the browser, and ends with what the light server learned while it ran."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from zecpy import PrivacyError, Wallet
from zecpy.cold import ColdSigner, describe

from .stage import ZEC_REPO, Stage

ZAT = 100_000_000


def zec(zat: int) -> str:
    return f"{zat / ZAT:.8f}".rstrip("0").rstrip(".") + " ZEC"


@dataclass
class Scene:
    stage: Stage
    name: str
    _start: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._start = {
            "zecpy": len(self.stage.zecpy_proxy.records),
            "devtool": len(self.stage.devtool_proxy.records),
        }
        self.stage.hub.publish("scene", scene=self.name, state="start")

    def step(self, text: str, status: str = "ok", **data: object) -> None:
        self.stage.hub.publish("step", scene=self.name, text=text, status=status, **data)

    def identifying(self, actor: str = "zecpy") -> int:
        proxy = self.stage.zecpy_proxy if actor == "zecpy" else self.stage.devtool_proxy
        return sum(1 for r in proxy.records[self._start[actor]:] if r.label.value == "identifying")

    def requests(self, actor: str = "zecpy") -> int:
        proxy = self.stage.zecpy_proxy if actor == "zecpy" else self.stage.devtool_proxy
        return len(proxy.records) - self._start[actor]

    def done(self, **data: object) -> None:
        self.stage.hub.publish(
            "scene", scene=self.name, state="done",
            requests=self.requests(), identifying=self.identifying(), **data,
        )


async def _wallet(stage: Stage, name: str) -> Wallet:
    wallet, _mnemonic = await Wallet.create(
        stage.wallet_dir(name), network="regtest", server=stage.zecpy_proxy.url,
        regtest_heights=stage.devnet.heights,
    )
    return wallet


async def _merchant(stage: Stage, scene: Scene) -> Wallet:
    if getattr(stage, "merchant", None) is None:
        scene.step("Shop backend creates a ZecPy wallet", status="run")
        stage.merchant = await _wallet(stage, "shop")
        scene.step("Shop wallet ready: no seed on disk, 24 words handed to the caller once")
    return stage.merchant


async def _funded(stage: Stage, scene: Scene, name: str, zat: int) -> Wallet:
    wallet = await _wallet(stage, name)
    await stage.pay(wallet.address(), zat)
    await stage.mine(10)
    await wallet.sync()
    scene.step(f"{name.capitalize()} wallet funded with {zec(zat)}", balance=wallet.balance().spendable)
    return wallet


async def _settle(stage: Stage, scene: Scene, shop: Wallet, reference: str) -> None:
    """Syncs the shop until its invoice is confirmed, narrating each event."""
    for _ in range(4):
        await shop.sync()
        for event in shop.invoices.poll(confirmations=3):
            if event.invoice.reference != reference:
                continue
            scene.step(
                f"payment.{event.state}: {zec(event.value_zat)} for {reference}",
                status="ok" if event.state == "confirmed" else "run",
                txid=event.txid, confirmations=event.confirmations,
            )
            if event.state == "confirmed":
                return
        await stage.mine(1)
    raise RuntimeError(f"{reference} did not confirm")


async def checkout(stage: Stage) -> None:
    scene = Scene(stage, "checkout")
    shop = await _merchant(stage, scene)
    invoice = shop.invoices.create(150_000, "order-77")
    scene.step(
        f"Invoice order-77 for {zec(invoice.amount_zat)}: its own shielded address",
        address=invoice.address, uri=invoice.uri,
    )
    scene.step("Customer pays from their own wallet", status="run")
    await stage.pay(invoice.address, invoice.amount_zat)
    scene.step("Payment mined. The shop matches it by address during trial decryption: no memo, no lookup")
    await _settle(stage, scene, shop, "order-77")
    scene.done()


async def control(stage: Stage) -> None:
    """zcash-devtool, the reference wallet on the same librustzcash crates, doing a wallet's
    first two steps through its own audit proxy."""
    scene = Scene(stage, "control")
    wallet = stage.wallet_dir("devtool")
    server = stage.devtool_proxy.listen
    heights = str(ZEC_REPO / "devnet" / "activation-heights.toml")

    async def devtool(*args: str, stdin: bytes = b"") -> None:
        proc = await asyncio.create_subprocess_exec(
            str(stage.devtool_bin), *args,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await asyncio.wait_for(proc.communicate(stdin), timeout=600)
        if proc.returncode != 0:
            raise RuntimeError(err.decode()[-500:])

    scene.step("zcash-devtool creates a wallet", status="run")
    await devtool(
        "wallet", "-w", str(wallet), "init", "--name", "control", "--identity", str(wallet) + ".age",
        "-n", "regtest", "--activation-heights", heights, "-s", server, stdin=b"\n",
    )
    scene.step("zcash-devtool syncs", status="run")
    await devtool("wallet", "-w", str(wallet), "sync", "-s", server)
    leaks = scene.identifying("devtool")
    scene.step(f"The server could identify this wallet from {leaks} requests", status="refused")
    stage.hub.publish(
        "scene", scene="control", state="done",
        requests=scene.requests("devtool"), identifying=leaks,
    )


async def memos(stage: Stage) -> None:
    scene = Scene(stage, "memos")
    shop = await _merchant(stage, scene)
    memo = "Thanks! Order 78: two espressos, no sugar"
    address = shop.invoices.create(90_000, "order-78").address
    others = (stage.devnet.devtool("list-addresses") or "").split()
    bystander = next((w for w in others if w.startswith("uregtest")), None)
    if bystander is None:
        raise RuntimeError("cannot find a miner address for bystander payments")

    scene.step("Eight other people pay each other in the same block as our customer", status="run")
    payments = [(bystander, 10_000 + 1_000 * i, None) for i in range(8)] + [(address, 90_000, memo)]
    random.shuffle(payments)
    await asyncio.to_thread(_send_all, stage, payments)
    await stage.mine(1)
    await shop.sync()
    [tx] = [t for t in shop.transactions() if any(o.address == address for o in t.outputs)]
    scene.step("Payment found, but compact blocks carry no memo text", memo_pending=tx.memo_pending)

    scene.step("fetch_memos(): the real fetch goes out among 7 decoys", status="run")
    report = await shop.fetch_memos(decoys=7, max_delay=0)
    stage.hub.publish("secret", scene="memos", real_txid=tx.txid)
    fetched = shop.transaction(tx.txid).outputs
    text = next((o.memo for o in fetched if o.memo), None)
    scene.step(
        f"Memo decrypted locally: “{text}”" if text else "Memo waiting for more cover",
        status="ok" if report.fetched else "run",
        fetched=report.fetched, waiting=report.waiting,
    )
    scene.done(decoys=7)


def _send_all(stage: Stage, payments: list[tuple[str, int, str | None]]) -> None:
    """Many miner payments into the next block: the chain traffic decoys come from."""
    stage.devnet.devtool("sync", "-s", "127.0.0.1:19067")
    for address, zat, memo in payments:
        extra = ["--memo", memo] if memo else []
        stage.devnet.devtool(
            "send", "-i", "miner.age", "--address", address, "--value", str(zat), "-s", "127.0.0.1:19067", *extra
        )


async def agent(stage: Stage) -> None:
    scene = Scene(stage, "agent")
    shop = await _merchant(stage, scene)
    bot = await _funded(stage, scene, "agent", 1_000_000)
    invoice = shop.invoices.create(125_000, "api-call-4411")
    scene.step("The shop hands the agent a payment link", uri=invoice.uri)
    request = bot.parse_request(invoice.uri)
    scene.step(f"Agent reads it: {zec(request.total)} to one shielded address")

    try:
        await bot.pay(invoice.uri, max_zat=100_000)
        raise RuntimeError("an over-budget link was paid")
    except PrivacyError as refused:
        scene.step(f"pay(max_zat=100_000) refused: {refused}", status="refused")
    scene.step("Budget raised to 0.002 ZEC: pay(max_zat=200_000)", status="run")
    txid = await bot.pay(invoice.uri, max_zat=200_000)
    scene.step("Paid, proved and signed on the agent's machine", txid=txid)
    await stage.mine(1)
    await _settle(stage, scene, shop, "api-call-4411")
    scene.done()


async def cold(stage: Stage) -> None:
    scene = Scene(stage, "cold")
    heights = stage.devnet.heights
    signer, _mnemonic = ColdSigner.generate(network="regtest", regtest_heights=heights)
    scene.step("Offline machine generates the seed; only a viewing key leaves it")
    hot = await Wallet.watch(
        stage.wallet_dir("hot"), signer.watch_bundle(), server=stage.zecpy_proxy.url, regtest_heights=heights
    )
    scene.step(f"Server imports the viewing key. can_send = {hot.can_send}")
    await stage.pay(hot.address(), 1_000_000)
    await stage.mine(10)
    await hot.sync()
    scene.step(f"Server sees {zec(hot.balance().spendable)} it cannot spend")

    shop = await _merchant(stage, scene)
    scene.step("Server builds and proves a refund as an unsigned PCZT", status="run")
    pczt = await asyncio.to_thread(hot.propose_cold, shop.address(), 200_000)
    summary = await asyncio.to_thread(signer.inspect, pczt)
    scene.step("Signer checks it against its own key before signing", summary=describe(summary))
    signed = await asyncio.to_thread(signer.sign, pczt)
    txid = await hot.broadcast_signed(signed)
    await stage.mine(1)
    scene.step("Signed offline, broadcast by the server", txid=txid)
    scene.done()


SCENES: dict[str, Callable[[Stage], Awaitable[None]]] = {
    "checkout": checkout,
    "control": control,
    "memos": memos,
    "agent": agent,
    "cold": cold,
}
