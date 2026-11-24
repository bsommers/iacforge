import json

import pytest

from iacforge import core
from iacforge.engines.base import ProcResult
from iacforge.engines.terraform import TerraformEngine
from iacforge.errors import EngineError, NotConfirmedError, ToolMissingError
from iacforge.render import bind
from iacforge.spec import parse_spec

SPEC = {
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "t1"},
    "spec": {"provider": "local", "engine": "opentofu", "resources": [
        {"name": "my-file", "type": "file", "properties": {"path": "out/a.txt", "content": "hi\n"}}]},
}


def bound(engine="opentofu"):
    return bind(parse_spec(SPEC), engine)


class Fake:
    """Fake Runner: records calls; responses keyed by first arg after the binary."""

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, args, cwd, env=None, timeout=None):
        self.calls.append((list(args), cwd, env))
        r = self.responses.get(args[1], ProcResult(0, "", ""))
        return r(args) if callable(r) else r

    @property
    def verbs(self):
        return [c[0][1] for c in self.calls]


def which_of(*present):
    return lambda n: f"/bin/{n}" if n in present else None


PLAN_JSON = json.dumps({"resource_changes": [
    {"address": "local_file.my_file", "change": {"actions": ["create"]}},
    {"address": "local_file.b", "change": {"actions": ["update"]}},
    {"address": "local_file.c", "change": {"actions": ["delete", "create"]}},
    {"address": "local_file.d", "change": {"actions": ["no-op"]}},
]})


def test_binary_selection(monkeypatch):
    monkeypatch.delenv("IACFORGE_TF_BINARY", raising=False)
    both = which_of("tofu", "terraform")
    assert TerraformEngine("opentofu", which=both).binary() == "/bin/tofu"
    assert TerraformEngine("terraform", which=both).binary() == "/bin/terraform"
    assert TerraformEngine("opentofu", which=which_of("terraform")).binary() == "/bin/terraform"
    assert TerraformEngine("terraform", which=which_of("tofu")).binary() == "/bin/tofu"
    monkeypatch.setenv("IACFORGE_TF_BINARY", "mytf")
    assert TerraformEngine("opentofu", which=which_of("mytf", "tofu")).binary() == "/bin/mytf"


def test_missing_binary(tmp_path, monkeypatch):
    monkeypatch.delenv("IACFORGE_TF_BINARY", raising=False)
    e = TerraformEngine("opentofu", runner=Fake(), which=which_of())
    with pytest.raises(ToolMissingError) as ei:
        e.plan(bound(), tmp_path)
    assert ei.value.exit_code == 3
    assert e.tool_status()["available"] is False


def test_render_writes_main_tf_json(tmp_path):
    e = TerraformEngine("opentofu", runner=Fake(), which=which_of("tofu"))
    res = e.render(bound(), tmp_path / "deep" / "wd")
    assert res == {"files": ["main.tf.json"]}
    doc = json.loads((tmp_path / "deep" / "wd" / "main.tf.json").read_text())
    assert "my_file" in doc["resource"]["local_file"]


def test_plan_sequence_and_parsing(tmp_path, monkeypatch):
    monkeypatch.delenv("IACFORGE_TF_BINARY", raising=False)
    f = Fake({"plan": ProcResult(2, "Plan: 2 to add", ""), "show": ProcResult(0, PLAN_JSON, "")})
    e = TerraformEngine("opentofu", runner=f, which=which_of("tofu"))
    out = e.plan(bound(), tmp_path)
    assert f.verbs == ["init", "plan", "show"]
    assert out["changes"] == {"add": 2, "change": 1, "destroy": 1}
    assert [r["address"] for r in out["resources"]] == ["local_file.my_file", "local_file.b", "local_file.c"]
    assert out["has_changes"] is True
    plan_args = f.calls[1][0]
    assert "-detailed-exitcode" in plan_args and "-out=tfplan" in plan_args and "-no-color" in plan_args
    assert f.calls[0][2]["TF_IN_AUTOMATION"] == "1"
    assert f.calls[0][1] == tmp_path


def test_init_cached(tmp_path):
    f = Fake({"plan": ProcResult(0, "", ""), "show": ProcResult(0, "{}", "")})
    e = TerraformEngine("opentofu", runner=f, which=which_of("tofu"))
    (tmp_path / ".terraform.lock.hcl").write_text("")
    e.plan(bound(), tmp_path)
    e.plan(bound(), tmp_path)
    assert f.verbs.count("init") == 1  # second plan skips init


def test_apply_and_outputs_mapping(tmp_path):
    outs = json.dumps({"my_file__path": {"value": "/x/a.txt"}, "my_file__id": {"value": "abc"}})
    f = Fake({"apply": ProcResult(0, "Apply complete! Resources: 1 added, 0 changed, 0 destroyed.", ""),
              "output": ProcResult(0, outs, "")})
    e = TerraformEngine("opentofu", runner=f, which=which_of("tofu"))
    res = e.apply(bound(), tmp_path)
    assert f.verbs == ["init", "apply", "output"]
    assert "-auto-approve" in f.calls[1][0]
    assert res["changes"] == {"add": 1, "change": 0, "destroy": 0}
    assert res["outputs"] == {"my-file": {"path": "/x/a.txt", "id": "abc"}}  # original name restored


def test_destroy_sequence(tmp_path):
    f = Fake({"destroy": ProcResult(0, "Destroy complete! Resources: 1 destroyed.", "")})
    e = TerraformEngine("terraform", runner=f, which=which_of("terraform"))
    res = e.destroy(bound("terraform"), tmp_path)
    assert f.verbs == ["init", "destroy"]
    assert f.calls[1][0][0] == "/bin/terraform"
    assert res["changes"]["destroy"] == 1


def test_error_mapping_stderr_tail(tmp_path):
    f = Fake({"init": ProcResult(1, "", "\n".join(f"line{i}" for i in range(100)))})
    e = TerraformEngine("opentofu", runner=f, which=which_of("tofu"))
    with pytest.raises(EngineError) as ei:
        e.plan(bound(), tmp_path)
    assert ei.value.exit_code == 4
    assert "line99" in ei.value.details["stderr"] and "line0\n" not in ei.value.details["stderr"]


def test_plan_exit_1_is_error(tmp_path):
    f = Fake({"plan": ProcResult(1, "", "boom")})
    e = TerraformEngine("opentofu", runner=f, which=which_of("tofu"))
    with pytest.raises(EngineError):
        e.plan(bound(), tmp_path)


def test_confirm_gate_via_core(tmp_path):
    f = Fake()
    for fn in (core.apply, core.destroy):
        with pytest.raises(NotConfirmedError) as ei:
            fn(SPEC, workdir=tmp_path, runner=f)
        assert ei.value.exit_code == 5
    assert f.calls == []


# ------------------------------------------------------------------ real tofu e2e
@pytest.mark.tofu
def test_e2e_local_file(tmp_path, tf_bin):
    spec = json.loads(json.dumps(SPEC))
    spec["spec"]["resources"][0]["name"] = "hello"
    wd = tmp_path / "wd"
    target = wd / "out" / "a.txt"
    p = core.plan(spec, workdir=wd)
    assert p["changes"]["add"] == 1 and not target.exists()
    a = core.apply(spec, workdir=wd, confirm=True)
    assert a["changes"]["add"] == 1
    assert target.read_text() == "hi\n"
    assert a["outputs"]["hello"]["id"]
    assert core.outputs(spec, workdir=wd)["outputs"]["hello"]["path"].endswith("a.txt")
    assert core.plan(spec, workdir=wd)["changes"] == {"add": 0, "change": 0, "destroy": 0}
    d = core.destroy(spec, workdir=wd, confirm=True)
    assert d["changes"]["destroy"] == 1
    assert not target.exists()
