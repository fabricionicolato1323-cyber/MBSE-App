from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

MODULE = Path(__file__).resolve().parents[1] / "sam_level1_scenario_incremental.py"


def stub(name, **attrs):
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


class SamLevel1SyncError(RuntimeError):
    pass


class SamSettings:
    project_id = "p"


def rows(value):
    return [x for x in value or [] if isinstance(x, dict)]


def fingerprint(value):
    import hashlib, json
    return hashlib.sha256(
        json.dumps(sorted(value, key=lambda x: json.dumps(x, sort_keys=True)),
                   sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


# This test loads the candidate module against lightweight dependency stubs.
# Preserve and restore the real application modules so pytest collection of this
# file cannot contaminate any test modules collected afterwards.
_STUBBED_MODULE_NAMES = (
    "sam_connection",
    "sam_level1_communication_incremental",
    "sam_level1_direct",
    "sam_level1_incremental",
    "sam_level1_managed_direct",
    "sam_level1_sync",
    "sam_level1_transactional",
    "sam_reload_safe_factory",
)
_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULE_NAMES}

try:
    stub("sam_connection", SamSettings=SamSettings)
    stub("sam_level1_communication_incremental",
         build_incremental_plan_with_communication=lambda *a, **k: {},
         sync_level1_incremental_with_communication=lambda *a, **k: {})
    stub("sam_level1_direct", _MetadataTolerantFactory=lambda x: x)
    stub("sam_level1_incremental", SYNC_STATE_VERSION=2,
         _delete_owned_tree=lambda *a, **k: None, _descendants=lambda *a, **k: [],
         _managed_instance=lambda *a, **k: None, _scenario_fingerprint=fingerprint)
    stub("sam_level1_managed_direct", _library_status=lambda *a, **k: {})
    stub("sam_level1_sync", SamLevel1SyncError=SamLevel1SyncError,
         _documentation=lambda *a, **k: None, _rows=rows,
         level1_snapshot_digest=lambda *a, **k: "digest")
    stub("sam_level1_transactional",
         _element_id=lambda x: getattr(x, "id", None),
         _element_name=lambda x: getattr(x, "name", ""),
         _load_project=lambda *a, **k: (None, None, None, None))
    stub("sam_reload_safe_factory", ReloadSafeFactory=lambda *a, **k: None)

    spec = importlib.util.spec_from_file_location("scenario_candidate", MODULE)
    m = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(m)
finally:
    for name, original in _saved_modules.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def scenario(name="Patrol", sid="scenario-1", exchange="Target report"):
    return {
        "id": sid,
        "name": name,
        "valid": True,
        "steps": [
            {"kind": "activity", "activity_id": "a1"},
            {"kind": "interaction", "exchange_name": exchange,
             "source_activity_id": "a1", "target_activity_id": "a2"},
            {"kind": "activity", "activity_id": "a2"},
        ],
    }


def state(row):
    return {
        "scenarios": {
            m.scenario_identity(row): {
                "sam_id": "sam-1", "name": row["name"], "source": m._source(row)
            }
        }
    }


def test_create_rename_replace_delete_delta():
    old = scenario()
    base = state(old)
    rename = m.scenario_change_set([scenario(name="Patrol renamed")], base)
    assert rename["update"][0]["change_kind"] == "rename"
    replace = m.scenario_change_set([scenario(exchange="Confirmed report")], base)
    assert replace["update"][0]["change_kind"] == "replace"
    add = m.scenario_change_set([old, scenario("Second", "scenario-2")], base)
    assert add["counts"]["create"] == 1
    delete = m.scenario_change_set([], base)
    assert delete["counts"]["delete"] == 1


class Factory:
    def __init__(self):
        self.n = 0
        self.calls = []

    def new(self, kind, **kwargs):
        self.n += 1
        x = SimpleNamespace(id=f"id-{self.n}", name=kwargs.get("name"))
        self.calls.append((kind, kwargs, x))
        return x

    def create_action_usage(self, **kwargs):
        return self.new("action", **kwargs)

    def create_flow_connection_usage(self, **kwargs):
        return self.new("flow", **kwargs)

    def create_succession(self, **kwargs):
        return self.new("succession", **kwargs)


def test_sam_tree_preserves_activity_exchange_activity_path():
    factory = Factory()
    model = {"nodes": [
        {"id": "a1", "type": "OperationalActivity", "name": "Detect"},
        {"id": "a2", "type": "OperationalActivity", "name": "Report"},
    ]}
    result = m._create_tree(
        factory, SimpleNamespace(), {
            "OperationalScenario": SimpleNamespace(),
            "OperationalActivity": SimpleNamespace(),
            "OperationalExchange": SimpleNamespace(),
        }, model, scenario(), "__stage__"
    )
    kinds = [kind for kind, _, _ in factory.calls]
    assert kinds.count("action") == 3
    assert kinds.count("flow") == 1
    assert kinds.count("succession") == 1
    assert [item["name"] for item in result["expected"]] == [
        "1. Detect", "3. Report", "2. Target report"
    ]
    assert all(item["sam_id"] for item in result["expected"])


def test_scenario_id_is_stable_across_rename():
    assert m.scenario_identity(scenario("A")) == m.scenario_identity(scenario("B"))
