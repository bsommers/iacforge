import json

import pytest

from iacforge import cli, core
from iacforge.engines.base import ProcResult
from iacforge.errors import NotConfirmedError

SPEC = {
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "c1"},
    "spec": {"provider": "local", "engine": "opentofu", "resources": [
        {"name": "hello", "type": "file", "properties": {"path": "out/a.txt", "content": "hi\n"}}]},
}


@pytest.fixture
def specfile(tmp_path):
    p = tmp_path / "stack.json"
    p.write_text(json.dumps(SPEC))
    return p


def run(capsys, *argv):
    code = cli.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_validate_json_envelope(capsys, specfile):
    code, out, _ = run(capsys, "--json", "validate", str(specfile))
    env = json.loads(out)
    assert code == 0 and env["ok"] and env["command"] == "validate"
    assert env["data"]["resources"] == ["hello"]


def test_invalid_spec_exit_2(capsys, tmp_path):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"kind": "Stack"}))
    code, out, _ = run(capsys, "--json", "validate", str(p))
    env = json.loads(out)
    assert code == 2 and not env["ok"] and env["error"]["code"] == "invalid_spec"


def test_apply_without_yes_exit_5(capsys, specfile, tmp_path):
    for c in ("apply", "destroy"):
        code, out, _ = run(capsys, "--json", c, str(specfile), "--workdir", str(tmp_path / "w"))
        assert code == 5 and json.loads(out)["error"]["code"] == "not_confirmed"


def test_tool_missing_exit_3(capsys, specfile, tmp_path, monkeypatch):
    monkeypatch.setenv("IACFORGE_TF_BINARY", "definitely-not-installed-xyz")
    code, out, _ = run(capsys, "--json", "plan", str(specfile), "--workdir", str(tmp_path / "w"))
    assert code == 3 and json.loads(out)["error"]["code"] == "tool_missing"


def test_engine_failure_exit_4(specfile, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: "/bin/tofu")
    def runner(args, cwd, env=None, timeout=None):
        return ProcResult(1, "", "kaboom")
    with pytest.raises(Exception) as ei:
        core.plan(str(specfile), workdir=tmp_path / "w", runner=runner)
    assert ei.value.exit_code == 4


def test_render_command_writes_file(capsys, specfile, tmp_path):
    wd = tmp_path / "w"
    code, out, _ = run(capsys, "--json", "render", str(specfile), "--workdir", str(wd))
    assert code == 0 and (wd / "main.tf.json").exists()
    assert json.loads(out)["data"]["files"] == ["main.tf.json"]


def test_render_pulumi(capsys, specfile, tmp_path):
    wd = tmp_path / "w"
    code, _, _ = run(capsys, "--json", "render", str(specfile), "--engine", "pulumi", "--workdir", str(wd))
    assert code == 0 and (wd / "Pulumi.yaml").exists() and (wd / "__main__.py").exists()


def test_init_command(capsys, tmp_path):
    p = tmp_path / "s.yaml"
    code, _out, _ = run(capsys, "--json", "init", "--path", str(p))
    assert code == 0 and p.exists()
    code, _, _ = run(capsys, "--json", "validate", str(p))
    assert code == 0
    code, _out, _ = run(capsys, "--json", "init", "--path", str(p))  # exists, no --force
    assert code == 2
    assert run(capsys, "--json", "init", "--path", str(p), "--force")[0] == 0


def test_human_output_and_version(capsys, specfile):
    code, out, _ = run(capsys, "validate", str(specfile))
    assert code == 0 and "valid" in out
    code, out, _ = run(capsys, "--json", "version")
    assert json.loads(out)["data"]["engines"]


def test_core_gate_direct(tmp_path):
    with pytest.raises(NotConfirmedError):
        core.apply(SPEC, workdir=tmp_path)


# ---- import (ADR 0006)

def _import_runner(calls):
    def runner(args, cwd, env=None, timeout=None):
        calls.append(args)
        if "show" in args:
            return ProcResult(0, json.dumps({"resource_changes": []}), "")
        return ProcResult(0, "ok", "")
    return runner


def test_import_gate_exit_5(capsys, specfile, tmp_path):
    code, out, _ = run(capsys, "--json", "import", str(specfile), "--resource", "hello", "--id", "x",
                       "--workdir", str(tmp_path / "w"))
    assert code == 5 and json.loads(out)["error"]["code"] == "not_confirmed"


def test_import_unknown_resource(specfile, tmp_path):
    from iacforge.errors import SpecError
    with pytest.raises(SpecError):
        core.import_resource(str(specfile), "nope", id="x", confirm=True, workdir=tmp_path / "w")


def test_import_derived_id_unsupported(specfile, tmp_path):
    from iacforge.errors import UnsupportedError
    with pytest.raises(UnsupportedError):
        core.import_resource(str(specfile), "hello", confirm=True, workdir=tmp_path / "w")


def test_import_explicit_id_terraform_argv(specfile, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: "/bin/tofu")
    calls: list = []
    d = core.import_resource(str(specfile), "hello", id="abc", confirm=True,
                             workdir=tmp_path / "w", runner=_import_runner(calls))
    imp = next(c for c in calls if "import" in c)
    assert imp[0] == "/bin/tofu" and imp[1:4] == ["import", "-input=false", "-no-color"]
    assert imp[4].endswith(".hello") and imp[5] == "abc"
    assert d["imported"] == {"resource": "hello", "address": imp[4], "id": "abc"}
    assert d["changes"] == {"add": 0, "change": 0, "destroy": 0}


def test_import_derived_id_via_adapter(specfile, tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: "/bin/tofu")
    from iacforge.adapters import get_adapter
    monkeypatch.setattr(type(get_adapter("local")), "import_id",
                        lambda self, res, props, config: "derived-1")
    d = core.import_resource(str(specfile), "hello", confirm=True, workdir=tmp_path / "w",
                             runner=_import_runner([]))
    assert d["imported"]["id"] == "derived-1"


def test_import_cli_json_and_human(capsys, specfile, tmp_path, monkeypatch):
    from iacforge.engines import get_engine
    monkeypatch.setattr("shutil.which", lambda n: "/bin/tofu")
    monkeypatch.setattr(core, "get_engine", lambda name, runner=None: get_engine(name, runner=_import_runner([])))
    code, out, _ = run(capsys, "--json", "import", str(specfile), "--resource", "hello", "--id", "abc",
                       "-y", "--workdir", str(tmp_path / "w"))
    env = json.loads(out)
    assert code == 0 and env["command"] == "import" and env["data"]["imported"]["id"] == "abc"
    code, out, _ = run(capsys, "import", str(specfile), "--resource", "hello", "--id", "abc",
                       "-y", "--workdir", str(tmp_path / "w2"))
    assert out.startswith("imported ") and "plan: +0 ~0 -0" in out
