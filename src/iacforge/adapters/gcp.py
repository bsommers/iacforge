"""`gcp` provider: Google Cloud (hashicorp/google ~> 6.0 / pulumi_gcp).

Credentials are never part of the spec: use Application Default Credentials
(``gcloud auth application-default login``, ``GOOGLE_APPLICATION_CREDENTIALS``, or workload identity).
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import ALL_PLATFORMS, PULUMI, TF, Props, ProviderAdapter, PulumiResult, TfResult, tf_id

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")
_SA_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


def _cidr(v: str) -> str:
    try:
        ipaddress.ip_network(v, strict=True)
    except ValueError as e:
        raise ValueError(f"invalid CIDR '{v}': {e}") from None
    return v


class GcpConfig(Props):
    project: str = Field(min_length=1, description="GCP project id (credentials come from ADC, never the spec).")
    region: str = "us-central1"
    zone: str = "us-central1-a"
    labels: dict[str, str] = Field(default_factory=dict, description="Default labels merged into labelled resources.")


class NetworkProps(Props):
    auto_create_subnetworks: bool = Field(default=False, alias="autoCreateSubnetworks")
    routing_mode: Literal["REGIONAL", "GLOBAL"] = Field(default="REGIONAL", alias="routingMode")
    description: str = ""


class SubnetProps(Props):
    network: str = Field(description="Name of a stack `network` resource.")
    cidr: str
    region: str | None = None
    private_ip_google_access: bool = Field(default=True, alias="privateIpGoogleAccess")

    _v = field_validator("cidr")(lambda cls, v: _cidr(v))


class AllowRule(Props):
    protocol: str = "tcp"
    ports: list[str] = Field(default_factory=list, description='e.g. ["22", "8000-8100"]; empty = all ports.')


class FirewallProps(Props):
    network: str = Field(description="Name of a stack `network` resource.")
    allow: list[AllowRule] = Field(min_length=1)
    direction: Literal["INGRESS", "EGRESS"] = "INGRESS"
    source_ranges: list[str] = Field(default_factory=list, alias="sourceRanges")
    source_tags: list[str] = Field(default_factory=list, alias="sourceTags")
    target_tags: list[str] = Field(default_factory=list, alias="targetTags")
    destination_ranges: list[str] = Field(default_factory=list, alias="destinationRanges")
    priority: int = Field(default=1000, ge=0, le=65535)

    @field_validator("source_ranges", "destination_ranges")
    @classmethod
    def _ranges(cls, v):
        return [_cidr_loose(x) for x in v]

    @model_validator(mode="after")
    def _need_source(self):
        if self.direction == "INGRESS" and not (self.source_ranges or self.source_tags):
            raise ValueError("INGRESS firewall needs sourceRanges or sourceTags")
        if self.direction == "EGRESS" and not self.destination_ranges:
            self.destination_ranges = ["0.0.0.0/0"]
        return self


def _cidr_loose(v: str) -> str:
    try:
        ipaddress.ip_network(v, strict=False)
    except ValueError as e:
        raise ValueError(f"invalid CIDR '{v}': {e}") from None
    return v


class VmProps(Props):
    machine_type: str = Field(default="e2-small", alias="machineType")
    image: str = "debian-cloud/debian-12"
    disk_gb: int = Field(default=20, ge=10, alias="diskGb")
    zone: str | None = None
    subnet: str | None = Field(default=None, description="Name of a stack `subnet` resource.")
    network: str | None = Field(default=None, description="Name of a stack `network` resource (default subnets).")
    public_ip: bool = Field(default=False, alias="publicIp")
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    startup_script: str | None = Field(default=None, alias="startupScript")
    service_account: str | None = Field(default=None, alias="serviceAccount",
                                        description="Name of a stack `service_account` resource.")
    service_account_email: str | None = Field(default=None, alias="serviceAccountEmail")
    service_account_scopes: list[str] = Field(default_factory=lambda: ["https://www.googleapis.com/auth/cloud-platform"],
                                              alias="serviceAccountScopes")
    preemptible: bool = False
    spot: bool = False

    @model_validator(mode="after")
    def _check(self):
        if not (self.subnet or self.network):
            raise ValueError("vm needs `subnet` or `network`")
        if self.subnet and self.network:
            raise ValueError("set only one of `subnet` / `network`")
        if self.preemptible and self.spot:
            raise ValueError("set only one of `preemptible` / `spot`")
        if self.service_account and self.service_account_email:
            raise ValueError("set only one of `serviceAccount` / `serviceAccountEmail`")
        return self


class BucketProps(Props):
    bucket_name: str | None = Field(default=None, alias="bucketName", description="Globally unique; default: resource name.")
    location: str | None = Field(default=None, description="Default: providerConfig.region.")
    storage_class: Literal["STANDARD", "NEARLINE", "COLDLINE", "ARCHIVE"] = Field(default="STANDARD", alias="storageClass")
    versioning: bool = False
    uniform_bucket_level_access: bool = Field(default=True, alias="uniformBucketLevelAccess")
    force_destroy: bool = Field(default=False, alias="forceDestroy")
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("bucket_name")
    @classmethod
    def _n(cls, v):
        if v is not None and not _BUCKET_RE.match(v):
            raise ValueError("invalid bucket name")
        return v


class ServiceAccountProps(Props):
    account_id: str | None = Field(default=None, alias="accountId", description="6-30 chars; default: resource name.")
    display_name: str = Field(default="", alias="displayName")
    description: str = ""


def _labels(config: GcpConfig, props) -> dict[str, str]:
    return {**config.labels, **getattr(props, "labels", {})}


class GcpAdapter(ProviderAdapter):
    name = "gcp"
    description = "Google Cloud: VPC networks, subnets, firewalls, Compute Engine VMs, GCS buckets, service accounts."
    status = "beta"
    category = "cloud"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF, PULUMI})
    required_tools = ()  # gcloud is optional (ADC login only)
    pulumi_packages = ("pulumi", "pulumi-gcp")
    config_model = GcpConfig
    resource_models = {
        "network": NetworkProps,
        "subnet": SubnetProps,
        "firewall": FirewallProps,
        "vm": VmProps,
        "bucket": BucketProps,
        "service_account": ServiceAccountProps,
    }
    tf_types = {
        "network": "google_compute_network",
        "subnet": "google_compute_subnetwork",
        "firewall": "google_compute_firewall",
        "vm": "google_compute_instance",
        "bucket": "google_storage_bucket",
        "service_account": "google_service_account",
    }
    tf_required_providers = {"google": {"source": "hashicorp/google", "version": "~> 6.0"}}
    docs_url = "https://registry.terraform.io/providers/hashicorp/google/latest/docs"

    # ---- validation ----
    def references(self, res, props) -> list[str]:
        out: list[str] = []
        for attr in ("network", "subnet", "service_account"):
            v = getattr(props, attr, None)
            if v:
                out.append(v)
        return out

    def validate_stack(self, stack, config, props) -> list[str]:
        errs = []
        types = {r.name: r.type for r in stack.spec.resources}
        expect = {"network": "network", "subnet": "subnet", "service_account": "service_account"}
        for r in stack.spec.resources:
            p = props[r.name]
            for attr, want in expect.items():
                v = getattr(p, attr, None)
                if v and r.type != want and v in types and types[v] != want:
                    errs.append(f"{r.name}: `{attr}` refers to '{v}' which is a {types[v]}, expected {want}")
            if r.type == "service_account":
                aid = p.account_id or r.name
                if not _SA_RE.match(aid):
                    errs.append(f"{r.name}: service account id '{aid}' must be 6-30 chars [a-z0-9-], start with a letter")
            if r.type == "bucket" and not _BUCKET_RE.match(p.bucket_name or r.name):
                errs.append(f"{r.name}: bucket name '{p.bucket_name or r.name}' is invalid (3+ chars, lowercase)")
        return errs

    # ---- terraform ----
    def tf_provider_blocks(self, config):
        return {"google": {"project": config.project, "region": config.region, "zone": config.zone}}

    def tf_resource(self, res, props, ctx) -> TfResult:
        cfg: GcpConfig = ctx.config
        addr = f"{self.tf_types[res.type]}.{tf_id(res.name)}"
        def o(attr: str) -> str:
            return "${" + f"{addr}.{attr}" + "}"
        t = res.type

        if t == "network":
            body = {"name": res.name, "auto_create_subnetworks": props.auto_create_subnetworks,
                    "routing_mode": props.routing_mode}
            if props.description:
                body["description"] = props.description
            return TfResult(body, outputs={"id": o("id"), "self_link": o("self_link"), "name": o("name")})

        if t == "subnet":
            body = {"name": res.name, "ip_cidr_range": props.cidr, "region": props.region or cfg.region,
                    "network": ctx.ref(props.network, "self_link"),
                    "private_ip_google_access": props.private_ip_google_access}
            return TfResult(body, outputs={"id": o("id"), "self_link": o("self_link"), "cidr": o("ip_cidr_range")})

        if t == "firewall":
            allow = []
            for a in props.allow:
                blk: dict = {"protocol": a.protocol}
                if a.ports:
                    blk["ports"] = a.ports
                allow.append(blk)
            body = {"name": res.name, "network": ctx.ref(props.network, "self_link"),
                    "direction": props.direction, "priority": props.priority, "allow": allow}
            if props.direction == "INGRESS":
                if props.source_ranges:
                    body["source_ranges"] = props.source_ranges
                if props.source_tags:
                    body["source_tags"] = props.source_tags
            else:
                body["destination_ranges"] = props.destination_ranges
            if props.target_tags:
                body["target_tags"] = props.target_tags
            return TfResult(body, outputs={"id": o("id"), "self_link": o("self_link")})

        if t == "vm":
            nic: dict = {}
            if props.subnet:
                nic["subnetwork"] = ctx.ref(props.subnet, "self_link")
            else:
                nic["network"] = ctx.ref(props.network, "self_link")
            if props.public_ip:
                nic["access_config"] = [{}]
            body: dict = {
                "name": res.name, "machine_type": props.machine_type, "zone": props.zone or cfg.zone,
                "boot_disk": {"initialize_params": {"image": props.image, "size": props.disk_gb}},
                "network_interface": [nic],
            }
            if props.tags:
                body["tags"] = props.tags
            labels = _labels(cfg, props)
            if labels:
                body["labels"] = labels
            if props.metadata:
                body["metadata"] = props.metadata
            if props.startup_script:
                body["metadata_startup_script"] = props.startup_script
            email = ctx.ref(props.service_account, "email") if props.service_account else props.service_account_email
            if email:
                body["service_account"] = {"email": email, "scopes": props.service_account_scopes}
            if props.spot or props.preemptible:
                sched = {"preemptible": True, "automatic_restart": False, "on_host_maintenance": "TERMINATE"}
                if props.spot:
                    sched.update(provisioning_model="SPOT", instance_termination_action="STOP")
                body["scheduling"] = sched
            outs = {"id": o("id"), "self_link": o("self_link"),
                    "internal_ip": o("network_interface[0].network_ip")}
            if props.public_ip:
                outs["external_ip"] = o("network_interface[0].access_config[0].nat_ip")
            return TfResult(body, outputs=outs)

        if t == "bucket":
            name = props.bucket_name or res.name
            body = {"name": name, "location": props.location or cfg.region, "storage_class": props.storage_class,
                    "uniform_bucket_level_access": props.uniform_bucket_level_access,
                    "force_destroy": props.force_destroy}
            if props.versioning:
                body["versioning"] = {"enabled": True}
            labels = _labels(cfg, props)
            if labels:
                body["labels"] = labels
            return TfResult(body, outputs={"name": o("name"), "url": o("url"), "self_link": o("self_link")})

        if t == "service_account":
            body = {"account_id": props.account_id or res.name}
            if props.display_name:
                body["display_name"] = props.display_name
            if props.description:
                body["description"] = props.description
            return TfResult(body, outputs={"id": o("id"), "email": o("email"), "name": o("name")})
        raise NotImplementedError(t)

    # ---- pulumi ----
    def pulumi_provider(self, config, stack):
        import pulumi_gcp

        return pulumi_gcp.Provider("gcp", project=config.project, region=config.region, zone=config.zone)

    def pulumi_resource(self, res, props, ctx) -> PulumiResult:
        import pulumi_gcp as gcp

        from ..render import pulumi_opts

        cfg: GcpConfig = ctx.config
        opts = pulumi_opts(ctx, res)
        t = res.type

        if t == "network":
            r = gcp.compute.Network(res.name, name=res.name, auto_create_subnetworks=props.auto_create_subnetworks,
                                    routing_mode=props.routing_mode, description=props.description or None, opts=opts)
            return PulumiResult(r, {"id": r.id, "self_link": r.self_link, "name": r.name})

        if t == "subnet":
            r = gcp.compute.Subnetwork(res.name, name=res.name, ip_cidr_range=props.cidr,
                                       region=props.region or cfg.region, network=ctx.get(props.network).self_link,
                                       private_ip_google_access=props.private_ip_google_access, opts=opts)
            return PulumiResult(r, {"id": r.id, "self_link": r.self_link, "cidr": r.ip_cidr_range})

        if t == "firewall":
            allows = [gcp.compute.FirewallAllowArgs(protocol=a.protocol, ports=a.ports or None) for a in props.allow]
            kw = {}
            if props.direction == "INGRESS":
                kw["source_ranges"] = props.source_ranges or None
                kw["source_tags"] = props.source_tags or None
            else:
                kw["destination_ranges"] = props.destination_ranges
            r = gcp.compute.Firewall(res.name, name=res.name, network=ctx.get(props.network).self_link,
                                     direction=props.direction, priority=props.priority, allows=allows,
                                     target_tags=props.target_tags or None, opts=opts, **kw)
            return PulumiResult(r, {"id": r.id, "self_link": r.self_link})

        if t == "vm":
            nic_kw = {}
            if props.subnet:
                nic_kw["subnetwork"] = ctx.get(props.subnet).self_link
            else:
                nic_kw["network"] = ctx.get(props.network).self_link
            if props.public_ip:
                nic_kw["access_configs"] = [gcp.compute.InstanceNetworkInterfaceAccessConfigArgs()]
            kw = {}
            email = ctx.get(props.service_account).email if props.service_account else props.service_account_email
            if email:
                kw["service_account"] = gcp.compute.InstanceServiceAccountArgs(
                    email=email, scopes=props.service_account_scopes)
            if props.spot or props.preemptible:
                kw["scheduling"] = gcp.compute.InstanceSchedulingArgs(
                    preemptible=True, automatic_restart=False, on_host_maintenance="TERMINATE",
                    provisioning_model="SPOT" if props.spot else None,
                    instance_termination_action="STOP" if props.spot else None)
            r = gcp.compute.Instance(
                res.name, name=res.name, machine_type=props.machine_type, zone=props.zone or cfg.zone,
                boot_disk=gcp.compute.InstanceBootDiskArgs(
                    initialize_params=gcp.compute.InstanceBootDiskInitializeParamsArgs(
                        image=props.image, size=props.disk_gb)),
                network_interfaces=[gcp.compute.InstanceNetworkInterfaceArgs(**nic_kw)],
                tags=props.tags or None, labels=_labels(cfg, props) or None, metadata=props.metadata or None,
                metadata_startup_script=props.startup_script, opts=opts, **kw)
            outs = {"id": r.id, "self_link": r.self_link,
                    "internal_ip": r.network_interfaces[0].network_ip}
            if props.public_ip:
                outs["external_ip"] = r.network_interfaces[0].access_configs[0].nat_ip
            return PulumiResult(r, outs)

        if t == "bucket":
            r = gcp.storage.Bucket(
                res.name, name=props.bucket_name or res.name, location=props.location or cfg.region,
                storage_class=props.storage_class, uniform_bucket_level_access=props.uniform_bucket_level_access,
                force_destroy=props.force_destroy,
                versioning=gcp.storage.BucketVersioningArgs(enabled=True) if props.versioning else None,
                labels=_labels(cfg, props) or None, opts=opts)
            return PulumiResult(r, {"name": r.name, "url": r.url, "self_link": r.self_link})

        if t == "service_account":
            r = gcp.serviceaccount.Account(res.name, account_id=props.account_id or res.name,
                                           display_name=props.display_name or None,
                                           description=props.description or None, opts=opts)
            return PulumiResult(r, {"id": r.id, "email": r.email, "name": r.name})
        raise NotImplementedError(t)


ADAPTER = GcpAdapter()


def _stack(name, resources, cfg=None):
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": name},
            "spec": {"provider": "gcp", "providerConfig": cfg or {"project": "my-project"}, "resources": resources}}


EXAMPLES = [
    _stack("gcp-example", [
        {"name": "sa", "type": "service_account", "properties": {"accountId": "app-runner", "displayName": "App runner"}},
        {"name": "vpc", "type": "network", "properties": {}},
        {"name": "subnet-a", "type": "subnet", "properties": {"network": "vpc", "cidr": "10.10.0.0/24"}},
        {"name": "allow-ssh", "type": "firewall", "properties": {
            "network": "vpc", "allow": [{"protocol": "tcp", "ports": ["22"]}],
            "sourceRanges": ["10.0.0.0/8"], "targetTags": ["ssh"]}},
        {"name": "web", "type": "vm", "properties": {
            "subnet": "subnet-a", "publicIp": True, "tags": ["ssh"], "serviceAccount": "sa",
            "startupScript": "#!/bin/sh\necho hi\n", "metadata": {"role": "web"}, "spot": True}},
        {"name": "data-bucket-example-1", "type": "bucket", "properties": {"versioning": True, "location": "US"}},
    ], {"project": "my-project", "labels": {"managed-by": "iacforge"}}),
]
