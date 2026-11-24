"""`hyperv` provider: Hyper-V VMs on a Windows host (taliesins/hyperv). Terraform/OpenTofu only.

Credentials: the spec has no password field by design; export ``HYPERV_PASSWORD``
(and optionally ``HYPERV_USER``), which the provider reads from the environment. Switches/VHDs in the stack are referenced
explicitly via ``switchRef`` / ``vhdRef`` (implicit dependencies); plain ``switch`` names an
existing Hyper-V switch.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .base import TF, WINDOWS, Props, ProviderAdapter, TfResult, tf_id

GIB = 1024**3
MIB = 1024**2


class HypervConfig(Props):
    host: str = "127.0.0.1"
    port: int = Field(default=5986, ge=1, le=65535)
    https: bool = True
    insecure: bool = False
    user: str | None = Field(default=None, description="Falls back to env HYPERV_USER.")
    use_ntlm: bool = Field(default=True, alias="useNtlm")


class VmProps(Props):
    generation: int = Field(default=2, ge=1, le=2)
    memory_mb: int = Field(default=1024, ge=32, alias="memoryMb")
    vcpu: int = Field(default=1, ge=1)
    switch: str | None = Field(default=None, description="Existing Hyper-V switch name.")
    switch_ref: str | None = Field(default=None, alias="switchRef", description="Stack `switch` resource.")
    vhd_path: str | None = Field(default=None, alias="vhdPath", description="Existing VHDX path to attach.")
    vhd_ref: str | None = Field(default=None, alias="vhdRef", description="Stack `vhd` resource to attach.")
    vhd_size_gb: int | None = Field(default=None, ge=1, alias="vhdSizeGb", description="Create a VHD of this size next to the VM (needs vhdPath).")
    dynamic_memory: bool = Field(default=False, alias="dynamicMemory")

    @model_validator(mode="after")
    def _chk(self):
        if self.switch and self.switch_ref:
            raise ValueError("set only one of `switch` and `switchRef`")
        if self.vhd_ref and (self.vhd_path or self.vhd_size_gb):
            raise ValueError("`vhdRef` excludes `vhdPath`/`vhdSizeGb`")
        if self.vhd_size_gb and not self.vhd_path:
            raise ValueError("`vhdSizeGb` requires `vhdPath`")
        return self


class SwitchProps(Props):
    type: str = Field(default="Internal", pattern=r"^(Internal|Private|External)$")
    net_adapter_names: list[str] = Field(default_factory=list, alias="netAdapterNames")

    @model_validator(mode="after")
    def _chk(self):
        if self.type == "External" and not self.net_adapter_names:
            raise ValueError("External switch requires `netAdapterNames`")
        return self


class VhdProps(Props):
    path: str = Field(description="Destination .vhdx path on the Hyper-V host.")
    size_gb: int | None = Field(default=None, ge=1, alias="sizeGb")
    source: str | None = Field(default=None, description="Existing VHD to copy from.")

    @model_validator(mode="after")
    def _chk(self):
        if self.size_gb is None and not self.source:
            raise ValueError("vhd needs `sizeGb` or `source`")
        return self


class HypervAdapter(ProviderAdapter):
    name = "hyperv"
    description = "Hyper-V virtual machines, switches and VHDs on a Windows host (taliesins/hyperv)."
    status = "beta"
    category = "local"
    platforms = frozenset({WINDOWS})
    engines = frozenset({TF})
    required_tools = ("powershell",)
    config_model = HypervConfig
    resource_models = {"vm": VmProps, "switch": SwitchProps, "vhd": VhdProps}
    tf_types = {"vm": "hyperv_machine_instance", "switch": "hyperv_network_switch", "vhd": "hyperv_vhd"}
    tf_required_providers = {"hyperv": {"source": "taliesins/hyperv", "version": "~> 1.2"}}
    docs_url = "https://registry.terraform.io/providers/taliesins/hyperv/latest/docs"

    def references(self, res, props):
        return [r for r in (getattr(props, "switch_ref", None), getattr(props, "vhd_ref", None)) if r]

    def tf_provider_blocks(self, config):
        b = {"host": config.host, "port": config.port, "https": config.https,
             "insecure": config.insecure, "use_ntlm": config.use_ntlm}
        if config.user:
            b["user"] = config.user
        return {"hyperv": b}

    def tf_resource(self, res, props, ctx):
        tid = tf_id(res.name)
        if res.type == "switch":
            body = {"name": res.name, "switch_type": props.type}
            if props.net_adapter_names:
                body["net_adapter_names"] = list(props.net_adapter_names)
            return TfResult(body=body, outputs={"name": "${hyperv_network_switch.%s.name}" % tid})
        if res.type == "vhd":
            body = {"path": props.path, "vhd_type": "Dynamic"}
            if props.size_gb:
                body["size"] = props.size_gb * GIB
            if props.source:
                body["source"] = props.source
            return TfResult(body=body, outputs={"path": "${hyperv_vhd.%s.path}" % tid})
        # vm
        extra: dict = {}
        vhd_path = props.vhd_path
        if props.vhd_ref:
            vhd_path = ctx.ref(props.vhd_ref, "path")
        elif props.vhd_path and props.vhd_size_gb:
            extra["hyperv_vhd"] = {f"{tid}_vhd": {"path": props.vhd_path, "size": props.vhd_size_gb * GIB, "vhd_type": "Dynamic"}}
            vhd_path = "${hyperv_vhd.%s_vhd.path}" % tid
        body = {
            "name": res.name, "generation": props.generation, "processor_count": props.vcpu,
            "static_memory": not props.dynamic_memory,
            "memory_startup_bytes": props.memory_mb * MIB,
        }
        if props.dynamic_memory:
            body["memory_minimum_bytes"] = min(props.memory_mb, 512) * MIB
            body["memory_maximum_bytes"] = props.memory_mb * 4 * MIB
        sw = ctx.ref(props.switch_ref, "name") if props.switch_ref else props.switch
        if sw:
            body["network_adaptors"] = [{"name": "wan", "switch_name": sw}]
        if vhd_path:
            body["hard_disk_drives"] = [{"controller_type": "Scsi", "controller_number": 0,
                                         "controller_location": 0, "path": vhd_path}]
        return TfResult(body=body, extra=extra, outputs={
            "id": "${hyperv_machine_instance.%s.id}" % tid, "name": "${hyperv_machine_instance.%s.name}" % tid})


ADAPTER = HypervAdapter()

EXAMPLES = [
    {
        "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "hyperv-example"},
        "spec": {"provider": "hyperv", "resources": [
            {"name": "labswitch", "type": "switch", "properties": {"type": "Internal"}},
            {"name": "disk", "type": "vhd", "properties": {"path": "C:\\VMs\\lab\\disk.vhdx", "sizeGb": 40}},
            {"name": "lab1", "type": "vm", "properties": {
                "generation": 2, "memoryMb": 2048, "vcpu": 2, "switchRef": "labswitch", "vhdRef": "disk"}},
        ]},
    }
]
