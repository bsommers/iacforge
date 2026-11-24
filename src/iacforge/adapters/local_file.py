"""`local` provider: files on the host filesystem. Zero external dependencies beyond the engine.

This is the reference adapter (smallest complete example of the contract) and the provider
used by end-to-end tests, since it needs no daemon, hypervisor or cloud account.

Relative paths resolve against the engine workdir.
"""

from __future__ import annotations

from pydantic import Field

from .base import ALL_PLATFORMS, PULUMI, TF, Props, ProviderAdapter, PulumiResult, TfResult, tf_id


class FileProps(Props):
    path: str = Field(description="Destination path; relative paths resolve against the workdir.")
    content: str = Field(default="", description="File content (UTF-8).")
    file_permission: str = Field(default="0644", pattern=r"^0?[0-7]{3}$", alias="filePermission")


class LocalAdapter(ProviderAdapter):
    name = "local"
    description = "Files on the local filesystem (hashicorp/local). Reference adapter and e2e test target."
    status = "stable"
    category = "local"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF, PULUMI})
    pulumi_packages = ("pulumi",)
    resource_models = {"file": FileProps}
    tf_types = {"file": "local_file"}
    tf_required_providers = {"local": {"source": "hashicorp/local", "version": "~> 2.5"}}
    docs_url = "https://registry.terraform.io/providers/hashicorp/local/latest/docs"

    def tf_resource(self, res, props: FileProps, ctx) -> TfResult:
        addr = f"local_file.{tf_id(res.name)}"
        return TfResult(
            body={"filename": props.path, "content": props.content,
                  "file_permission": props.file_permission.rjust(4, "0")},
            outputs={"path": "${" + addr + ".filename}", "id": "${" + addr + ".id}"},
        )

    def pulumi_resource(self, res, props: FileProps, ctx) -> PulumiResult:
        from ..render import pulumi_opts
        from ._pulumi_local import LocalFile

        f = LocalFile(res.name, path=props.path, content=props.content,
                      mode=props.file_permission, opts=pulumi_opts(ctx, res))
        return PulumiResult(resource=f, outputs={"path": f.path, "id": f.id})


ADAPTER = LocalAdapter()


EXAMPLES = [
    {
        "apiVersion": "iacforge/v1",
        "kind": "Stack",
        "metadata": {"name": "local-example"},
        "spec": {"provider": "local", "resources": [
            {"name": "hello", "type": "file", "properties": {"path": "out/hello.txt", "content": "hi\n"}},
        ]},
    }
]
