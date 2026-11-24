import pytest

from iacforge import mcp_server as m

SPEC = """\
apiVersion: iacforge/v1
kind: Stack
metadata: {name: t}
spec:
  provider: local
  engine: opentofu
  resources:
    - name: hello
      type: file
      properties: {path: out/hello.txt, content: hi}
"""


def test_version_envelope():
    r = m.iacforge_version()
    assert r["ok"] is True and "version" in r["data"]


def test_providers_and_schema():
    assert m.iacforge_providers()["ok"]
    assert m.iacforge_providers("local")["ok"]
    assert m.iacforge_schema()["ok"]


def test_doctor():
    assert m.iacforge_doctor()["data"]["providers"]


def test_validate_inline():
    r = m.iacforge_validate(SPEC)
    assert r["ok"] and r["data"]["valid"] is True


def test_validate_bad_spec():
    r = m.iacforge_validate("not: a stack\n")
    assert r["ok"] is False and r["error"]["code"] == "invalid_spec"


def test_unknown_provider():
    r = m.iacforge_providers("nope")
    assert r["ok"] is False and "code" in r["error"]


@pytest.mark.parametrize("fn", [m.iacforge_apply, m.iacforge_destroy])
def test_mutations_need_confirm(fn, tmp_path):
    r = fn(SPEC, workdir=str(tmp_path))
    assert r["ok"] is False and r["error"]["code"] == "not_confirmed"
    assert not list(tmp_path.iterdir())


def test_render_inline(tmp_path):
    r = m.iacforge_render(SPEC, workdir=str(tmp_path))
    assert r["ok"], r
    assert any(tmp_path.iterdir())


def test_descriptions_warn_agents():
    assert "confirm" in m.iacforge_apply.__doc__ and "plan" in m.iacforge_apply.__doc__
    assert "confirm" in m.iacforge_destroy.__doc__


def test_server_builds():
    pytest.importorskip("mcp")
    assert m.build_server() is not None
