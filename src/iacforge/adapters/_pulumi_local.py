"""Pulumi dynamic provider for local files (pure Python, cross-platform).

Imported only under the pulumi engine. Relative paths are resolved to absolute against
the program's working directory at preview/apply time (the engine runs programs with
cwd = workdir), and the absolute path is what is stored in state.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pulumi
from pulumi.dynamic import CreateResult, DiffResult, ResourceProvider, UpdateResult


def _write(path: str, content: str, mode: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    try:
        os.chmod(p, int(mode, 8))
    except (OSError, ValueError):  # chmod is best-effort on Windows
        pass


class _LocalFileProvider(ResourceProvider):
    def create(self, props: dict[str, Any]) -> CreateResult:
        _write(props["path"], props["content"], props["mode"])
        return CreateResult(id_=props["path"], outs=props)

    def diff(self, _id: str, olds: dict[str, Any], news: dict[str, Any]) -> DiffResult:
        keys = ("path", "content", "mode")
        changed = [k for k in keys if olds.get(k) != news.get(k)]
        return DiffResult(changes=bool(changed), replaces=["path"] if "path" in changed else [],
                          delete_before_replace=True)

    def update(self, _id: str, _olds: dict[str, Any], news: dict[str, Any]) -> UpdateResult:
        _write(news["path"], news["content"], news["mode"])
        return UpdateResult(outs=news)

    def delete(self, _id: str, props: dict[str, Any]) -> None:
        try:
            Path(props["path"]).unlink()
        except FileNotFoundError:
            pass


class LocalFile(pulumi.dynamic.Resource):
    path: pulumi.Output[str]
    content: pulumi.Output[str]

    def __init__(self, name: str, *, path: str, content: str, mode: str = "0644",
                 opts: pulumi.ResourceOptions | None = None):
        abs_path = str(Path(path) if Path(path).is_absolute() else (Path.cwd() / path).resolve())
        super().__init__(_LocalFileProvider(), name,
                         {"path": abs_path, "content": content, "mode": mode}, opts)
