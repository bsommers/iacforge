"""`libvirt` provider: local KVM/QEMU VMs via libvirt (Linux). dmacvicar/libvirt 0.8.x.

A ``vm`` emits extra blocks: ``<id>_base`` (base image volume), ``<id>_root`` (copy-on-write
root volume sized by ``diskGb``) and ``<id>_cloudinit`` (cloud-init ISO). Networks/pools in
the stack are referenced explicitly via ``networkRef`` / ``poolRef`` (implicit dependencies);
plain ``network`` / ``pool`` name something that already exists in libvirt.
"""

from __future__ import annotations

import json

from pydantic import Field, model_validator

from .base import LINUX, PULUMI, TF, Props, ProviderAdapter, PulumiResult, TfResult, tf_id

GIB = 1024**3


class LibvirtConfig(Props):
    uri: str = Field(default="qemu:///system", description="libvirt connection URI.")


class CloudInit(Props):
    user_data: str = Field(alias="userData", description="cloud-config user-data text.")
    meta_data: str | None = Field(default=None, alias="metaData")


class VmProps(Props):
    memory_mb: int = Field(default=1024, ge=64, alias="memoryMb")
    vcpu: int = Field(default=1, ge=1)
    image: str = Field(description="Base image URL or local path (qcow2/img).")
    disk_gb: int | None = Field(default=None, ge=1, alias="diskGb", description="Root disk size; default = image size.")
    network: str = Field(default="default", description="Existing libvirt network name.")
    network_ref: str | None = Field(default=None, alias="networkRef", description="Stack `network` resource to attach to (overrides `network`).")
    pool: str = Field(default="default", description="Existing libvirt storage pool name.")
    pool_ref: str | None = Field(default=None, alias="poolRef", description="Stack `pool` resource for volumes (overrides `pool`).")
    cloud_init: CloudInit | None = Field(default=None, alias="cloudInit")
    ssh_authorized_keys: list[str] = Field(default_factory=list, alias="sshAuthorizedKeys")
    autostart: bool = False

    @model_validator(mode="after")
    def _ci(self):
        if self.ssh_authorized_keys and self.cloud_init and not self.cloud_init.user_data.lstrip().startswith("#cloud-config"):
            raise ValueError("sshAuthorizedKeys can only be merged into cloudInit.userData starting with '#cloud-config'")
        return self


class NetworkProps(Props):
    mode: str = Field(default="nat", pattern=r"^(nat|isolated|bridge)$")
    cidr: str | None = Field(default=None, description="e.g. 192.168.150.0/24 (nat/isolated).")
    dhcp: bool = True
    autostart: bool = True
    bridge: str | None = Field(default=None, description="Host bridge device (required for mode=bridge).")
    domain: str | None = None

    @model_validator(mode="after")
    def _chk(self):
        if self.mode == "bridge" and not self.bridge:
            raise ValueError("mode 'bridge' requires `bridge`")
        if self.mode != "bridge" and not self.cidr:
            raise ValueError(f"mode '{self.mode}' requires `cidr`")
        return self


class PoolProps(Props):
    path: str = Field(description="Directory backing the pool.")


class VolumeProps(Props):
    pool: str = Field(default="default", description="Existing libvirt storage pool name.")
    pool_ref: str | None = Field(default=None, alias="poolRef")
    size_gb: int | None = Field(default=None, ge=1, alias="sizeGb")
    source: str | None = Field(default=None, description="Image URL or path to import.")

    @model_validator(mode="after")
    def _chk(self):
        if self.size_gb is None and not self.source:
            raise ValueError("volume needs `sizeGb` or `source`")
        return self


def merged_user_data(p: VmProps) -> str:
    base = p.cloud_init.user_data if p.cloud_init else "#cloud-config\n"
    if p.ssh_authorized_keys:
        base = base.rstrip("\n") + "\nssh_authorized_keys:\n" + "".join(f"  - {json.dumps(k)}\n" for k in p.ssh_authorized_keys)
    return base


class LibvirtAdapter(ProviderAdapter):
    name = "libvirt"
    description = "Local KVM/QEMU virtual machines, networks and storage via libvirt (dmacvicar/libvirt)."
    status = "beta"
    category = "local"
    platforms = frozenset({LINUX})
    engines = frozenset({TF, PULUMI})
    required_tools = ("virsh", "qemu-img")
    pulumi_packages = ("pulumi", "pulumi-libvirt")
    config_model = LibvirtConfig
    resource_models = {"vm": VmProps, "network": NetworkProps, "pool": PoolProps, "volume": VolumeProps}
    tf_types = {"vm": "libvirt_domain", "network": "libvirt_network", "pool": "libvirt_pool", "volume": "libvirt_volume"}
    tf_required_providers = {"libvirt": {"source": "dmacvicar/libvirt", "version": "~> 0.8.1"}}
    docs_url = "https://registry.terraform.io/providers/dmacvicar/libvirt/0.8.3/docs"

    def references(self, res, props):
        refs = []
        for r in (getattr(props, "network_ref", None), getattr(props, "pool_ref", None)):
            if r:
                refs.append(r)
        return refs

    def tf_provider_blocks(self, config):
        return {"libvirt": {"uri": config.uri}}

    def _pool(self, props, ctx):
        return ctx.ref(props.pool_ref, "name") if props.pool_ref else props.pool

    def tf_resource(self, res, props, ctx):
        tid = tf_id(res.name)
        if res.type == "pool":
            return TfResult(
                body={"name": res.name, "type": "dir", "path": props.path},
                outputs={"id": "${libvirt_pool.%s.id}" % tid, "name": "${libvirt_pool.%s.name}" % tid},
            )
        if res.type == "network":
            body: dict = {"name": res.name, "mode": {"nat": "nat", "isolated": "none", "bridge": "bridge"}[props.mode],
                          "autostart": props.autostart}
            if props.mode == "bridge":
                body["bridge"] = props.bridge
            else:
                body["addresses"] = [props.cidr]
                body["dhcp"] = [{"enabled": props.dhcp}]
            if props.domain:
                body["domain"] = props.domain
            return TfResult(body=body, outputs={"id": "${libvirt_network.%s.id}" % tid, "name": "${libvirt_network.%s.name}" % tid})
        if res.type == "volume":
            body = {"name": res.name, "pool": self._pool(props, ctx)}
            if props.source:
                body["source"] = props.source
            if props.size_gb:
                body["size"] = props.size_gb * GIB
            return TfResult(body=body, outputs={"id": "${libvirt_volume.%s.id}" % tid, "name": "${libvirt_volume.%s.name}" % tid})
        # vm
        pool = self._pool(props, ctx)
        root: dict = {"name": f"{res.name}-root", "pool": pool, "base_volume_id": "${libvirt_volume.%s_base.id}" % tid}
        if props.disk_gb:
            root["size"] = props.disk_gb * GIB
        ci: dict = {"name": f"{res.name}-cloudinit.iso", "pool": pool, "user_data": merged_user_data(props)}
        if props.cloud_init and props.cloud_init.meta_data:
            ci["meta_data"] = props.cloud_init.meta_data
        netname = ctx.ref(props.network_ref, "name") if props.network_ref else props.network
        body = {
            "name": res.name, "memory": props.memory_mb, "vcpu": props.vcpu, "autostart": props.autostart,
            "cloudinit": "${libvirt_cloudinit_disk.%s_cloudinit.id}" % tid,
            "disk": [{"volume_id": "${libvirt_volume.%s_root.id}" % tid}],
            "network_interface": [{"network_name": netname, "wait_for_lease": True}],
            "console": [{"type": "pty", "target_port": "0", "target_type": "serial"}],
        }
        return TfResult(
            body=body,
            extra={
                "libvirt_volume": {
                    f"{tid}_base": {"name": f"{res.name}-base", "pool": pool, "source": props.image},
                    f"{tid}_root": root,
                },
                "libvirt_cloudinit_disk": {f"{tid}_cloudinit": ci},
            },
            outputs={
                "id": "${libvirt_domain.%s.id}" % tid,
                "name": "${libvirt_domain.%s.name}" % tid,
                "ip": "${libvirt_domain.%s.network_interface[0].addresses[0]}" % tid,
            },
        )

    # ---- pulumi ----
    def pulumi_provider(self, config, stack):
        import pulumi_libvirt as lv

        return lv.Provider("libvirt", uri=config.uri)

    def pulumi_resource(self, res, props, ctx):
        import pulumi_libvirt as lv

        from ..render import pulumi_opts

        opts = pulumi_opts(ctx, res)
        if res.type == "pool":
            p = lv.Pool(res.name, name=res.name, type="dir", path=props.path, opts=opts)
            return PulumiResult(resource=p, outputs={"id": p.id, "name": p.name})
        if res.type == "network":
            kw: dict = {"name": res.name, "autostart": props.autostart,
                        "mode": {"nat": "nat", "isolated": "none", "bridge": "bridge"}[props.mode]}
            if props.mode == "bridge":
                kw["bridge"] = props.bridge
            else:
                kw["addresses"] = [props.cidr]
                kw["dhcp"] = lv.NetworkDhcpArgs(enabled=props.dhcp)
            if props.domain:
                kw["domain"] = props.domain
            n = lv.Network(res.name, opts=opts, **kw)
            return PulumiResult(resource=n, outputs={"id": n.id, "name": n.name})

        def pool_of(p):
            return ctx.get(p.pool_ref).name if p.pool_ref else p.pool

        if res.type == "volume":
            kw = {"name": res.name, "pool": pool_of(props)}
            if props.source:
                kw["source"] = props.source
            if props.size_gb:
                kw["size"] = props.size_gb * GIB
            v = lv.Volume(res.name, opts=opts, **kw)
            return PulumiResult(resource=v, outputs={"id": v.id, "name": v.name})
        pool = pool_of(props)
        base = lv.Volume(f"{res.name}-base", name=f"{res.name}-base", pool=pool, source=props.image, opts=opts)
        rkw: dict = {"name": f"{res.name}-root", "pool": pool, "base_volume_id": base.id}
        if props.disk_gb:
            rkw["size"] = props.disk_gb * GIB
        root = lv.Volume(f"{res.name}-root", opts=opts, **rkw)
        ckw: dict = {"name": f"{res.name}-cloudinit.iso", "pool": pool, "user_data": merged_user_data(props)}
        if props.cloud_init and props.cloud_init.meta_data:
            ckw["meta_data"] = props.cloud_init.meta_data
        ci = lv.CloudInitDisk(f"{res.name}-cloudinit", opts=opts, **ckw)
        netname = ctx.get(props.network_ref).name if props.network_ref else props.network
        d = lv.Domain(
            res.name, name=res.name, memory=props.memory_mb, vcpu=props.vcpu, autostart=props.autostart,
            cloudinit=ci.id, disks=[lv.DomainDiskArgs(volume_id=root.id)],
            network_interfaces=[lv.DomainNetworkInterfaceArgs(network_name=netname, wait_for_lease=True)],
            opts=opts,
        )
        return PulumiResult(resource=d, outputs={
            "id": d.id, "name": d.name,
            "ip": d.network_interfaces.apply(lambda n: n[0].addresses[0] if n and n[0].addresses else None),
        })


ADAPTER = LibvirtAdapter()

EXAMPLES = [
    {
        "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "libvirt-example"},
        "spec": {"provider": "libvirt", "resources": [
            {"name": "labpool", "type": "pool", "properties": {"path": "/var/lib/libvirt/images/lab"}},
            {"name": "labnet", "type": "network", "properties": {"mode": "nat", "cidr": "192.168.150.0/24"}},
            {"name": "data", "type": "volume", "properties": {"poolRef": "labpool", "sizeGb": 5}},
            {"name": "web", "type": "vm", "properties": {
                "image": "https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img",
                "memoryMb": 2048, "vcpu": 2, "diskGb": 20, "networkRef": "labnet", "poolRef": "labpool",
                "sshAuthorizedKeys": ["ssh-ed25519 AAAAC3Nza example"]}},
        ]},
    }
]
