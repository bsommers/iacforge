# Provider: aws

| | |
|---|---|
| Status | scaffold |
| Category | cloud |
| Host platforms | darwin, linux, windows |
| Engines | opentofu, terraform, pulumi |
| Host tools | none (engine only) |
| Resource types | `bucket`, `security_group`, `subnet`, `vm`, `vpc` |
| Upstream docs | <https://registry.terraform.io/providers/hashicorp/aws/latest/docs> |

Amazon Web Services: VPCs, subnets, security groups, EC2 instances and S3 buckets (`hashicorp/aws ~> 5.0`; `pulumi-aws` for Pulumi). **Status: scaffold**; the schema and rendering exist and are unit tested, but it has not been exercised against a live account. Expect changes.

- Platforms: Linux, macOS, Windows. Engines: OpenTofu, Terraform, Pulumi.
- **Authentication:** never put credentials in a spec. Use the ambient AWS environment (`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`, `AWS_PROFILE`, shared config, or SSO via `aws sso login`) and optionally name a `profile` in `providerConfig`.
- References: `subnet.vpc`, `security_group.vpc`, `vm.subnet`, `vm.securityGroups` name other stack resources and are type-checked.
- A `vm` needs exactly one of `ami` or `amiLookup`.
- Planning and applying creates billable resources.

Run `iacforge schema aws --json` for the machine-readable JSON Schema of everything below. Unknown keys are rejected, so typos fail at `validate`.

Property names are camelCase as written in the spec. Defaults shown as "unset" mean the property is omitted and the provider or engine default applies.

## providerConfig

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `region` | string | no | `"us-east-1"` |  |
| `profile` | string | no | unset |  |
| `defaultTags` | map of string | no | `{}` |  |

## Resource types

### `bucket`

Terraform/OpenTofu type: `aws_s3_bucket`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `bucketName` | string | no | unset | Globally unique; default: resource name. |
| `versioning` | boolean | no | `false` |  |
| `forceDestroy` | boolean | no | `false` |  |
| `tags` | map of string | no | `{}` |  |

Outputs: `arn`, `domain`, `id`

### `security_group`

Terraform/OpenTofu type: `aws_security_group`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `vpc` | string | yes | - | Name of a stack `vpc` resource. |
| `description` | string | no | `"Managed by iacforge"` |  |
| `ingress` | list of `Rule` | no | `[]` |  |
| `egress` | list of `Rule` | no | unset | Default: allow all outbound. |
| `tags` | map of string | no | `{}` |  |

`Rule` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `protocol` | string | no | `"tcp"` |  |
| `fromPort` | integer (min 0, max 65535) | no | `0` |  |
| `toPort` | integer (min 0, max 65535) | no | unset |  |
| `cidrs` | list of string | no | `["0.0.0.0/0"]` |  |
| `description` | string | no | `""` |  |

Outputs: `arn`, `id`

### `subnet`

Terraform/OpenTofu type: `aws_subnet`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `vpc` | string | yes | - | Name of a stack `vpc` resource. |
| `cidr` | string | yes | - |  |
| `availabilityZone` | string | no | unset |  |
| `public` | boolean | no | `false` |  |
| `tags` | map of string | no | `{}` |  |

Outputs: `arn`, `id`

### `vm`

Terraform/OpenTofu type: `aws_instance`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `instanceType` | string | no | `"t3.micro"` |  |
| `ami` | string | no | unset |  |
| `amiLookup` | `AmiLookup` | no | unset |  |
| `subnet` | string | no | unset | Name of a stack `subnet` resource. |
| `securityGroups` | list of string | no | `[]` |  |
| `keyName` | string | no | unset |  |
| `userData` | string | no | unset |  |
| `publicIp` | boolean | no | `false` |  |
| `tags` | map of string | no | `{}` |  |

`AmiLookup` object:

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `owner` | string | yes | - | Owner account id or alias, e.g. 099720109477 or amazon. |
| `namePattern` | string | yes | - |  |

Outputs: `arn`, `id`, `private_ip`, `public_ip`

### `vpc`

Terraform/OpenTofu type: `aws_vpc`.

| Property | Type | Required | Default | Description |
|---|---|---|---|---|
| `cidr` | string | yes | - |  |
| `enableDnsHostnames` | boolean | no | `true` |  |
| `enableDnsSupport` | boolean | no | `true` |  |
| `tags` | map of string | no | `{}` |  |

Outputs: `arn`, `cidr`, `id`


## Validation rules

- `vm` needs exactly one of `ami` / `amiLookup`.
- `Rule.toPort` must be >= `fromPort`. `toPort` defaults to `fromPort`.
- CIDR values must be valid CIDRs.

## Outputs

Outputs listed under each resource type are returned by `apply` and `outputs` as `{resource-name: {key: value}}`, for example `iacforge outputs` prints `{"web": {"id": "...", "name": "web"}}`.

## Example

See [`examples/aws/stack.yaml`](../../../examples/aws/stack.yaml):

```yaml
# AWS scaffold: VPC, subnet, SG, VM, bucket. Uses ambient AWS credentials/profile.
# bucket names are globally unique: change assets-example-bucket-1.
apiVersion: iacforge/v1
kind: Stack
metadata:
  name: aws-demo
spec:
  provider: aws
  providerConfig:
    region: us-east-1
    defaultTags:
      managed-by: iacforge
  resources:
  - name: vpc
    type: vpc
    properties:
      cidr: 10.20.0.0/16
  - name: pub-a
    type: subnet
    properties:
      vpc: vpc
      cidr: 10.20.1.0/24
      availabilityZone: us-east-1a
      public: true
  - name: web-sg
    type: security_group
    properties:
      vpc: vpc
      ingress:
      - protocol: tcp
        fromPort: 22
        cidrs:
        - 10.0.0.0/8
      - protocol: tcp
        fromPort: 80
        toPort: 80
  - name: web
    type: vm
    properties:
      subnet: pub-a
      securityGroups:
      - web-sg
      publicIp: true
      userData: '#!/bin/sh

        echo hi

        '
      amiLookup:
        owner: 099720109477
        namePattern: ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*
  - name: assets-example-bucket-1
    type: bucket
    properties:
      versioning: true
```
