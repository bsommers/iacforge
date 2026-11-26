"""gcp v0.2 resource types: Artifact Registry, Secret Manager, IAM, Cloud Run, Cloud SQL, GKE Autopilot."""

import copy
import importlib.util

import pytest

from iacforge.adapters.gcp import ADAPTER, EXAMPLES, GcpConfig
from iacforge.errors import SpecError, UnsupportedError
from iacforge.render import bind, render_terraform
from iacforge.spec import parse_spec

NEW_TYPES = {"artifact_registry", "secret", "iam_binding", "bucket_iam_binding", "secret_iam_binding",
             "registry_iam_binding", "cloud_run_service", "cloud_sql", "gke_autopilot"}


def stack(resources, cfg=None):
    return {"apiVersion": "iacforge/v1", "kind": "Stack", "metadata": {"name": "t"},
            "spec": {"provider": "gcp", "providerConfig": cfg or {"project": "p1"}, "resources": resources}}


def render(resources, cfg=None):
    return render_terraform(bind(parse_spec(stack(resources, cfg)), "opentofu"))


def bind_err(resources, cfg=None):
    with pytest.raises(SpecError) as e:
        bind(parse_spec(stack(resources, cfg)), "opentofu")
    return str(e.value) + str(e.value.details)


SA = {"name": "sa", "type": "service_account", "properties": {"accountId": "app-runner"}}
SEC = {"name": "key", "type": "secret", "properties": {}}
VPC = {"name": "vpc", "type": "network", "properties": {}}


def test_examples_cover_new_types():
    covered = {r["type"] for ex in EXAMPLES for r in ex["spec"]["resources"]}
    assert NEW_TYPES <= covered


def test_artifact_registry():
    out = render([{"name": "images", "type": "artifact_registry",
                   "properties": {"description": "d", "labels": {"a": "b"}}}], {"project": "p1", "labels": {"x": "y"}})
    r = out["resource"]["google_artifact_registry_repository"]["images"]
    assert r == {"repository_id": "images", "format": "DOCKER", "location": "us-central1", "description": "d",
                 "labels": {"x": "y", "a": "b"}}
    assert out["output"]["images__repository_url"]["value"].endswith(
        "-docker.pkg.dev/${google_artifact_registry_repository.images.project}"
        "/${google_artifact_registry_repository.images.repository_id}")
    assert {"images__id", "images__name"} <= set(out["output"])


def test_artifact_registry_python_format_url():
    out = render([{"name": "pk", "type": "artifact_registry", "properties": {"format": "PYTHON", "location": "europe-west1"}}])
    assert out["resource"]["google_artifact_registry_repository"]["pk"]["location"] == "europe-west1"
    assert "-python.pkg.dev/" in out["output"]["pk__repository_url"]["value"]


def test_secret_automatic_and_user_managed():
    out = render([SEC, {"name": "eu", "type": "secret", "properties": {"replication": ["europe-west1", "europe-west4"]}}])
    s = out["resource"]["google_secret_manager_secret"]
    assert s["key"] == {"secret_id": "key", "replication": {"auto": {}}}
    assert s["eu"]["replication"] == {"user_managed": {"replicas": [{"location": "europe-west1"},
                                                                    {"location": "europe-west4"}]}}
    assert {"key__id", "key__secret_id"} <= set(out["output"])


def test_secret_rejects_empty_regions_and_bad_name():
    bind_err([{"name": "k", "type": "secret", "properties": {"replication": []}}])
    bind_err([{"name": "bad.name", "type": "secret", "properties": {}}])


def test_iam_binding_project_literal_and_sa():
    out = render([SA, {"name": "b1", "type": "iam_binding", "properties": {"role": "roles/viewer", "member": "user:a@x.com"}},
                  {"name": "b2", "type": "iam_binding", "properties": {"role": "roles/logging.logWriter", "member": "sa"}}])
    m = out["resource"]["google_project_iam_member"]
    assert m["b1"] == {"project": "p1", "role": "roles/viewer", "member": "user:a@x.com"}
    assert m["b2"]["member"] == "serviceAccount:${google_service_account.sa.email}"
    assert m["b2"]["depends_on"] == ["google_service_account.sa"]
    assert "b1__id" in out["output"]


def test_scoped_iam_bindings():
    out = render([SA, SEC, {"name": "bk-example-1", "type": "bucket", "properties": {}},
                  {"name": "reg", "type": "artifact_registry", "properties": {}},
                  {"name": "i1", "type": "bucket_iam_binding",
                   "properties": {"role": "roles/storage.objectViewer", "member": "sa", "bucket": "bk-example-1"}},
                  {"name": "i2", "type": "secret_iam_binding",
                   "properties": {"role": "roles/secretmanager.secretAccessor", "member": "sa", "secret": "key"}},
                  {"name": "i3", "type": "registry_iam_binding",
                   "properties": {"role": "roles/artifactregistry.reader", "member": "group:g@x.com", "registry": "reg"}}])
    r = out["resource"]
    assert r["google_storage_bucket_iam_member"]["i1"]["bucket"] == "${google_storage_bucket.bk_example_1.name}"
    assert r["google_secret_manager_secret_iam_member"]["i2"]["secret_id"] == "${google_secret_manager_secret.key.secret_id}"
    i3 = r["google_artifact_registry_repository_iam_member"]["i3"]
    assert i3["repository"] == "${google_artifact_registry_repository.reg.repository_id}"
    assert i3["location"] == "${google_artifact_registry_repository.reg.location}"
    assert i3["member"] == "group:g@x.com"


def test_iam_role_validated():
    bind_err([{"name": "b", "type": "iam_binding", "properties": {"role": "owner", "member": "user:a@x.com"}}])


def test_cloud_run_defaults_are_safe():
    out = render([{"name": "web", "type": "cloud_run_service", "properties": {"image": "gcr.io/p/i:1"}}])
    svc = out["resource"]["google_cloud_run_v2_service"]["web"]
    assert svc["ingress"] == "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
    assert "google_cloud_run_v2_service_iam_member" not in out["resource"]
    c = svc["template"]["containers"][0]
    assert c["image"] == "gcr.io/p/i:1" and c["ports"] == {"container_port": 8080}
    assert c["resources"]["limits"] == {"cpu": "1", "memory": "512Mi"}
    assert svc["template"]["scaling"] == {"min_instance_count": 0, "max_instance_count": 10}
    assert "env" not in c and "service_account" not in svc["template"]
    assert {"web__id", "web__uri"} <= set(out["output"])


def test_cloud_run_secret_env_and_options():
    out = render([SA, SEC, {"name": "web", "type": "cloud_run_service", "properties": {
        "image": "i", "env": {"A": "1"}, "secretEnv": {"API_KEY": "key"}, "serviceAccount": "sa",
        "vpcConnector": "projects/p1/locations/us-central1/connectors/c", "minInstances": 1, "maxInstances": 2,
        "cpu": "2", "memory": "1Gi", "port": 9000}}])
    svc = out["resource"]["google_cloud_run_v2_service"]["web"]
    env = svc["template"]["containers"][0]["env"]
    assert env[0] == {"name": "A", "value": "1"}
    assert env[1] == {"name": "API_KEY", "value_source": {"secret_key_ref": {
        "secret": "${google_secret_manager_secret.key.secret_id}", "version": "latest"}}}
    assert "value" not in env[1]
    assert svc["template"]["service_account"] == "${google_service_account.sa.email}"
    assert svc["template"]["vpc_access"] == {"connector": "projects/p1/locations/us-central1/connectors/c"}
    assert svc["depends_on"] == ["google_secret_manager_secret.key", "google_service_account.sa"]


def test_cloud_run_allow_unauthenticated_emits_invoker():
    out = render([{"name": "web", "type": "cloud_run_service",
                   "properties": {"image": "i", "allowUnauthenticated": True}}])
    inv = out["resource"]["google_cloud_run_v2_service_iam_member"]["web_invoker"]
    assert inv["member"] == "allUsers" and inv["role"] == "roles/run.invoker"
    assert inv["name"] == "${google_cloud_run_v2_service.web.name}"


def test_cloud_run_validation():
    bind_err([{"name": "web", "type": "cloud_run_service", "properties": {"image": "i", "minInstances": 5, "maxInstances": 2}}])
    bind_err([SEC, {"name": "web", "type": "cloud_run_service",
                    "properties": {"image": "i", "env": {"A": "1"}, "secretEnv": {"A": "key"}}}])
    bind_err([{"name": "web", "type": "cloud_run_service", "properties": {"image": "i", "ingress": "everywhere"}}])


def test_cloud_sql_defaults_are_safe():
    out = render([{"name": "db", "type": "cloud_sql", "properties": {}}])
    db = out["resource"]["google_sql_database_instance"]["db"]
    assert db["deletion_protection"] is True
    assert db["settings"]["deletion_protection_enabled"] is True
    assert db["database_version"] == "POSTGRES_16" and db["settings"]["tier"] == "db-f1-micro"
    assert db["settings"]["backup_configuration"] == {"enabled": True, "point_in_time_recovery_enabled": True}
    assert db["settings"]["ip_configuration"] == {"ipv4_enabled": True}
    assert "google_sql_user" not in out["resource"] and "data" not in out
    assert {"db__id", "db__connection_name", "db__private_ip"} <= set(out["output"])


def test_cloud_sql_private_databases_and_password_secret():
    out = render([VPC, SEC, {"name": "db", "type": "cloud_sql", "properties": {
        "engine": "MYSQL_8_0", "network": "vpc", "availability": "REGIONAL", "databases": ["app", "ops"],
        "passwordSecret": "key", "deletionProtection": False, "diskGb": 50, "tier": "db-custom-2-7680"}}])
    db = out["resource"]["google_sql_database_instance"]["db"]
    ipc = db["settings"]["ip_configuration"]
    assert ipc == {"ipv4_enabled": False, "private_network": "${google_compute_network.vpc.self_link}"}
    assert db["deletion_protection"] is False and db["settings"]["availability_type"] == "REGIONAL"
    assert "point_in_time_recovery_enabled" not in db["settings"]["backup_configuration"]
    assert set(out["resource"]["google_sql_database"]) == {"db_db_app", "db_db_ops"}
    assert out["data"]["google_secret_manager_secret_version_access"]["db_pw"]["secret"] == \
        "${google_secret_manager_secret.key.secret_id}"
    user = out["resource"]["google_sql_user"]["db_user"]
    assert user["password"] == "${data.google_secret_manager_secret_version_access.db_pw.secret_data}"
    assert user["name"] == "app"
    assert sorted(db["depends_on"]) == ["google_compute_network.vpc", "google_secret_manager_secret.key"]


def test_cloud_sql_validation():
    bind_err([{"name": "db", "type": "cloud_sql", "properties": {"engine": "ORACLE_19"}}])
    bind_err([{"name": "db", "type": "cloud_sql", "properties": {"databases": ["a", "a"]}}])
    bind_err([{"name": "db", "type": "cloud_sql", "properties": {"diskGb": 1}}])


def test_gke_autopilot_defaults_are_safe():
    out = render([{"name": "gke", "type": "gke_autopilot", "properties": {}}])
    c = out["resource"]["google_container_cluster"]["gke"]
    assert c["enable_autopilot"] is True and c["deletion_protection"] is True
    assert c["private_cluster_config"] == {"enable_private_nodes": True}
    assert c["release_channel"] == {"channel": "REGULAR"} and c["location"] == "us-central1"
    assert "network" not in c
    assert {"gke__id", "gke__endpoint", "gke__name"} <= set(out["output"])


def test_gke_autopilot_network_and_overrides():
    out = render([VPC, {"name": "sn", "type": "subnet", "properties": {"network": "vpc", "cidr": "10.0.0.0/20"}},
                  {"name": "gke", "type": "gke_autopilot", "properties": {
                      "network": "vpc", "subnet": "sn", "masterCidr": "172.16.0.0/28", "releaseChannel": "STABLE",
                      "deletionProtection": False}}])
    c = out["resource"]["google_container_cluster"]["gke"]
    assert c["network"] == "${google_compute_network.vpc.self_link}"
    assert c["subnetwork"] == "${google_compute_subnetwork.sn.self_link}"
    assert c["private_cluster_config"] == {"enable_private_nodes": True, "master_ipv4_cidr_block": "172.16.0.0/28"}
    assert c["deletion_protection"] is False
    pub = render([{"name": "g2", "type": "gke_autopilot", "properties": {"privateNodes": False}}])
    assert "private_cluster_config" not in pub["resource"]["google_container_cluster"]["g2"]


def test_gke_validation():
    bind_err([{"name": "g", "type": "gke_autopilot", "properties": {"masterCidr": "172.16.0.0/28", "privateNodes": False}}])
    bind_err([{"name": "g", "type": "gke_autopilot", "properties": {"masterCidr": "nope"}}])
    bind_err([VPC, {"name": "sn", "type": "subnet", "properties": {"network": "vpc", "cidr": "10.0.0.0/20"}},
              {"name": "g", "type": "gke_autopilot", "properties": {"subnet": "sn"}}])


# ---- wrong-type references ----
@pytest.mark.parametrize("res,msg", [
    ({"name": "web", "type": "cloud_run_service", "properties": {"image": "i", "secretEnv": {"K": "sa"}}}, "expected secret"),
    ({"name": "web", "type": "cloud_run_service", "properties": {"image": "i", "serviceAccount": "key"}},
     "expected service_account"),
    ({"name": "db", "type": "cloud_sql", "properties": {"passwordSecret": "sa"}}, "expected secret"),
    ({"name": "db", "type": "cloud_sql", "properties": {"network": "key"}}, "expected network"),
    ({"name": "g", "type": "gke_autopilot", "properties": {"network": "key"}}, "expected network"),
    ({"name": "b", "type": "iam_binding", "properties": {"role": "roles/viewer", "member": "key"}},
     "expected service_account"),
    ({"name": "b", "type": "bucket_iam_binding", "properties": {"role": "roles/viewer", "member": "sa", "bucket": "key"}},
     "expected bucket"),
    ({"name": "b", "type": "secret_iam_binding", "properties": {"role": "roles/viewer", "member": "sa", "secret": "sa"}},
     "expected secret"),
    ({"name": "b", "type": "registry_iam_binding",
      "properties": {"role": "roles/viewer", "member": "sa", "registry": "key"}}, "expected artifact_registry"),
])
def test_wrong_type_references_rejected(res, msg):
    assert msg in bind_err([SA, SEC, VPC, res])


def test_unknown_reference_rejected():
    assert "unknown" in bind_err([{"name": "db", "type": "cloud_sql", "properties": {"passwordSecret": "ghost"}}])


def test_references_lists_dependencies():
    b = bind(parse_spec(stack([SA, SEC, VPC, {"name": "web", "type": "cloud_run_service", "properties": {
        "image": "i", "secretEnv": {"K": "key"}, "serviceAccount": "sa"}}])), "opentofu")
    web = next(r for r in b.stack.spec.resources if r.name == "web")
    assert sorted(ADAPTER.references(web, b.props["web"])) == ["key", "sa"]


# ---- no credentials / values in any model ----
def test_no_model_accepts_password_or_value():
    for t, model in ADAPTER.resource_models.items():
        fields = set(model.model_fields) | {f.alias for f in model.model_fields.values() if f.alias}
        assert not fields & {"password", "value", "secret_value", "secretValue", "secretData", "secret_data"}, t
    for ptype, props in (("secret", {"value": "hunter2"}), ("secret", {"secretData": "x"}),
                         ("cloud_sql", {"password": "hunter2"}), ("cloud_sql", {"rootPassword": "x"})):
        bind_err([{"name": "x", "type": ptype, "properties": props}])


def _walk(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_example_has_no_secret_material():
    out = render_terraform(bind(parse_spec(EXAMPLES[1]), "opentofu"))
    pws = [v for k, v in _walk(out) if k == "password"]
    assert pws and all(v.startswith("${data.google_secret_manager_secret_version_access.") for v in pws)


# ---- enableApis ----
def test_enable_apis_off_by_default():
    out = render([SEC])
    assert "google_project_service" not in out["resource"]


def test_enable_apis_emits_services_and_depends_on():
    out = render([SEC, {"name": "web", "type": "cloud_run_service", "properties": {"image": "i"}},
                  {"name": "db", "type": "cloud_sql", "properties": {}},
                  {"name": "gke", "type": "gke_autopilot", "properties": {}},
                  {"name": "reg", "type": "artifact_registry", "properties": {}}],
                 {"project": "p1", "enableApis": True})
    svc = out["resource"]["google_project_service"]
    assert svc["key_api"] == {"service": "secretmanager.googleapis.com", "disable_on_destroy": False}
    assert svc["web_api"]["service"] == "run.googleapis.com"
    assert svc["db_api"]["service"] == "sqladmin.googleapis.com"
    assert svc["gke_api"]["service"] == "container.googleapis.com"
    assert svc["reg_api"]["service"] == "artifactregistry.googleapis.com"
    assert out["resource"]["google_secret_manager_secret"]["key"]["depends_on"] == ["google_project_service.key_api"]
    # resources that also have stack dependencies keep an implicit edge through `project`
    web = render([SEC, {"name": "web", "type": "cloud_run_service",
                        "properties": {"image": "i", "secretEnv": {"K": "key"}}}],
                 {"project": "p1", "enableApis": True})["resource"]["google_cloud_run_v2_service"]["web"]
    assert web["project"] == "${google_project_service.web_api.project}"


def test_enable_apis_covers_existing_types():
    out = render([VPC, {"name": "bk-example-1", "type": "bucket", "properties": {}}], {"project": "p1", "enableApis": True})
    svc = out["resource"]["google_project_service"]
    assert svc["vpc_api"]["service"] == "compute.googleapis.com"
    assert svc["bk_example_1_api"]["service"] == "storage.googleapis.com"


def test_enable_apis_config_default_false():
    assert GcpConfig(project="p").enable_apis is False
    assert GcpConfig.model_validate({"project": "p", "enableApis": True}).enable_apis is True


# ---- import ids ----
def _id(rtype, props=None, name=None, cfg=None, extra=None):
    name = name or ("res-bucket-1" if rtype == "bucket" else "r1")
    d = stack([*(extra or []), {"name": name, "type": rtype, "properties": props or {}}], cfg)
    b = bind(parse_spec(d), "opentofu")
    r = next(x for x in b.stack.spec.resources if x.name == name)
    return ADAPTER.import_id(r, b.props[name], b.config)


@pytest.mark.parametrize("rtype,props,extra,want", [
    ("network", {}, None, "projects/p1/global/networks/r1"),
    ("subnet", {"network": "vpc", "cidr": "10.0.0.0/24"}, [VPC], "projects/p1/regions/us-central1/subnetworks/r1"),
    ("subnet", {"network": "vpc", "cidr": "10.0.0.0/24", "region": "europe-west1"}, [VPC],
     "projects/p1/regions/europe-west1/subnetworks/r1"),
    ("firewall", {"network": "vpc", "allow": [{"protocol": "tcp"}], "sourceRanges": ["10.0.0.0/8"]}, [VPC],
     "projects/p1/global/firewalls/r1"),
    ("vm", {"network": "vpc", "zone": "us-east1-b"}, [VPC], "projects/p1/zones/us-east1-b/instances/r1"),
    ("vm", {"network": "vpc"}, [VPC], "projects/p1/zones/us-central1-a/instances/r1"),
    ("bucket", {"bucketName": "real-name"}, None, "p1/real-name"),
    ("bucket", {}, None, "p1/res-bucket-1"),
    ("service_account", {"accountId": "app-runner"}, None, "projects/p1/serviceAccounts/app-runner@p1.iam.gserviceaccount.com"),
    ("artifact_registry", {}, None, "projects/p1/locations/us-central1/repositories/r1"),
    ("artifact_registry", {"repositoryId": "imgs", "location": "europe-west1"}, None,
     "projects/p1/locations/europe-west1/repositories/imgs"),
    ("secret", {}, None, "projects/p1/secrets/r1"),
    ("cloud_run_service", {"image": "i"}, None, "projects/p1/locations/us-central1/services/r1"),
    ("cloud_sql", {}, None, "projects/p1/instances/r1"),
    ("gke_autopilot", {}, None, "projects/p1/locations/us-central1/clusters/r1"),
    ("iam_binding", {"role": "roles/viewer", "member": "user:a@x.com"}, None, "p1 roles/viewer user:a@x.com"),
])
def test_import_id(rtype, props, extra, want):
    assert _id(rtype, props, extra=extra) == want


def test_import_id_uses_config_project_and_region():
    assert _id("cloud_sql", cfg={"project": "other"}) == "projects/other/instances/r1"
    assert _id("gke_autopilot", cfg={"project": "p2", "region": "asia-east1"}) == \
        "projects/p2/locations/asia-east1/clusters/r1"


def test_import_id_unsupported_when_it_needs_another_resources_name():
    with pytest.raises(UnsupportedError):
        _id("iam_binding", {"role": "roles/viewer", "member": "sa"}, extra=[SA])
    with pytest.raises(UnsupportedError):
        _id("secret_iam_binding", {"role": "roles/viewer", "member": "user:a@x.com", "secret": "key"}, extra=[SEC])


def test_every_type_has_import_or_explicit_unsupported():
    covered = {"network", "subnet", "firewall", "vm", "bucket", "service_account", "artifact_registry", "secret",
               "cloud_run_service", "cloud_sql", "gke_autopilot", "iam_binding"}
    assert covered | {"bucket_iam_binding", "secret_iam_binding", "registry_iam_binding"} == set(ADAPTER.resource_models)


# ---- pulumi ----
@pytest.mark.skipif(not importlib.util.find_spec("pulumi_gcp"), reason="pulumi_gcp not installed")
@pytest.mark.parametrize("idx", range(len(EXAMPLES)))
def test_pulumi_mocks_all_examples(idx):
    import pulumi

    created = []

    class M(pulumi.runtime.Mocks):
        def new_resource(self, args):
            created.append(args.typ)
            return [args.name + "_id", {**args.inputs, "secretId": "s", "project": "p1", "selfLink": "sl", "email": "e@x"}]

        def call(self, args):
            return {"secretData": "x"} if "getSecretVersionAccess" in args.token else {}

    pulumi.runtime.set_mocks(M(), project="p", stack="s", preview=False)
    from iacforge.render import run_pulumi_program

    @pulumi.runtime.test
    def program():
        run_pulumi_program(bind(parse_spec(copy.deepcopy(EXAMPLES[idx])), "pulumi"))

    program()
    if idx == 1:
        for t in ("gcp:cloudrunv2/service:Service", "gcp:cloudrunv2/serviceIamMember:ServiceIamMember",
                  "gcp:sql/databaseInstance:DatabaseInstance", "gcp:sql/user:User", "gcp:sql/database:Database",
                  "gcp:container/cluster:Cluster", "gcp:secretmanager/secret:Secret",
                  "gcp:artifactregistry/repository:Repository", "gcp:projects/iAMMember:IAMMember",
                  "gcp:projects/service:Service", "gcp:storage/bucketIAMMember:BucketIAMMember",
                  "gcp:secretmanager/secretIamMember:SecretIamMember",
                  "gcp:artifactregistry/repositoryIamMember:RepositoryIamMember"):
            assert t in created, t
