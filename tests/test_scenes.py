"""Every scene runs end to end against devnet, and its privacy claims hold."""

import json

import pytest

from demo.hub import Hub
from demo.scenes import SCENES
from demo.stage import Stage, rpc


@pytest.fixture
async def stage(tmp_path):
    try:
        rpc("getblockcount")
    except OSError:
        pytest.skip("devnet is not running")
    hub = Hub()
    s = Stage(hub, tmp_path)
    await s.start()
    yield s
    await s.stop()


def _events(stage, kind, **match):
    out = [json.loads(line) for line in stage.hub._history]
    return [e for e in out if e["type"] == kind and all(e.get(k) == v for k, v in match.items())]


@pytest.mark.parametrize("name", ["checkout", "memos", "agent", "cold"])
async def test_zecpy_scene_reveals_nothing_identifying_in_the_clear(stage, name):
    await SCENES[name](stage)
    [done] = _events(stage, "scene", scene=name, state="done")
    if name == "memos":
        # The memo fetch is the one identifying request type, and only among decoys.
        fetches = [e for e in _events(stage, "audit", actor="zecpy") if e["method"] == "GetTransaction"]
        [secret] = _events(stage, "secret", scene="memos")
        assert len(fetches) == 8 and secret["real_txid"] in {e["detail"] for e in fetches}
        assert done["identifying"] == 8
    else:
        assert done["identifying"] == 0, _events(stage, "audit", actor="zecpy")


async def test_control_scene_catches_devtool(stage):
    await SCENES["control"](stage)
    [done] = _events(stage, "scene", scene="control", state="done")
    assert done["identifying"] > 0
