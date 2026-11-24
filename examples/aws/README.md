# aws example

Scaffold: VPC, subnet, security group, VM and bucket. Uses your ambient AWS credentials; change the globally unique bucket name. Creates billable resources.

```sh
iacforge validate stack.yaml
iacforge plan stack.yaml
iacforge apply stack.yaml --yes
iacforge outputs stack.yaml
iacforge destroy stack.yaml --yes
```

Reference: [docs/user-guide/providers/aws.md](../../docs/user-guide/providers/aws.md)
