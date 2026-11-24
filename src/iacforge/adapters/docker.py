"""`docker` provider: local containers, images, networks and volumes.

Works against any Docker-API-compatible daemon on Linux, macOS (Docker Desktop, Colima,
OrbStack) and Windows (Docker Desktop). Terraform: ``kreuzwerker/docker ~> 3.0``;
Pulumi: ``pulumi-docker`` (v4 API).

``providerConfig.host`` is optional. When omitted the provider uses ``DOCKER_HOST`` or the
platform default socket. Examples::

    host: unix:///var/run/docker.sock                    # Linux / Docker Desktop (mac)
    host: unix:///Users/me/.colima/default/docker.sock   # Colima
    host: npipe:////./pipe/docker_engine                 # Windows Docker Desktop
    host: unix:///run/user/1000/podman/podman.sock       # rootless Podman (API-compatible)

Podman works through its Docker-compatible socket (``systemctl --user enable --now
podman.socket``); point ``host`` at it as above.

A container's image is given either as a plain reference (``image: nginx:1.27``) or as the
name of an ``image`` resource in the stack (``imageFrom: base``).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .base import (
    ALL_PLATFORMS,
    PULUMI,
    TF,
    Props,
    ProviderAdapter,
    PulumiResult,
    TfResult,
    tf_id,
)


class RegistryAuth(Props):
    """Registry credentials come from a docker config.json (default ~/.docker/config.json,
    populated by `docker login`). Literal usernames/passwords are deliberately not accepted:
    they would land in main.tf.json and state."""

    address: str = Field(description="Registry host, e.g. ghcr.io or registry-1.docker.io.")
    config_file: str | None = Field(default=None, alias="configFile",
                                    description="Path to a docker config.json holding credentials.")


class DockerConfig(Props):
    host: str | None = Field(default=None, description="Docker daemon endpoint; default: DOCKER_HOST / platform default.")
    registry_auth: list[RegistryAuth] = Field(default_factory=list, alias="registryAuth")


class ImageProps(Props):
    name: str = Field(min_length=1, description="Image reference, e.g. nginx:1.27.")
    keep_locally: bool = Field(default=False, alias="keepLocally",
                               description="Keep the image in the daemon on destroy.")


class PortMap(Props):
    internal: int = Field(ge=1, le=65535)
    external: int | None = Field(default=None, ge=1, le=65535)
    protocol: Literal["tcp", "udp", "sctp"] = "tcp"
    ip: str | None = None


class VolumeMount(Props):
    volume: str | None = Field(default=None, description="Name of a `volume` resource in the stack.")
    host_path: str | None = Field(default=None, alias="hostPath", description="Bind-mount host path.")
    container_path: str = Field(alias="containerPath", min_length=1)
    read_only: bool = Field(default=False, alias="readOnly")

    @model_validator(mode="after")
    def _one_source(self) -> VolumeMount:
        if (self.volume is None) == (self.host_path is None):
            raise ValueError("exactly one of 'volume' or 'hostPath' is required")
        return self


class ContainerProps(Props):
    image: str | None = Field(default=None, description="Image reference (e.g. alpine:3.20).")
    image_from: str | None = Field(default=None, alias="imageFrom",
                                   description="Name of an `image` resource in the stack.")
    name: str | None = Field(default=None, description="Container name; defaults to the resource name.")
    command: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    ports: list[PortMap] = Field(default_factory=list)
    volumes: list[VolumeMount] = Field(default_factory=list)
    networks: list[str] = Field(default_factory=list, description="Names of `network` resources in the stack.")
    restart: Literal["no", "on-failure", "always", "unless-stopped"] | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    memory_mb: int | None = Field(default=None, ge=4, alias="memoryMb")

    @model_validator(mode="after")
    def _one_image(self) -> ContainerProps:
        if (self.image is None) == (self.image_from is None):
            raise ValueError("exactly one of 'image' or 'imageFrom' is required")
        return self


class NetworkProps(Props):
    name: str | None = Field(default=None, description="Network name; defaults to the resource name.")
    driver: str = "bridge"
    internal: bool = False
    subnet: str | None = Field(default=None, pattern=r"^[0-9a-fA-F:.]+/\d{1,3}$")
    labels: dict[str, str] = Field(default_factory=dict)


class VolumeProps(Props):
    name: str | None = Field(default=None, description="Volume name; defaults to the resource name.")
    driver: str = "local"
    labels: dict[str, str] = Field(default_factory=dict)


def _tf_labels(labels: dict[str, str]) -> list[dict[str, str]]:
    return [{"label": k, "value": labels[k]} for k in sorted(labels)]



class DockerAdapter(ProviderAdapter):
    name = "docker"
    description = ("Local containers, images, networks and volumes via the Docker API "
                   "(Docker Desktop, Colima, OrbStack, Linux engine; Podman via its socket).")
    status = "stable"
    category = "local"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF, PULUMI})
    required_tools = ("docker",)
    pulumi_packages = ("pulumi", "pulumi-docker")
    config_model = DockerConfig
    resource_models = {"image": ImageProps, "container": ContainerProps,
                       "network": NetworkProps, "volume": VolumeProps}
    tf_types = {"image": "docker_image", "container": "docker_container",
                "network": "docker_network", "volume": "docker_volume"}
    tf_required_providers = {"docker": {"source": "kreuzwerker/docker", "version": "~> 3.0"}}
    docs_url = "https://registry.terraform.io/providers/kreuzwerker/docker/latest/docs"

    # ---- validation ----
    def references(self, res, props) -> list[str]:
        if res.type != "container":
            return []
        refs: list[str] = []
        if props.image_from:
            refs.append(props.image_from)
        refs += props.networks
        refs += [v.volume for v in props.volumes if v.volume]
        return list(dict.fromkeys(refs))

    def validate_stack(self, stack, config, props) -> list[str]:
        errs: list[str] = []
        types = {r.name: r.type for r in stack.spec.resources}

        def check(owner: str, target: str, want: str) -> None:
            if target in types and types[target] != want:
                errs.append(f"{owner}: '{target}' is a {types[target]}, expected a {want} resource")

        for r in stack.spec.resources:
            if r.type != "container":
                continue
            p = props[r.name]
            if p.image_from:
                check(r.name, p.image_from, "image")
            for n in p.networks:
                check(r.name, n, "network")
            for v in p.volumes:
                if v.volume:
                    check(r.name, v.volume, "volume")
            if len(set(p.networks)) != len(p.networks):
                errs.append(f"{r.name}: duplicate entries in networks")
        return errs

    # ---- terraform ----
    def tf_provider_blocks(self, config: DockerConfig) -> dict[str, Any]:
        block: dict[str, Any] = {}
        if config.host:
            block["host"] = config.host
        if config.registry_auth:
            auths = []
            for a in config.registry_auth:
                d: dict[str, Any] = {"address": a.address}
                if a.config_file is not None:
                    d["config_file"] = a.config_file
                auths.append(d)
            block["registry_auth"] = auths
        return {"docker": block}

    def tf_resource(self, res, props, ctx) -> TfResult:
        addr = f"{self.tf_types[res.type]}.{tf_id(res.name)}"

        def o(attr: str) -> str:
            return "${" + f"{addr}.{attr}" + "}"

        if res.type == "image":
            return TfResult(
                body={"name": props.name, "keep_locally": props.keep_locally},
                outputs={"id": o("id"), "image_id": o("image_id"), "name": o("name")},
            )
        if res.type == "network":
            body: dict[str, Any] = {"name": props.name or res.name, "driver": props.driver,
                                    "internal": props.internal}
            if props.subnet:
                body["ipam_config"] = [{"subnet": props.subnet}]
            if props.labels:
                body["labels"] = _tf_labels(props.labels)
            return TfResult(body=body, outputs={"id": o("id"), "name": o("name")})
        if res.type == "volume":
            body = {"name": props.name or res.name, "driver": props.driver}
            if props.labels:
                body["labels"] = _tf_labels(props.labels)
            return TfResult(body=body, outputs={"name": o("name")})

        # container
        body = {
            "name": props.name or res.name,
            "image": ctx.ref(props.image_from, "image_id") if props.image_from else props.image,
        }
        if props.command is not None:
            body["command"] = list(props.command)
        if props.env:
            body["env"] = [f"{k}={props.env[k]}" for k in sorted(props.env)]
        if props.ports:
            ports = []
            for p in props.ports:
                d: dict[str, Any] = {"internal": p.internal, "protocol": p.protocol}
                if p.external is not None:
                    d["external"] = p.external
                if p.ip:
                    d["ip"] = p.ip
                ports.append(d)
            body["ports"] = ports
        if props.volumes:
            vols = []
            for v in props.volumes:
                d = {"container_path": v.container_path, "read_only": v.read_only}
                if v.volume:
                    d["volume_name"] = ctx.ref(v.volume, "name")
                else:
                    d["host_path"] = v.host_path
                vols.append(d)
            body["volumes"] = vols
        if props.networks:
            body["networks_advanced"] = [{"name": ctx.ref(n, "name")} for n in props.networks]
        if props.restart:
            body["restart"] = props.restart
        if props.labels:
            body["labels"] = _tf_labels(props.labels)
        if props.memory_mb is not None:
            body["memory"] = props.memory_mb
        nd = f"{addr}.network_data"
        return TfResult(body=body, outputs={
            "id": o("id"),
            "name": o("name"),
            "ip_address": "${try(" + nd + "[0].ip_address, \"\")}",
            "ip_addresses": "${[for n in " + nd + " : n.ip_address]}",
        })

    # ---- pulumi ----
    def pulumi_provider(self, config: DockerConfig, stack):
        if not config.host and not config.registry_auth:
            return None
        import pulumi_docker as docker

        kw: dict[str, Any] = {}
        if config.host:
            kw["host"] = config.host
        if config.registry_auth:
            kw["registry_auth"] = [
                docker.ProviderRegistryAuthArgs(
                    address=a.address, config_file=a.config_file)
                for a in config.registry_auth
            ]
        return docker.Provider("docker", **kw)

    def pulumi_resource(self, res, props, ctx) -> PulumiResult:
        import pulumi_docker as docker

        from ..render import pulumi_opts

        opts = pulumi_opts(ctx, res)
        if res.type == "image":
            r = docker.RemoteImage(res.name, name=props.name, keep_locally=props.keep_locally, opts=opts)
            return PulumiResult(r, {"id": r.id, "image_id": r.image_id, "name": r.name})
        if res.type == "network":
            kw: dict[str, Any] = {"name": props.name or res.name, "driver": props.driver,
                                  "internal": props.internal}
            if props.subnet:
                kw["ipam_configs"] = [docker.NetworkIpamConfigArgs(subnet=props.subnet)]
            if props.labels:
                kw["labels"] = [docker.NetworkLabelArgs(label=k, value=props.labels[k])
                                for k in sorted(props.labels)]
            r = docker.Network(res.name, opts=opts, **kw)
            return PulumiResult(r, {"id": r.id, "name": r.name})
        if res.type == "volume":
            kw = {"name": props.name or res.name, "driver": props.driver}
            if props.labels:
                kw["labels"] = [docker.VolumeLabelArgs(label=k, value=props.labels[k])
                                for k in sorted(props.labels)]
            r = docker.Volume(res.name, opts=opts, **kw)
            return PulumiResult(r, {"name": r.name})

        kw = {"name": props.name or res.name,
              "image": ctx.get(props.image_from).image_id if props.image_from else props.image}
        if props.command is not None:
            kw["command"] = list(props.command)
        if props.env:
            kw["envs"] = [f"{k}={props.env[k]}" for k in sorted(props.env)]
        if props.ports:
            kw["ports"] = [docker.ContainerPortArgs(internal=p.internal, external=p.external,
                                                    protocol=p.protocol, ip=p.ip) for p in props.ports]
        if props.volumes:
            vols = []
            for v in props.volumes:
                vols.append(docker.ContainerVolumeArgs(
                    container_path=v.container_path, read_only=v.read_only,
                    volume_name=ctx.get(v.volume).name if v.volume else None,
                    host_path=v.host_path))
            kw["volumes"] = vols
        if props.networks:
            kw["networks_advanced"] = [docker.ContainerNetworksAdvancedArgs(name=ctx.get(n).name)
                                       for n in props.networks]
        if props.restart:
            kw["restart"] = props.restart
        if props.labels:
            kw["labels"] = [docker.ContainerLabelArgs(label=k, value=props.labels[k])
                            for k in sorted(props.labels)]
        if props.memory_mb is not None:
            kw["memory"] = props.memory_mb
        r = docker.Container(res.name, opts=opts, **kw)
        ips = r.network_datas.apply(lambda nds: [n.ip_address for n in (nds or [])])
        return PulumiResult(r, {"id": r.id, "name": r.name,
                                "ip_address": ips.apply(lambda xs: xs[0] if xs else ""),
                                "ip_addresses": ips})


ADAPTER = DockerAdapter()


EXAMPLES = [
    {
        "apiVersion": "iacforge/v1",
        "kind": "Stack",
        "metadata": {"name": "docker-web"},
        "spec": {"provider": "docker", "resources": [
            {"name": "net", "type": "network",
             "properties": {"subnet": "172.30.0.0/24", "labels": {"env": "dev"}}},
            {"name": "data", "type": "volume", "properties": {"labels": {"env": "dev"}}},
            {"name": "base", "type": "image", "properties": {"name": "nginx:1.27-alpine", "keepLocally": True}},
            {"name": "web", "type": "container", "properties": {
                "imageFrom": "base", "env": {"B": "2", "A": "1"},
                "ports": [{"internal": 80, "external": 8080}],
                "volumes": [{"volume": "data", "containerPath": "/data"}],
                "networks": ["net"], "restart": "unless-stopped",
                "labels": {"app": "web"}, "memoryMb": 128}},
            {"name": "job", "type": "container", "properties": {
                "image": "alpine:3.20", "command": ["sleep", "3600"],
                "volumes": [{"hostPath": "/tmp", "containerPath": "/host", "readOnly": True}]}},
        ]},
    }
]
