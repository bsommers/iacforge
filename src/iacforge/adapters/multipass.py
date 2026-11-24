"""`multipass` provider: Canonical Multipass VMs (Linux, macOS, Windows). larstobi/multipass.

Cross-platform local VM option and the primary macOS VM path. Terraform/OpenTofu only.
``cloudInit`` is written to ``<id>_cloudinit`` (hashicorp/local ``local_file``) and passed
via ``cloudinit_file``.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .base import ALL_PLATFORMS, TF, Props, ProviderAdapter, TfResult, tf_id


class VmProps(Props):
    image: str = Field(default="24.04", description="Image alias, e.g. 24.04, 22.04, or a URL.")
    cpus: int = Field(default=1, ge=1)
    memory_gb: float | None = Field(default=None, gt=0, alias="memoryGb")
    memory: str | None = Field(default=None, pattern=r"^\d+(\.\d+)?[KMG]i?B?$", description="e.g. 2G or 1536M; overrides memoryGb.")
    disk_gb: int = Field(default=5, ge=1, alias="diskGb")
    cloud_init: str | None = Field(default=None, alias="cloudInit", description="cloud-config user-data text.")

    @model_validator(mode="after")
    def _chk(self):
        if self.memory is not None and self.memory_gb is not None:
            raise ValueError("set only one of `memory` and `memoryGb`")
        return self


def _mem(p: VmProps) -> str:
    if p.memory:
        return p.memory
    gb = p.memory_gb if p.memory_gb is not None else 1
    return f"{int(gb)}G" if float(gb).is_integer() else f"{int(gb * 1024)}M"


class MultipassAdapter(ProviderAdapter):
    name = "multipass"
    description = "Ubuntu VMs via Canonical Multipass; cross-platform (Linux/macOS/Windows) local VMs (larstobi/multipass)."
    status = "beta"
    category = "local"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF})
    required_tools = ("multipass",)
    resource_models = {"vm": VmProps}
    tf_types = {"vm": "multipass_instance"}
    tf_required_providers = {
        "multipass": {"source": "larstobi/multipass", "version": "~> 1.4"},
        "local": {"source": "hashicorp/local", "version": "~> 2.5"},
    }
    docs_url = "https://registry.terraform.io/providers/larstobi/multipass/latest/docs"

    def tf_resource(self, res, props, ctx):
        tid = tf_id(res.name)
        body = {"name": res.name, "image": props.image, "cpus": props.cpus,
                "memory": _mem(props), "disk": f"{props.disk_gb}G"}
        extra = {}
        if props.cloud_init is not None:
            extra["local_file"] = {f"{tid}_cloudinit": {
                "filename": f"${{path.module}}/{tid}-cloud-init.yaml", "content": props.cloud_init}}
            body["cloudinit_file"] = "${local_file.%s_cloudinit.filename}" % tid
        return TfResult(body=body, extra=extra, outputs={
            "name": "${multipass_instance.%s.name}" % tid, "ipv4": "${multipass_instance.%s.ipv4}" % tid})


ADAPTER = MultipassAdapter()

EXAMPLES = [
    {
        "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "multipass-example"},
        "spec": {"provider": "multipass", "resources": [
            {"name": "dev", "type": "vm", "properties": {
                "image": "24.04", "cpus": 2, "memoryGb": 2, "diskGb": 10,
                "cloudInit": "#cloud-config\npackages:\n  - htop\n"}},
        ]},
    }
]
