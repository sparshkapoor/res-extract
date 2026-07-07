import asyncio
from dataclasses import dataclass
from pathlib import Path

import pytest

from app.models import Ingredient
from app.pipeline import vlm
from app.pipeline.vlm import _select_hero, _split_generic_ingredient


def test_select_hero_picks_highest_confidence_true_result():
    candidates = [Path("hero_0.jpg"), Path("hero_1.jpg"), Path("hero_2.jpg")]
    results = {
        "hero:0": {"is_hero_shot": True, "confidence": "low"},
        "hero:1": {"is_hero_shot": True, "confidence": "high"},
        "hero:2": {"is_hero_shot": False, "confidence": "high"},
    }
    assert _select_hero(candidates, results) == Path("hero_1.jpg")


def test_select_hero_ignores_non_hero_results_regardless_of_confidence():
    candidates = [Path("hero_0.jpg"), Path("hero_1.jpg")]
    results = {
        "hero:0": {"is_hero_shot": False, "confidence": "high"},
        "hero:1": {"is_hero_shot": True, "confidence": "low"},
    }
    # is_hero_shot=True wins over a "high" confidence False result — the
    # boolean gate matters more than confidence, which only breaks ties
    # among candidates the VLM actually marked as hero shots.
    assert _select_hero(candidates, results) == Path("hero_1.jpg")


def test_select_hero_returns_none_when_no_results():
    assert _select_hero([Path("hero_0.jpg")], {}) is None


def test_split_generic_ingredient_preserves_quantity_shape():
    generic = Ingredient(name="spices", quantity=None, unit=None, name_is_generic=True)
    split = _split_generic_ingredient(generic, ["paprika", "cumin"])
    assert [i.name for i in split] == ["paprika", "cumin"]
    assert all(i.is_estimated and not i.name_is_generic for i in split)
    assert all(i.quantity is None and i.unit is None for i in split)


# --- _VlmWorkerManager (WS5) --------------------------------------------
# Exercised against tests/fixtures/fake_vlm_worker.py, a lightweight
# stand-in that speaks the same ready-handshake/JSONL-serve-loop protocol
# as the real worker but needs no mlx_vlm/model — fast and portable.

_FAKE_WORKER = Path(__file__).parent / "fixtures" / "fake_vlm_worker.py"


@dataclass
class _FakeSettings:
    vlm_model_name: str = "fake-model"
    vlm_ready_timeout_seconds: float = 5.0
    vlm_idle_check_interval_seconds: float = 0.05
    vlm_idle_timeout_seconds: float = 0.15
    vlm_request_timeout_seconds: float = 5.0


@pytest.fixture
def manager(monkeypatch):
    monkeypatch.setattr(vlm, "_WORKER_SCRIPT", _FAKE_WORKER)
    monkeypatch.setattr(vlm, "get_settings", lambda: _FakeSettings())
    return vlm._VlmWorkerManager()


@pytest.mark.asyncio
async def test_ready_handshake_and_call(manager):
    results = await manager.call([{"id": "a"}, {"id": "b"}])
    assert results == [{"id": "a", "echo": True}, {"id": "b", "echo": True}]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_crash_mid_batch_raises_after_respawn_and_retry_both_crash(manager):
    # The retry resends the identical (still crash-triggering) batch, so
    # this is the "still broken after the one allowed retry" path.
    with pytest.raises(vlm.VlmError):
        await manager.call([{"id": "a", "crash": True}])
    await manager.shutdown()


@pytest.mark.asyncio
async def test_worker_crash_respawns_and_retry_succeeds(manager):
    # Simulates an unexpected crash (not the request's fault, e.g. an OOM)
    # by killing the worker out-of-band, then sending a normal batch — the
    # write to the dead process's stdin fails, which should trigger the
    # same kill+respawn+retry path, and this retry succeeds since the
    # batch itself is clean.
    await manager.call([{"id": "a"}])
    manager._proc.kill()
    await manager._proc.wait()

    results = await manager.call([{"id": "b"}])

    assert results == [{"id": "b", "echo": True}]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_manager_usable_again_after_a_permanent_failure(manager):
    with pytest.raises(vlm.VlmError):
        await manager.call([{"id": "a", "crash": True}])
    # A later, unrelated call should spawn a fresh worker rather than
    # staying wedged in the failed state.
    results = await manager.call([{"id": "b"}])
    assert results == [{"id": "b", "echo": True}]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_idle_timeout_unloads_worker(manager):
    await manager.call([{"id": "a"}])
    assert manager._proc is not None
    await asyncio.sleep(0.4)  # well past the fake idle_timeout (0.15s) + check interval
    assert manager._proc is None
    await manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_terminates_worker(manager):
    await manager.call([{"id": "a"}])
    assert manager._proc is not None
    await manager.shutdown()
    assert manager._proc is None


@pytest.mark.asyncio
async def test_shutdown_without_any_call_is_a_noop(manager):
    await manager.shutdown()  # never spawned anything — must not raise
