"""`aws` provider: Amazon Web Services (hashicorp/aws ~> 5.0 / pulumi_aws). Scaffold.

Credentials are never part of the spec: use the ambient AWS environment (env vars, shared
config/credentials, SSO) and optionally name a ``profile`` in providerConfig.
"""

from __future__ import annotations

import ipaddress

from pydantic import Field, field_validator, model_validator

from .base import ALL_PLATFORMS, PULUMI, TF, Props, ProviderAdapter, PulumiResult, TfResult, tf_id


def _cidr(v: str) -> str:
    try:
        ipaddress.ip_network(v, strict=False)
    except ValueError as e:
        raise ValueError(f"invalid CIDR '{v}': {e}") from None
    return v


class AwsConfig(Props):
    region: str = "us-east-1"
    profile: str | None = None
    default_tags: dict[str, str] = Field(default_factory=dict, alias="defaultTags")


class VpcProps(Props):
    cidr: str
    enable_dns_hostnames: bool = Field(default=True, alias="enableDnsHostnames")
    enable_dns_support: bool = Field(default=True, alias="enableDnsSupport")
    tags: dict[str, str] = Field(default_factory=dict)

    _v = field_validator("cidr")(lambda cls, v: _cidr(v))


class SubnetProps(Props):
    vpc: str = Field(description="Name of a stack `vpc` resource.")
    cidr: str
    availability_zone: str | None = Field(default=None, alias="availabilityZone")
    public: bool = False
    tags: dict[str, str] = Field(default_factory=dict)

    _v = field_validator("cidr")(lambda cls, v: _cidr(v))


class Rule(Props):
    protocol: str = "tcp"
    from_port: int = Field(default=0, ge=0, le=65535, alias="fromPort")
    to_port: int | None = Field(default=None, ge=0, le=65535, alias="toPort")
    cidrs: list[str] = Field(default_factory=lambda: ["0.0.0.0/0"])
    description: str = ""

    @field_validator("cidrs")
    @classmethod
    def _c(cls, v):
        return [_cidr(x) for x in v]

    @model_validator(mode="after")
    def _p(self):
        if self.to_port is None:
            self.to_port = self.from_port
        if self.protocol in ("-1", "all"):
            self.protocol, self.from_port, self.to_port = "-1", 0, 0
        elif self.to_port < self.from_port:
            raise ValueError("toPort must be >= fromPort")
        return self


class SecurityGroupProps(Props):
    vpc: str = Field(description="Name of a stack `vpc` resource.")
    description: str = "Managed by iacforge"
    ingress: list[Rule] = Field(default_factory=list)
    egress: list[Rule] | None = Field(default=None, description="Default: allow all outbound.")
    tags: dict[str, str] = Field(default_factory=dict)


class AmiLookup(Props):
    owner: str = Field(description="Owner account id or alias, e.g. 099720109477 or amazon.")
    name_pattern: str = Field(alias="namePattern")


class VmProps(Props):
    instance_type: str = Field(default="t3.micro", alias="instanceType")
    ami: str | None = None
    ami_lookup: AmiLookup | None = Field(default=None, alias="amiLookup")
    subnet: str | None = Field(default=None, description="Name of a stack `subnet` resource.")
    security_groups: list[str] = Field(default_factory=list, alias="securityGroups")
    key_name: str | None = Field(default=None, alias="keyName")
    user_data: str | None = Field(default=None, alias="userData")
    public_ip: bool = Field(default=False, alias="publicIp")
    tags: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _a(self):
        if bool(self.ami) == bool(self.ami_lookup):
            raise ValueError("set exactly one of `ami` / `amiLookup`")
        return self


class BucketProps(Props):
    bucket_name: str | None = Field(default=None, alias="bucketName", description="Globally unique; default: resource name.")
    versioning: bool = False
    force_destroy: bool = Field(default=False, alias="forceDestroy")
    tags: dict[str, str] = Field(default_factory=dict)


class AwsAdapter(ProviderAdapter):
    name = "aws"
    description = "Amazon Web Services: VPC, subnets, security groups, EC2 instances, S3 buckets."
    status = "scaffold"
    category = "cloud"
    platforms = ALL_PLATFORMS
    engines = frozenset({TF, PULUMI})
    required_tools = ()
    pulumi_packages = ("pulumi", "pulumi-aws")
    config_model = AwsConfig
    resource_models = {"vpc": VpcProps, "subnet": SubnetProps, "security_group": SecurityGroupProps,
                       "vm": VmProps, "bucket": BucketProps}
    tf_types = {"vpc": "aws_vpc", "subnet": "aws_subnet", "security_group": "aws_security_group",
                "vm": "aws_instance", "bucket": "aws_s3_bucket"}
    tf_required_providers = {"aws": {"source": "hashicorp/aws", "version": "~> 5.0"}}
    docs_url = "https://registry.terraform.io/providers/hashicorp/aws/latest/docs"

    def references(self, res, props) -> list[str]:
        out = []
        for attr in ("vpc", "subnet"):
            v = getattr(props, attr, None)
            if v:
                out.append(v)
        out += list(getattr(props, "security_groups", []))
        return out

    def validate_stack(self, stack, config, props) -> list[str]:
        types = {r.name: r.type for r in stack.spec.resources}
        errs = []
        for r in stack.spec.resources:
            p = props[r.name]
            checks = [(a, getattr(p, a, None), w) for a, w in (("vpc", "vpc"), ("subnet", "subnet"))]
            checks += [("securityGroups", s, "security_group") for s in getattr(p, "security_groups", [])]
            for attr, v, want in checks:
                if v and v in types and types[v] != want:
                    errs.append(f"{r.name}: `{attr}` refers to '{v}' which is a {types[v]}, expected {want}")
        return errs

    def tf_provider_blocks(self, config):
        blk = {"region": config.region}
        if config.profile:
            blk["profile"] = config.profile
        if config.default_tags:
            blk["default_tags"] = {"tags": config.default_tags}
        return {"aws": blk}

    @staticmethod
    def _rule_tf(r: Rule) -> dict:
        return {"protocol": r.protocol, "from_port": r.from_port, "to_port": r.to_port,
                "cidr_blocks": r.cidrs, "description": r.description,
                "ipv6_cidr_blocks": [], "prefix_list_ids": [], "security_groups": [], "self": False}

    def tf_resource(self, res, props, ctx) -> TfResult:
        tid = tf_id(res.name)
        addr = f"{self.tf_types[res.type]}.{tid}"
        o = lambda attr: "${" + f"{addr}.{attr}" + "}"
        tags = lambda p: {"Name": res.name, **p.tags}
        t = res.type

        if t == "vpc":
            body = {"cidr_block": props.cidr, "enable_dns_hostnames": props.enable_dns_hostnames,
                    "enable_dns_support": props.enable_dns_support, "tags": tags(props)}
            return TfResult(body, outputs={"id": o("id"), "arn": o("arn"), "cidr": o("cidr_block")})

        if t == "subnet":
            body = {"vpc_id": ctx.ref(props.vpc, "id"), "cidr_block": props.cidr,
                    "map_public_ip_on_launch": props.public, "tags": tags(props)}
            if props.availability_zone:
                body["availability_zone"] = props.availability_zone
            return TfResult(body, outputs={"id": o("id"), "arn": o("arn")})

        if t == "security_group":
            egress = props.egress if props.egress is not None else [Rule(protocol="-1")]
            body = {"name": res.name, "description": props.description, "vpc_id": ctx.ref(props.vpc, "id"),
                    "ingress": [self._rule_tf(r) for r in props.ingress],
                    "egress": [self._rule_tf(r) for r in egress], "tags": tags(props)}
            return TfResult(body, outputs={"id": o("id"), "arn": o("arn")})

        if t == "vm":
            result = TfResult(body={})
            if props.ami_lookup:
                ami_name = f"{tid}_ami"
                result.data = {"aws_ami": {ami_name: {
                    "most_recent": True, "owners": [props.ami_lookup.owner],
                    "filter": [{"name": "name", "values": [props.ami_lookup.name_pattern]}]}}}
                ami = "${data.aws_ami." + ami_name + ".id}"
            else:
                ami = props.ami
            body = {"ami": ami, "instance_type": props.instance_type, "tags": tags(props)}
            if props.subnet:
                body["subnet_id"] = ctx.ref(props.subnet, "id")
            if props.security_groups:
                body["vpc_security_group_ids"] = [ctx.ref(s, "id") for s in props.security_groups]
            if props.key_name:
                body["key_name"] = props.key_name
            if props.user_data:
                body["user_data"] = props.user_data
            if props.public_ip:
                body["associate_public_ip_address"] = True
            result.body = body
            result.outputs = {"id": o("id"), "private_ip": o("private_ip"), "public_ip": o("public_ip"),
                              "arn": o("arn")}
            return result

        if t == "bucket":
            body = {"bucket": props.bucket_name or res.name, "force_destroy": props.force_destroy, "tags": props.tags}
            extra = {}
            if props.versioning:
                extra = {"aws_s3_bucket_versioning": {f"{tid}_versioning": {
                    "bucket": o("id"), "versioning_configuration": {"status": "Enabled"}}}}
            return TfResult(body, extra=extra, outputs={"id": o("id"), "arn": o("arn"),
                                                        "domain": o("bucket_regional_domain_name")})
        raise NotImplementedError(t)

    # ---- pulumi ----
    def pulumi_provider(self, config, stack):
        import pulumi_aws

        kw = {"region": config.region}
        if config.profile:
            kw["profile"] = config.profile
        if config.default_tags:
            kw["default_tags"] = pulumi_aws.ProviderDefaultTagsArgs(tags=config.default_tags)
        return pulumi_aws.Provider("aws", **kw)

    def pulumi_resource(self, res, props, ctx) -> PulumiResult:
        import pulumi
        import pulumi_aws as aws

        from ..render import pulumi_opts

        opts = pulumi_opts(ctx, res)
        tags = lambda p: {"Name": res.name, **p.tags}
        t = res.type

        if t == "vpc":
            r = aws.ec2.Vpc(res.name, cidr_block=props.cidr, enable_dns_hostnames=props.enable_dns_hostnames,
                            enable_dns_support=props.enable_dns_support, tags=tags(props), opts=opts)
            return PulumiResult(r, {"id": r.id, "arn": r.arn, "cidr": r.cidr_block})

        if t == "subnet":
            r = aws.ec2.Subnet(res.name, vpc_id=ctx.get(props.vpc).id, cidr_block=props.cidr,
                               availability_zone=props.availability_zone,
                               map_public_ip_on_launch=props.public, tags=tags(props), opts=opts)
            return PulumiResult(r, {"id": r.id, "arn": r.arn})

        if t == "security_group":
            def rules(rs):
                return [aws.ec2.SecurityGroupIngressArgs(protocol=x.protocol, from_port=x.from_port,
                                                         to_port=x.to_port, cidr_blocks=x.cidrs,
                                                         description=x.description) for x in rs]
            egress = props.egress if props.egress is not None else [Rule(protocol="-1")]
            r = aws.ec2.SecurityGroup(
                res.name, name=res.name, description=props.description, vpc_id=ctx.get(props.vpc).id,
                ingress=rules(props.ingress),
                egress=[aws.ec2.SecurityGroupEgressArgs(protocol=x.protocol, from_port=x.from_port,
                                                        to_port=x.to_port, cidr_blocks=x.cidrs,
                                                        description=x.description) for x in egress],
                tags=tags(props), opts=opts)
            return PulumiResult(r, {"id": r.id, "arn": r.arn})

        if t == "vm":
            if props.ami_lookup:
                ami = aws.ec2.get_ami_output(
                    most_recent=True, owners=[props.ami_lookup.owner],
                    filters=[aws.ec2.GetAmiFilterArgs(name="name", values=[props.ami_lookup.name_pattern])],
                    opts=pulumi.InvokeOutputOptions(provider=ctx.provider) if ctx.provider is not None
                    and hasattr(pulumi, "InvokeOutputOptions") else None).id
            else:
                ami = props.ami
            r = aws.ec2.Instance(
                res.name, ami=ami, instance_type=props.instance_type,
                subnet_id=ctx.get(props.subnet).id if props.subnet else None,
                vpc_security_group_ids=[ctx.get(s).id for s in props.security_groups] or None,
                key_name=props.key_name, user_data=props.user_data,
                associate_public_ip_address=True if props.public_ip else None, tags=tags(props), opts=opts)
            return PulumiResult(r, {"id": r.id, "private_ip": r.private_ip, "public_ip": r.public_ip, "arn": r.arn})

        if t == "bucket":
            r = aws.s3.BucketV2(res.name, bucket=props.bucket_name or res.name,
                                force_destroy=props.force_destroy, tags=props.tags, opts=opts)
            if props.versioning:
                aws.s3.BucketVersioningV2(
                    f"{res.name}-versioning", bucket=r.id,
                    versioning_configuration=aws.s3.BucketVersioningV2VersioningConfigurationArgs(status="Enabled"),
                    opts=pulumi_opts(ctx, res.model_copy(update={"depends_on": []}), depends_on=[r]))
            return PulumiResult(r, {"id": r.id, "arn": r.arn, "domain": r.bucket_regional_domain_name})
        raise NotImplementedError(t)


ADAPTER = AwsAdapter()

EXAMPLES = [{
    "apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "aws-example"},
    "spec": {"provider": "aws", "providerConfig": {"region": "us-east-1", "defaultTags": {"managed-by": "iacforge"}},
             "resources": [
        {"name": "vpc", "type": "vpc", "properties": {"cidr": "10.20.0.0/16"}},
        {"name": "pub-a", "type": "subnet", "properties": {
            "vpc": "vpc", "cidr": "10.20.1.0/24", "availabilityZone": "us-east-1a", "public": True}},
        {"name": "web-sg", "type": "security_group", "properties": {
            "vpc": "vpc", "ingress": [{"protocol": "tcp", "fromPort": 22, "cidrs": ["10.0.0.0/8"]},
                                       {"protocol": "tcp", "fromPort": 80, "toPort": 80}]}},
        {"name": "web", "type": "vm", "properties": {
            "subnet": "pub-a", "securityGroups": ["web-sg"], "publicIp": True, "userData": "#!/bin/sh\necho hi\n",
            "amiLookup": {"owner": "099720109477",
                          "namePattern": "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"}}},
        {"name": "assets-example-bucket-1", "type": "bucket", "properties": {"versioning": True}},
    ]},
}]
