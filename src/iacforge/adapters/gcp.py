"""`gcp` provider: Google Cloud (hashicorp/google ~> 6.0 / pulumi_gcp).

Credentials are never part of the spec: use Application Default Credentials
(``gcloud auth application-default login``, ``GOOGLE_APPLICATION_CREDENTIALS``, or workload identity).
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from ..errors import UnsupportedError
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
    enable_apis: bool = Field(default=False, alias="enableApis",
                              description="Also manage the Google APIs each resource needs (google_project_service).")


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


_MEMBER_LITERAL_PUBLIC = ("allUsers", "allAuthenticatedUsers")
_SQL_ENGINE_RE = re.compile(r"^(POSTGRES_\d{2}|MYSQL_\d_\d|SQLSERVER_\d{4}_[A-Z]+)$")


def _is_literal_member(v: str) -> bool:
    return ":" in v or v in _MEMBER_LITERAL_PUBLIC


class ArtifactRegistryProps(Props):
    format: Literal["DOCKER", "MAVEN", "NPM", "PYTHON", "APT", "YUM", "GO", "GENERIC"] = "DOCKER"
    location: str | None = Field(default=None, description="Default: providerConfig.region.")
    repository_id: str | None = Field(default=None, alias="repositoryId", description="Default: resource name.")
    description: str = ""
    labels: dict[str, str] = Field(default_factory=dict)


class SecretProps(Props):
    """Container only: there is deliberately no value field (add versions out of band)."""

    replication: Literal["automatic"] | list[str] = Field(
        default="automatic", description='"automatic" or a non-empty list of regions (user-managed).')
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("replication")
    @classmethod
    def _repl(cls, v):
        if isinstance(v, list) and not v:
            raise ValueError("user-managed replication needs at least one region")
        return v


class IamBindingProps(Props):
    """Project-level IAM member."""

    role: str = Field(pattern=r"^(roles|projects/[^/]+/roles|organizations/\d+/roles)/[\w.]+$")
    member: str = Field(min_length=1, description="Literal `user:...`/`group:...` or the name of a stack `service_account`.")


class BucketIamBindingProps(IamBindingProps):
    """IAM member scoped to one bucket."""

    bucket: str = Field(description="Name of a stack `bucket` resource.")


class SecretIamBindingProps(IamBindingProps):
    """IAM member scoped to one secret."""

    secret: str = Field(description="Name of a stack `secret` resource.")


class RegistryIamBindingProps(IamBindingProps):
    """IAM member scoped to one Artifact Registry repository."""

    registry: str = Field(description="Name of a stack `artifact_registry` resource.")


class CloudRunProps(Props):
    image: str = Field(min_length=1)
    port: int = Field(default=8080, ge=1, le=65535)
    env: dict[str, str] = Field(default_factory=dict)
    secret_env: dict[str, str] = Field(default_factory=dict, alias="secretEnv",
                                       description="ENV_NAME -> name of a stack `secret` resource (latest version).")
    service_account: str | None = Field(default=None, alias="serviceAccount",
                                        description="Name of a stack `service_account` resource.")
    min_instances: int = Field(default=0, ge=0, alias="minInstances")
    max_instances: int = Field(default=10, ge=1, alias="maxInstances")
    cpu: str = "1"
    memory: str = "512Mi"
    ingress: Literal["INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER", "INGRESS_TRAFFIC_INTERNAL_ONLY",
                     "INGRESS_TRAFFIC_ALL"] = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    allow_unauthenticated: bool = Field(default=False, alias="allowUnauthenticated")
    vpc_connector: str | None = Field(default=None, alias="vpcConnector",
                                      description="Serverless VPC Access connector id (projects/.../connectors/x).")
    location: str | None = Field(default=None, description="Default: providerConfig.region.")

    @model_validator(mode="after")
    def _check(self):
        if self.min_instances > self.max_instances:
            raise ValueError("minInstances must be <= maxInstances")
        clash = set(self.env) & set(self.secret_env)
        if clash:
            raise ValueError(f"env and secretEnv both set: {', '.join(sorted(clash))}")
        return self


class GkeAutopilotProps(Props):
    network: str | None = Field(default=None, description="Name of a stack `network` resource.")
    subnet: str | None = Field(default=None, description="Name of a stack `subnet` resource.")
    release_channel: Literal["RAPID", "REGULAR", "STABLE"] = Field(default="REGULAR", alias="releaseChannel")
    private_nodes: bool = Field(default=True, alias="privateNodes")
    master_cidr: str | None = Field(default=None, alias="masterCidr", description="/28 for the private control plane.")
    deletion_protection: bool = Field(default=True, alias="deletionProtection")
    location: str | None = Field(default=None, description="Default: providerConfig.region.")

    @model_validator(mode="after")
    def _check(self):
        if self.subnet and not self.network:
            raise ValueError("`subnet` needs `network`")
        if self.master_cidr:
            _cidr(self.master_cidr)
            if not self.private_nodes:
                raise ValueError("`masterCidr` only applies with privateNodes: true")
        return self


class CloudSqlProps(Props):
    """No password field exists: use `passwordSecret` (a stack `secret`) or IAM database auth."""

    engine: str = Field(default="POSTGRES_16", description="POSTGRES_16, MYSQL_8_0, ...")
    tier: str = "db-f1-micro"
    disk_gb: int = Field(default=10, ge=10, alias="diskGb")
    network: str | None = Field(default=None, description="Name of a stack `network` resource (private IP).")
    availability: Literal["ZONAL", "REGIONAL"] = "ZONAL"
    backups: bool = True
    databases: list[str] = Field(default_factory=list)
    deletion_protection: bool = Field(default=True, alias="deletionProtection")
    password_secret: str | None = Field(default=None, alias="passwordSecret",
                                        description="Name of a stack `secret`; its latest version is the app user's password.")
    user_name: str = Field(default="app", alias="userName", description="Database user created when passwordSecret is set.")
    region: str | None = Field(default=None, description="Default: providerConfig.region.")

    @field_validator("engine")
    @classmethod
    def _engine(cls, v):
        if not _SQL_ENGINE_RE.match(v):
            raise ValueError(f"invalid engine '{v}' (e.g. POSTGRES_16, MYSQL_8_0)")
        return v

    @field_validator("databases")
    @classmethod
    def _dbs(cls, v):
        if len(set(v)) != len(v) or any(not re.match(r"^[A-Za-z0-9_-]+$", d) for d in v):
            raise ValueError("databases must be unique names of [A-Za-z0-9_-]")
        return v


# resource type -> Google API it needs (used when providerConfig.enableApis is true). Scoped IAM members
# have no entry: the resource they attach to already carries the API dependency.
_APIS = {
    "network": "compute.googleapis.com", "subnet": "compute.googleapis.com",
    "firewall": "compute.googleapis.com", "vm": "compute.googleapis.com",
    "bucket": "storage.googleapis.com", "service_account": "iam.googleapis.com",
    "artifact_registry": "artifactregistry.googleapis.com", "secret": "secretmanager.googleapis.com",
    "iam_binding": "cloudresourcemanager.googleapis.com",
    "cloud_run_service": "run.googleapis.com", "cloud_sql": "sqladmin.googleapis.com",
    "gke_autopilot": "container.googleapis.com",
}


def _labels(config: GcpConfig, props) -> dict[str, str]:
    return {**config.labels, **getattr(props, "labels", {})}


class GcpAdapter(ProviderAdapter):
    name = "gcp"
    description = ("Google Cloud: VPC, Compute VMs, GCS, service accounts, Artifact Registry, Secret Manager, IAM, "
                   "Cloud Run, Cloud SQL, GKE Autopilot.")
    status = "beta"
    backends = frozenset({"local", "gcs"})
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
        "artifact_registry": ArtifactRegistryProps,
        "secret": SecretProps,
        "iam_binding": IamBindingProps,
        "bucket_iam_binding": BucketIamBindingProps,
        "secret_iam_binding": SecretIamBindingProps,
        "registry_iam_binding": RegistryIamBindingProps,
        "cloud_run_service": CloudRunProps,
        "cloud_sql": CloudSqlProps,
        "gke_autopilot": GkeAutopilotProps,
    }
    tf_types = {
        "network": "google_compute_network",
        "subnet": "google_compute_subnetwork",
        "firewall": "google_compute_firewall",
        "vm": "google_compute_instance",
        "bucket": "google_storage_bucket",
        "service_account": "google_service_account",
        "artifact_registry": "google_artifact_registry_repository",
        "secret": "google_secret_manager_secret",
        "iam_binding": "google_project_iam_member",
        "bucket_iam_binding": "google_storage_bucket_iam_member",
        "secret_iam_binding": "google_secret_manager_secret_iam_member",
        "registry_iam_binding": "google_artifact_registry_repository_iam_member",
        "cloud_run_service": "google_cloud_run_v2_service",
        "cloud_sql": "google_sql_database_instance",
        "gke_autopilot": "google_container_cluster",
    }
    # pulumi type tokens, used by `iacforge import` under the pulumi engine (ADR 0006)
    pulumi_types = {
        "network": "gcp:compute/network:Network",
        "subnet": "gcp:compute/subnetwork:Subnetwork",
        "firewall": "gcp:compute/firewall:Firewall",
        "vm": "gcp:compute/instance:Instance",
        "bucket": "gcp:storage/bucket:Bucket",
        "service_account": "gcp:serviceaccount/account:Account",
        "artifact_registry": "gcp:artifactregistry/repository:Repository",
        "secret": "gcp:secretmanager/secret:Secret",
        "iam_binding": "gcp:projects/iAMMember:IAMMember",
        "bucket_iam_binding": "gcp:storage/bucketIAMMember:BucketIAMMember",
        "secret_iam_binding": "gcp:secretmanager/secretIamMember:SecretIamMember",
        "registry_iam_binding": "gcp:artifactregistry/repositoryIamMember:RepositoryIamMember",
        "cloud_run_service": "gcp:cloudrunv2/service:Service",
        "cloud_sql": "gcp:sql/databaseInstance:DatabaseInstance",
        "gke_autopilot": "gcp:container/cluster:Cluster",
    }
    tf_required_providers = {"google": {"source": "hashicorp/google", "version": "~> 6.0"}}
    docs_url = "https://registry.terraform.io/providers/hashicorp/google/latest/docs"

    # ---- validation ----
    def _ref_attrs(self, props) -> list[tuple[str, str, str]]:
        """(attribute label, referenced stack resource name, expected type) for every cross-reference."""
        out: list[tuple[str, str, str]] = []
        for attr, want in (("network", "network"), ("subnet", "subnet"), ("service_account", "service_account"),
                           ("password_secret", "secret"), ("bucket", "bucket"), ("secret", "secret"),
                           ("registry", "artifact_registry")):
            v = getattr(props, attr, None)
            if v:
                out.append((attr, v, want))
        for env, sec in getattr(props, "secret_env", {}).items():
            out.append((f"secretEnv.{env}", sec, "secret"))
        member = getattr(props, "member", None)
        if member and not _is_literal_member(member):
            out.append(("member", member, "service_account"))
        return out

    def references(self, res, props) -> list[str]:
        return list(dict.fromkeys(name for _, name, _ in self._ref_attrs(props)))

    def validate_stack(self, stack, config, props) -> list[str]:
        errs = []
        types = {r.name: r.type for r in stack.spec.resources}
        for r in stack.spec.resources:
            p = props[r.name]
            for attr, v, want in self._ref_attrs(p):
                if v in types and types[v] != want:
                    errs.append(f"{r.name}: `{attr}` refers to '{v}' which is a {types[v]}, expected {want}")
            if r.type == "service_account":
                aid = p.account_id or r.name
                if not _SA_RE.match(aid):
                    errs.append(f"{r.name}: service account id '{aid}' must be 6-30 chars [a-z0-9-], start with a letter")
            if r.type == "bucket" and not _BUCKET_RE.match(p.bucket_name or r.name):
                errs.append(f"{r.name}: bucket name '{p.bucket_name or r.name}' is invalid (3+ chars, lowercase)")
            if r.type == "secret" and not re.match(r"^[A-Za-z0-9_-]{1,255}$", r.name):
                errs.append(f"{r.name}: secret id must be 1-255 chars of [A-Za-z0-9_-]")
            if r.type == "artifact_registry" and not re.match(r"^[a-z][a-z0-9-]{0,62}$", p.repository_id or r.name):
                errs.append(f"{r.name}: repository id must be lowercase letters, digits, hyphens")
            if r.type in ("cloud_run_service", "cloud_sql", "gke_autopilot") \
                    and not re.match(r"^[a-z][a-z0-9-]{0,48}[a-z0-9]$", r.name):
                errs.append(f"{r.name}: name must be lowercase letters, digits, hyphens (2-50 chars, start with a letter)")
        return errs

    # ---- import (ADR 0006) ----
    def import_id(self, res, props, config) -> str:
        p, t = config.project, res.type
        if t == "network":
            return f"projects/{p}/global/networks/{res.name}"
        if t == "subnet":
            return f"projects/{p}/regions/{props.region or config.region}/subnetworks/{res.name}"
        if t == "firewall":
            return f"projects/{p}/global/firewalls/{res.name}"
        if t == "vm":
            return f"projects/{p}/zones/{props.zone or config.zone}/instances/{res.name}"
        if t == "bucket":
            return f"{p}/{props.bucket_name or res.name}"
        if t == "service_account":
            return f"projects/{p}/serviceAccounts/{props.account_id or res.name}@{p}.iam.gserviceaccount.com"
        if t == "artifact_registry":
            return f"projects/{p}/locations/{props.location or config.region}/repositories/{props.repository_id or res.name}"
        if t == "secret":
            return f"projects/{p}/secrets/{res.name}"
        if t == "cloud_run_service":
            return f"projects/{p}/locations/{props.location or config.region}/services/{res.name}"
        if t == "cloud_sql":
            return f"projects/{p}/instances/{res.name}"
        if t == "gke_autopilot":
            return f"projects/{p}/locations/{props.location or config.region}/clusters/{res.name}"
        if t == "iam_binding":
            if not _is_literal_member(props.member):
                raise UnsupportedError(f"{res.name}: member is a stack service_account; pass the import id explicitly "
                                       f"('{p} {props.role} serviceAccount:<email>')")
            return f"{p} {props.role} {props.member}"
        raise UnsupportedError(f"{res.name}: cannot derive an import id for type '{t}' (it depends on another "
                               f"resource's real name); pass the id explicitly")

    # ---- terraform ----
    def tf_provider_blocks(self, config):
        return {"google": {"project": config.project, "region": config.region, "zone": config.zone}}

    def tf_resource(self, res, props, ctx) -> TfResult:
        result = self._tf_resource(res, props, ctx)
        api = _APIS.get(res.type) if ctx.config.enable_apis else None
        if api:
            block = f"{tf_id(res.name)}_api"
            service = f"google_project_service.{block}"
            result.extra.setdefault("google_project_service", {})[block] = {
                "service": api, "disable_on_destroy": False}
            # The engine overwrites depends_on when the resource has stack dependencies, so also reference the
            # service through `project`: an implicit dependency that survives that overwrite.
            result.body["project"] = "${" + service + ".project}"
            result.body["depends_on"] = sorted({*(ctx.address(d) for d in res.depends_on), service})
        return result

    def _tf_resource(self, res, props, ctx) -> TfResult:
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

        if t == "artifact_registry":
            loc = props.location or cfg.region
            body = {"repository_id": props.repository_id or res.name, "format": props.format, "location": loc}
            if props.description:
                body["description"] = props.description
            labels = _labels(cfg, props)
            if labels:
                body["labels"] = labels
            host = f"{o('location')}-{props.format.lower()}.pkg.dev"
            url = f"{host}/{o('project')}/{o('repository_id')}"
            return TfResult(body, outputs={"id": o("id"), "name": o("name"), "repository_url": url})

        if t == "secret":
            repl = ({"auto": {}} if props.replication == "automatic"
                    else {"user_managed": {"replicas": [{"location": loc} for loc in props.replication]}})
            body = {"secret_id": res.name, "replication": repl}
            labels = _labels(cfg, props)
            if labels:
                body["labels"] = labels
            return TfResult(body, outputs={"id": o("id"), "secret_id": o("secret_id")})

        if t == "iam_binding":
            member = props.member if _is_literal_member(props.member) \
                else "serviceAccount:" + ctx.ref(props.member, "email")
            return TfResult({"project": cfg.project, "role": props.role, "member": member}, outputs={"id": o("id")})

        if t in ("bucket_iam_binding", "secret_iam_binding", "registry_iam_binding"):
            member = props.member if _is_literal_member(props.member) \
                else "serviceAccount:" + ctx.ref(props.member, "email")
            body = {"role": props.role, "member": member}
            if t == "bucket_iam_binding":
                body["bucket"] = ctx.ref(props.bucket, "name")
            elif t == "secret_iam_binding":
                body["secret_id"] = ctx.ref(props.secret, "secret_id")
            else:
                body["repository"] = ctx.ref(props.registry, "repository_id")
                body["location"] = ctx.ref(props.registry, "location")
            return TfResult(body, outputs={"id": o("id")})

        if t == "cloud_run_service":
            loc = props.location or cfg.region
            envs = [{"name": k, "value": v} for k, v in sorted(props.env.items())]
            for k, sec in sorted(props.secret_env.items()):
                envs.append({"name": k, "value_source": {"secret_key_ref": {
                    "secret": ctx.ref(sec, "secret_id"), "version": "latest"}}})
            container: dict = {"image": props.image, "ports": {"container_port": props.port},
                               "resources": {"limits": {"cpu": props.cpu, "memory": props.memory}}}
            if envs:
                container["env"] = envs
            template: dict = {"containers": [container],
                              "scaling": {"min_instance_count": props.min_instances,
                                          "max_instance_count": props.max_instances}}
            if props.service_account:
                template["service_account"] = ctx.ref(props.service_account, "email")
            if props.vpc_connector:
                template["vpc_access"] = {"connector": props.vpc_connector}
            body = {"name": res.name, "location": loc, "ingress": props.ingress, "template": template}
            extra = {}
            if props.allow_unauthenticated:
                extra["google_cloud_run_v2_service_iam_member"] = {f"{tf_id(res.name)}_invoker": {
                    "name": o("name"), "location": o("location"), "project": o("project"),
                    "role": "roles/run.invoker", "member": "allUsers"}}
            return TfResult(body, extra=extra, outputs={"id": o("id"), "uri": o("uri")})

        if t == "cloud_sql":
            settings: dict = {"tier": props.tier, "disk_size": props.disk_gb, "availability_type": props.availability,
                              "deletion_protection_enabled": props.deletion_protection}
            ipc: dict = {"ipv4_enabled": not props.network}
            if props.network:
                ipc["private_network"] = ctx.ref(props.network, "self_link")
            settings["ip_configuration"] = ipc
            backup: dict = {"enabled": props.backups}
            if props.backups and props.engine.startswith("POSTGRES"):
                backup["point_in_time_recovery_enabled"] = True
            settings["backup_configuration"] = backup
            body = {"name": res.name, "database_version": props.engine, "region": props.region or cfg.region,
                    "deletion_protection": props.deletion_protection, "settings": settings}
            extra = {}
            tid = tf_id(res.name)
            for d in props.databases:
                extra.setdefault("google_sql_database", {})[f"{tid}_db_{tf_id(d)}"] = {"name": d, "instance": o("name")}
            data = {}
            if props.password_secret:
                data["google_secret_manager_secret_version_access"] = {f"{tid}_pw": {
                    "secret": ctx.ref(props.password_secret, "secret_id")}}
                extra["google_sql_user"] = {f"{tid}_user": {
                    "name": props.user_name, "instance": o("name"),
                    "password": "${data.google_secret_manager_secret_version_access." + f"{tid}_pw.secret_data" + "}"}}
            return TfResult(body, extra=extra, data=data, outputs={
                "id": o("id"), "connection_name": o("connection_name"), "private_ip": o("private_ip_address")})

        if t == "gke_autopilot":
            body = {"name": res.name, "location": props.location or cfg.region, "enable_autopilot": True,
                    "deletion_protection": props.deletion_protection,
                    "release_channel": {"channel": props.release_channel}, "ip_allocation_policy": {}}
            if props.network:
                body["network"] = ctx.ref(props.network, "self_link")
            if props.subnet:
                body["subnetwork"] = ctx.ref(props.subnet, "self_link")
            if props.private_nodes:
                pcc: dict = {"enable_private_nodes": True}
                if props.master_cidr:
                    pcc["master_ipv4_cidr_block"] = props.master_cidr
                body["private_cluster_config"] = pcc
            return TfResult(body, outputs={"id": o("id"), "endpoint": o("endpoint"), "name": o("name")})
        raise NotImplementedError(t)

    # ---- pulumi ----
    def pulumi_provider(self, config, stack):
        import pulumi_gcp

        return pulumi_gcp.Provider("gcp", project=config.project, region=config.region, zone=config.zone)

    def pulumi_resource(self, res, props, ctx) -> PulumiResult:
        import pulumi
        import pulumi_gcp as gcp

        from ..render import pulumi_opts

        cfg: GcpConfig = ctx.config
        t = res.type
        api = _APIS.get(t) if cfg.enable_apis else None
        if api:
            svc = gcp.projects.Service(
                f"{res.name}-api", service=api, disable_on_destroy=False,
                opts=pulumi.ResourceOptions(provider=ctx.provider) if ctx.provider is not None else None)
            deps = [ctx.resources[d] for d in res.depends_on if d in ctx.resources]
            opts = pulumi_opts(ctx, res, depends_on=[*deps, svc])
        else:
            opts = pulumi_opts(ctx, res)
        helper_opts = pulumi.ResourceOptions(provider=ctx.provider) if ctx.provider is not None else None

        def member_of(m):
            return m if _is_literal_member(m) else pulumi.Output.concat("serviceAccount:", ctx.get(m).email)

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

        if t == "artifact_registry":
            loc = props.location or cfg.region
            r = gcp.artifactregistry.Repository(
                res.name, repository_id=props.repository_id or res.name, format=props.format, location=loc,
                description=props.description or None, labels=_labels(cfg, props) or None, opts=opts)
            url = pulumi.Output.concat(r.location, f"-{props.format.lower()}.pkg.dev/", r.project, "/", r.repository_id)
            return PulumiResult(r, {"id": r.id, "name": r.name, "repository_url": url})

        if t == "secret":
            if props.replication == "automatic":
                repl = gcp.secretmanager.SecretReplicationArgs(auto=gcp.secretmanager.SecretReplicationAutoArgs())
            else:
                repl = gcp.secretmanager.SecretReplicationArgs(
                    user_managed=gcp.secretmanager.SecretReplicationUserManagedArgs(
                        replicas=[gcp.secretmanager.SecretReplicationUserManagedReplicaArgs(location=x)
                                  for x in props.replication]))
            r = gcp.secretmanager.Secret(res.name, secret_id=res.name, replication=repl,
                                         labels=_labels(cfg, props) or None, opts=opts)
            return PulumiResult(r, {"id": r.id, "secret_id": r.secret_id})

        if t == "iam_binding":
            r = gcp.projects.IAMMember(res.name, project=cfg.project, role=props.role,
                                       member=member_of(props.member), opts=opts)
            return PulumiResult(r, {"id": r.id})

        if t == "bucket_iam_binding":
            r = gcp.storage.BucketIAMMember(res.name, bucket=ctx.get(props.bucket).name, role=props.role,
                                            member=member_of(props.member), opts=opts)
            return PulumiResult(r, {"id": r.id})

        if t == "secret_iam_binding":
            r = gcp.secretmanager.SecretIamMember(res.name, secret_id=ctx.get(props.secret).secret_id,
                                                  role=props.role, member=member_of(props.member), opts=opts)
            return PulumiResult(r, {"id": r.id})

        if t == "registry_iam_binding":
            repo = ctx.get(props.registry)
            r = gcp.artifactregistry.RepositoryIamMember(
                res.name, repository=repo.repository_id, location=repo.location, role=props.role,
                member=member_of(props.member), opts=opts)
            return PulumiResult(r, {"id": r.id})

        if t == "cloud_run_service":
            loc = props.location or cfg.region
            run = gcp.cloudrunv2
            envs = [run.ServiceTemplateContainerEnvArgs(name=k, value=v) for k, v in sorted(props.env.items())]
            for k, sec in sorted(props.secret_env.items()):
                envs.append(run.ServiceTemplateContainerEnvArgs(
                    name=k, value_source=run.ServiceTemplateContainerEnvValueSourceArgs(
                        secret_key_ref=run.ServiceTemplateContainerEnvValueSourceSecretKeyRefArgs(
                            secret=ctx.get(sec).secret_id, version="latest"))))
            kw = {}
            if props.service_account:
                kw["service_account"] = ctx.get(props.service_account).email
            if props.vpc_connector:
                kw["vpc_access"] = run.ServiceTemplateVpcAccessArgs(connector=props.vpc_connector)
            template = run.ServiceTemplateArgs(
                containers=[run.ServiceTemplateContainerArgs(
                    image=props.image, envs=envs or None,
                    ports=run.ServiceTemplateContainerPortsArgs(container_port=props.port),
                    resources=run.ServiceTemplateContainerResourcesArgs(
                        limits={"cpu": props.cpu, "memory": props.memory}))],
                scaling=run.ServiceTemplateScalingArgs(
                    min_instance_count=props.min_instances, max_instance_count=props.max_instances), **kw)
            r = run.Service(res.name, name=res.name, location=loc, ingress=props.ingress, template=template, opts=opts)
            if props.allow_unauthenticated:
                run.ServiceIamMember(f"{res.name}-invoker", name=r.name, location=r.location, project=r.project,
                                     role="roles/run.invoker", member="allUsers", opts=helper_opts)
            return PulumiResult(r, {"id": r.id, "uri": r.uri})

        if t == "cloud_sql":
            sql = gcp.sql
            ipc = sql.DatabaseInstanceSettingsIpConfigurationArgs(
                ipv4_enabled=not props.network,
                private_network=ctx.get(props.network).self_link if props.network else None)
            backup = sql.DatabaseInstanceSettingsBackupConfigurationArgs(
                enabled=props.backups,
                point_in_time_recovery_enabled=True if props.backups and props.engine.startswith("POSTGRES") else None)
            r = sql.DatabaseInstance(
                res.name, name=res.name, database_version=props.engine, region=props.region or cfg.region,
                deletion_protection=props.deletion_protection,
                settings=sql.DatabaseInstanceSettingsArgs(
                    tier=props.tier, disk_size=props.disk_gb, availability_type=props.availability,
                    deletion_protection_enabled=props.deletion_protection, ip_configuration=ipc,
                    backup_configuration=backup), opts=opts)
            for d in props.databases:
                sql.Database(f"{res.name}-db-{d}", name=d, instance=r.name, opts=helper_opts)
            if props.password_secret:
                pw = gcp.secretmanager.get_secret_version_access_output(
                    secret=ctx.get(props.password_secret).secret_id).secret_data
                sql.User(f"{res.name}-user", name=props.user_name, instance=r.name, password=pw, opts=helper_opts)
            return PulumiResult(r, {"id": r.id, "connection_name": r.connection_name,
                                    "private_ip": r.private_ip_address})

        if t == "gke_autopilot":
            c = gcp.container
            kw = {}
            if props.network:
                kw["network"] = ctx.get(props.network).self_link
            if props.subnet:
                kw["subnetwork"] = ctx.get(props.subnet).self_link
            if props.private_nodes:
                kw["private_cluster_config"] = c.ClusterPrivateClusterConfigArgs(
                    enable_private_nodes=True, master_ipv4_cidr_block=props.master_cidr)
            r = c.Cluster(res.name, name=res.name, location=props.location or cfg.region, enable_autopilot=True,
                          deletion_protection=props.deletion_protection,
                          release_channel=c.ClusterReleaseChannelArgs(channel=props.release_channel),
                          ip_allocation_policy=c.ClusterIpAllocationPolicyArgs(), opts=opts, **kw)
            return PulumiResult(r, {"id": r.id, "endpoint": r.endpoint, "name": r.name})
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
    _stack("gcp-platform-example", [
        {"name": "run-sa", "type": "service_account", "properties": {"accountId": "run-app"}},
        {"name": "vpc", "type": "network", "properties": {}},
        {"name": "subnet-a", "type": "subnet", "properties": {"network": "vpc", "cidr": "10.20.0.0/20"}},
        {"name": "images", "type": "artifact_registry", "properties": {"format": "DOCKER", "description": "app images"}},
        {"name": "api-key", "type": "secret", "properties": {}},
        {"name": "db-pass", "type": "secret", "properties": {"replication": ["us-central1", "us-east1"]}},
        {"name": "artifacts-bucket-example-1", "type": "bucket", "properties": {}},
        {"name": "run-project-role", "type": "iam_binding", "properties": {
            "role": "roles/logging.logWriter", "member": "run-sa"}},
        {"name": "dev-viewer", "type": "iam_binding", "properties": {
            "role": "roles/viewer", "member": "user:dev@example.com"}},
        {"name": "run-reads-key", "type": "secret_iam_binding", "properties": {
            "role": "roles/secretmanager.secretAccessor", "member": "run-sa", "secret": "api-key"}},
        {"name": "run-pulls-images", "type": "registry_iam_binding", "properties": {
            "role": "roles/artifactregistry.reader", "member": "run-sa", "registry": "images"}},
        {"name": "run-writes-bucket", "type": "bucket_iam_binding", "properties": {
            "role": "roles/storage.objectAdmin", "member": "run-sa", "bucket": "artifacts-bucket-example-1"}},
        {"name": "web-app", "type": "cloud_run_service", "properties": {
            "image": "us-docker.pkg.dev/cloudrun/container/hello", "env": {"MODE": "prod"},
            "secretEnv": {"API_KEY": "api-key"}, "serviceAccount": "run-sa", "maxInstances": 3,
            "allowUnauthenticated": True, "ingress": "INGRESS_TRAFFIC_ALL"}},
        {"name": "app-db", "type": "cloud_sql", "properties": {
            "network": "vpc", "databases": ["app"], "passwordSecret": "db-pass"}},
        {"name": "cluster", "type": "gke_autopilot", "properties": {
            "network": "vpc", "subnet": "subnet-a", "masterCidr": "172.16.0.0/28"}},
    ], {"project": "my-project", "enableApis": True}),
]
