import json
from types import SimpleNamespace as NS

import pytest

from iacforge import core
from iacforge.engines.pulumi import PulumiEngine
from iacforge.errors import EngineError, ToolMissingError
from iacforge.render import bind
from iacforge.spec import parse_spec

SPEC = {
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "p1"},
    "spec": {"provider": "local", "engine": "pulumi", "resources": [
        {"name": "hello", "type": "file", "properties": {"path": "out/a.txt", "content": "hi\n"}}]},
}


def bound():
    return bind(parse_spec(SPEC))


class FakeStack:
    def __init__(self, fail=False):
        self.fail = fail

    def preview(self):
        return NS(stdout="prev", change_summary={"create": 2, "same": 1, "replace": 1})

    def up(self):
        if self.fail:
            raise RuntimeError("update failed")
        return NS(stdout="up", summary=NS(resource_changes={"create": 1}),
                  outputs={"hello__path": NS(value="/w/out/a.txt", secret=False)})

    def destroy(self):
        return NS(stdout="down", summary=NS(resource_changes={"delete": 1}))

    def outputs(self):
        return {"hello__id": NS(value="x")}


def engine(stack=None, cli=True):
    e = PulumiEngine(which=lambda n: "/bin/pulumi" if cli else None)
    st = stack or FakeStack()
    e._open_stack = lambda b, wd: st
    return e


def test_render_ejectable_project(tmp_path):
    res = PulumiEngine(which=lambda n: None).render(bound(), tmp_path / "wd")
    wd = tmp_path / "wd"
    assert set(res["files"]) == {"Pulumi.yaml", "__main__.py", "requirements.txt", "stack.json"}
    assert "runtime: python" in (wd / "Pulumi.yaml").read_text()
    assert "run_pulumi_program" in (wd / "__main__.py").read_text()
    reqs = (wd / "requirements.txt").read_text().split()
    assert "iacforge" in reqs and "pulumi" in reqs
    spec = json.loads((wd / "stack.json").read_text())
    assert spec["apiVersion"] == "iacforge/v1"
    parse_spec(spec)  # round-trips


def test_plan_summary(tmp_path):
    out = engine().plan(bound(), tmp_path)
    assert out["changes"] == {"add": 3, "change": 0, "destroy": 1}  # replace counts both
    assert out["has_changes"]


def test_apply_outputs_nested(tmp_path):
    out = engine().apply(bound(), tmp_path)
    assert out["changes"] == {"add": 1, "change": 0, "destroy": 0}
    assert out["outputs"] == {"hello": {"path": "/w/out/a.txt"}}


def test_destroy_and_outputs(tmp_path):
    e = engine()
    assert e.destroy(bound(), tmp_path)["changes"]["destroy"] == 1
    assert e.outputs(bound(), tmp_path) == {"outputs": {"hello": {"id": "x"}}}


def test_cwd_is_workdir_during_call(tmp_path):
    import os
    seen = {}
    st = FakeStack()
    st.preview = lambda: seen.setdefault("cwd", os.getcwd()) and NS(stdout="", change_summary={})
    engine(st).plan(bound(), tmp_path)
    assert seen["cwd"] == str(tmp_path.resolve())
    assert os.getcwd() != str(tmp_path)


def test_engine_failure_mapped(tmp_path):
    with pytest.raises(EngineError) as ei:
        engine(FakeStack(fail=True)).apply(bound(), tmp_path)
    assert "update failed" in ei.value.details["stderr"]


def test_missing_cli(tmp_path):
    e = PulumiEngine(which=lambda n: None)
    with pytest.raises(ToolMissingError) as ei:
        e.plan(bound(), tmp_path)
    assert "pulumi" in ei.value.details["hint"]
    assert e.tool_status()["binary"] is None


def test_passphrase_default(monkeypatch, tmp_path):
    monkeypatch.delenv("PULUMI_CONFIG_PASSPHRASE", raising=False)
    env = PulumiEngine()._env(tmp_path)
    assert env["PULUMI_CONFIG_PASSPHRASE"] == ""
    assert env["PULUMI_BACKEND_URL"] == f"file://{(tmp_path / 'state').as_posix()}"
    monkeypatch.setenv("PULUMI_CONFIG_PASSPHRASE", "s3")
    assert PulumiEngine()._env(tmp_path)["PULUMI_CONFIG_PASSPHRASE"] == "s3"


@pytest.mark.pulumi
def test_e2e_local_file(tmp_path, pulumi_bin):
    pytest.importorskip("pulumi.automation")
    wd = tmp_path / "wd"
    a = core.apply(SPEC, workdir=wd, confirm=True)
    target = wd / "out" / "a.txt"
    assert target.read_text() == "hi\n" and a["outputs"]["hello"]["path"]
    core.destroy(SPEC, workdir=wd, confirm=True)
    assert not target.exists()
