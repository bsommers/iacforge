# Contracts

Three contracts hold iacforge together: the **ProviderAdapter** (pure translation), the **Engine**
(side effects) and the **Runner** (process execution seam). Source of truth:
`src/iacforge/adapters/base.py`, `src/iacforge/engines/base.py`. Changing a contract needs an ADR
(see [ADR 0003](../adr/0003-plugin-contract.md)).

## ProviderAdapter

Subclass `iacforge.adapters.base.ProviderAdapter`, export a module-level `ADAPTER = MyAdapter()` and
an `EXAMPLES` list, and register the module in `ADAPTER_MODULES` (`adapters/__init__.py`).

### Class attributes

| Attribute | Type | Default | Meaning |
|---|---|---|---|
| `name` | `ClassVar[str]` | required | Provider id used in `spec.provider`; must equal its registry key (checked by `get_adapter`). |
| `description` | `ClassVar[str]` | required | One line shown by `iacforge providers`. |
| `status` | `str` | `"stable"` | `stable`, `beta` or `scaffold` (enforced by the contract suite). |
| `category` | `str` | `"local"` | `local` or `cloud`. |
| `platforms` | `frozenset[str]` | `ALL_PLATFORMS` | Host OSes it can provision from/on: `linux`, `darwin`, `windows`. A mismatch yields a warning, not an error. |
| `engines` | `frozenset[str]` | `{TF, PULUMI}` | Engine families supported: `"terraform"` (covers `opentofu` and `terraform`) and/or `"pulumi"`. `bind()` raises `UnsupportedError` for others. |
| `required_tools` | `tuple[str, ...]` | `()` | Host binaries needed at apply time; used by `iacforge doctor` (`doctor` checks the tools in `core.HOST_TOOLS` and falls back to `shutil.which` for others). |
| `pulumi_packages` | `tuple[str, ...]` | `()` | pip packages the Pulumi engine needs; written into the ejected `requirements.txt`. |
| `config_model` | `type[Props]` | `EmptyConfig` | Pydantic model for `spec.providerConfig`. |
| `resource_models` | `dict[str, type[Props]]` | `{}` | Resource `type` -> property model. Keys are the supported resource types. |
| `tf_types` | `dict[str, str]` | `{}` | Resource `type` -> Terraform resource type. Must cover every key of `resource_models` when `TF` is in `engines`. |
| `tf_required_providers` | `dict[str, dict[str, str]]` | `{}` | Becomes `terraform.required_providers`; must be non-empty for TF adapters. Pin with `~>`. |
| `docs_url` | `str` | `""` | Link shown in `describe()`. |

`Props` is the base model for config and property models: `extra="forbid"` (typos are errors) and
`populate_by_name=True` (use `Field(alias="camelCase")` for spec keys, snake_case in Python).

### Methods

| Method | Required | Purpose |
|---|---|---|
| `references(res, props) -> list[str]` | no (default `[]`) | Stack resource names mentioned in `props` (e.g. `network: vpc`). `bind()` merges them into `depends_on` and errors on unknown names. |
| `validate_stack(stack, config, props) -> list[str]` | no (default `[]`) | Cross-resource checks beyond pydantic; return error strings (reported under path `spec`). |
| `tf_provider_blocks(config) -> dict` | no (default `{}`) | The Terraform `provider` block(s), e.g. `{"google": {"project": ...}}`. |
| `tf_resource(res, props, ctx: TfContext) -> TfResult` | required if `TF` in `engines` | Render one stack resource. Default raises `NotImplementedError`. |
| `pulumi_provider(config, stack)` | no (default `None`) | Explicit Pulumi provider instance, or `None` for ambient config. Called once per program run. |
| `pulumi_resource(res, props, ctx: PulumiContext) -> PulumiResult` | required if `PULUMI` in `engines` | Create one Pulumi resource. |
| `describe()` (classmethod) | no | Capability dict used by `iacforge providers`. Do not override casually. |
| `json_schema()` (classmethod) | no | `{provider, providerConfig, resources: {type: schema}}`, used by `iacforge schema <provider>`. |

### Result and context types

```python
@dataclass
class TfResult:
    body: dict[str, Any]                                  # primary resource block attributes
    extra: dict[str, dict[str, dict[str, Any]]] = {}      # {tf_type: {block_name: body}} helper resources
    data: dict[str, dict[str, dict[str, Any]]] = {}       # {data_type: {block_name: body}}
    outputs: dict[str, str] = {}                          # {key: "${expr}"}

@dataclass
class TfContext:
    stack: StackSpec; config: BaseModel; adapter: ProviderAdapter
    def address(self, resource_name) -> str               # "docker_network.net"
    def ref(self, resource_name, attr) -> str             # "${docker_network.net.id}"

@dataclass
class PulumiResult:
    resource: Any                                         # the pulumi.Resource
    outputs: dict[str, Any] = {}                          # key -> Output / value

@dataclass
class PulumiContext:
    stack: StackSpec; config: BaseModel
    provider: Any = None                                  # from pulumi_provider()
    resources: dict[str, Any] = {}                        # stack name -> pulumi.Resource
    def get(self, resource_name) -> Any                   # already-created dependency
```

How `render_terraform` uses a `TfResult`: `body` is stored at
`resource.<tf_types[type]>.<tf_id(name)>`; `depends_on` (sorted addresses of the resolved
dependencies) is added to the body for you; each `extra` and `data` entry is merged under its type;
each `outputs` entry becomes `output.<tf_id(name)>__<key>.value`.

In Pulumi, create resources with `render.pulumi_opts(ctx, res)` so the explicit provider and
`depends_on` are wired. Dependencies are guaranteed to exist in `ctx.resources` because the
program creates resources in topological order. Import Pulumi SDK packages **inside** the method;
they are optional dependencies.

### `references()` versus `dependsOn`

- `dependsOn` is an explicit list written by the user in the spec, checked in `spec.py` (unknown
  names, self-reference, cycles).
- `references()` is what the adapter reports from the *properties* (a subnet's `network:` field).
  `bind()` appends those to `depends_on` (deduplicated, user order first), so the engine sees one
  merged list. Unknown references become `references unknown resource(s)` errors.
- You must still render the actual data dependency yourself (`ctx.ref(props.network, "self_link")`
  in Terraform, `ctx.get(props.network).self_link` in Pulumi); `references()` only guarantees
  ordering and existence. Use `validate_stack()` to check the referenced resource has the right
  *type* (see `gcp.py`).

### Naming rules adapters must follow

- Primary address: `<tf_types[type]>.<tf_id(name)>`. Never rename it.
- Extra blocks: `<tf_id(name)>_<suffix>` so they cannot collide with another stack resource.
- Outputs: use the plain key (`"ip"`); core prefixes `<tf_id(name)>__`. For Pulumi, `run_pulumi_program`
  exports with `output_key(name, key)`.
- Pulumi logical name: the stack resource name.

### `EXAMPLES` requirement

Each adapter module must export `EXAMPLES: list[dict]` of minimal valid stack documents which
**together use every resource type** in `resource_models`. The shared suite
(`tests/test_adapter_contract.py`) uses them to check, for every adapter:

1. registered, described, schema serialisable (`test_registered_and_described`);
2. every resource type has a Terraform type and `tf_required_providers` is set (`test_every_type_has_tf_type`);
3. examples cover all types (`test_examples_cover_all_types`);
4. rendering twice is byte-identical (`test_examples_render_deterministically`);
5. an unknown property is rejected (`test_unknown_property_rejected`);
6. the real `tofu`/`terraform` accepts the output: `init -backend=false` + `validate` (`test_examples_pass_tofu_validate`, marker `tofu`).

Examples are also the documentation corpus; keep them minimal and credential-free.

## Engine

`iacforge.engines.base.Engine`. Constructed as `Engine(runner=None, which=None)`; `runner`
defaults to `subprocess_runner`, `which` to `shutil.which`. Obtain one with
`engines.get_engine(name, runner=None, which=None)` (`opentofu`/`terraform` -> `TerraformEngine`,
`pulumi` -> `PulumiEngine`; otherwise `SpecError`).

| Member | Contract |
|---|---|
| `name` | `"opentofu"`, `"terraform"` or `"pulumi"`. |
| `tool_status()` | `{"available": bool, "binary": path or None, "version": str or None}` (Pulumi adds `"sdk"`). |
| `render(b, workdir)` | Write engine-native files; return `{"files": [relative paths]}`. Makes the workdir. No process is run. |
| `plan(b, workdir)` | Return `{"changes": {"add","change","destroy"}, "resources": [...], "has_changes": bool, "log": str}`. Must not modify infrastructure. |
| `apply(b, workdir)` | Return `{"changes": {...}, "outputs": {resource: {key: value}}, "log": str}`. |
| `destroy(b, workdir)` | Return `{"changes": {...}, "log": str}`. |
| `outputs(b, workdir)` | Return `{"outputs": {resource: {key: value}}}`. |

Rules: return JSON-serialisable dicts; raise `ToolMissingError` (binary absent) and `EngineError`
(tool ran and failed) only; never decide gating (core does); never branch on provider name.
`core` wraps the result as `{stack, provider, engine, resources, workdir, warnings?, **engine result}`.

## Runner

```python
class Runner(Protocol):
    def __call__(self, args: list[str], cwd: Path, env: dict[str, str] | None = None,
                 timeout: float | None = None) -> ProcResult: ...

@dataclass
class ProcResult:
    returncode: int; stdout: str; stderr: str
```

`subprocess_runner` merges `env` over `os.environ`, runs `subprocess.run(args, cwd=..., capture_output=True,
text=True, check=False, timeout=...)`: list arguments, **no shell**. Engines treat any raised
exception (timeout, `OSError`) as `EngineError`. Tests pass a fake runner through `core.*(…, runner=…)`
or `get_engine(..., runner=…)`; see [testing](testing.md).

## Result envelopes

`TfResult.outputs` expressions and Pulumi outputs are flattened to `<resource>__<key>`; engines
nest them back with `render.nest_outputs` and translate `tf_id` names back to the original stack
resource names before returning to the caller.
