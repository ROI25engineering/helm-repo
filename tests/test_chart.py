"""Render real Helm manifests and verify deployment/security contracts offline."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "simple-service"
PROFILE = CHART / "examples" / "keycloak.values.yaml"


def render(overrides=None, profile=False):
    with tempfile.TemporaryDirectory() as directory:
        values = Path(directory) / "values.yaml"
        values.write_text(yaml.safe_dump(overrides or {}), encoding="utf-8")
        command = ["helm", "template", "test-release", str(CHART)]
        if profile:
            command.extend(["-f", str(PROFILE)])
        command.extend(["-f", str(values)])
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def resource(documents, kind):
    matches = [doc for doc in documents if doc["kind"] == kind]
    if len(matches) != 1:
        raise AssertionError(f"Expected one {kind}, got {len(matches)}")
    return matches[0]


class ChartTests(unittest.TestCase):
    def test_defaults_preserve_single_service_and_opt_in_features(self):
        docs = render()
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(container["ports"], [
            {"name": "http", "containerPort": 80, "protocol": "TCP"}])
        self.assertNotIn("startupProbe", container)
        self.assertNotIn("terminationGracePeriodSeconds", pod)
        self.assertFalse(any(doc["kind"] == "NetworkPolicy" for doc in docs))
        service = resource(docs, "Service")["spec"]
        self.assertEqual(service["ports"], [
            {"name": "http", "port": 80, "targetPort": "http", "protocol": "TCP"}])

    def test_existing_port_and_ingress_overrides_still_work(self):
        docs = render({"containerPort": 4000, "service": {"port": 4000},
                       "ingress": {"enabled": True}})
        container = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["ports"][0]["containerPort"], 4000)
        backend = resource(docs, "Ingress")["spec"]["rules"][0]["http"]["paths"][0]["backend"]
        self.assertEqual(backend["service"]["port"]["number"], 4000)

    def test_optional_ports_and_zero_grace_period(self):
        docs = render({"terminationGracePeriodSeconds": 0,
                       "extraContainerPorts": [{"name": "metrics", "containerPort": 9090}]})
        pod = resource(docs, "Deployment")["spec"]["template"]["spec"]
        self.assertEqual(pod["terminationGracePeriodSeconds"], 0)
        self.assertEqual(pod["containers"][0]["ports"][1]["containerPort"], 9090)
        self.assertEqual(len(resource(docs, "Service")["spec"]["ports"]), 1)

    def test_keycloak_probes_use_unexposed_management_port(self):
        docs = render(profile=True)
        deployment = resource(docs, "Deployment")
        pod = deployment["spec"]["template"]["spec"]
        container = pod["containers"][0]
        self.assertEqual(container["args"], ["start"])
        self.assertEqual(deployment["spec"]["strategy"], {"type": "Recreate"})
        self.assertEqual(pod["terminationGracePeriodSeconds"], 60)
        self.assertEqual(container["ports"][1]["containerPort"], 9000)
        for probe, path in [("startupProbe", "/health/started"),
                            ("readinessProbe", "/health/ready"),
                            ("livenessProbe", "/health/live")]:
            self.assertEqual(container[probe]["httpGet"], {"path": path, "port": "management"})
        service = resource(docs, "Service")["spec"]
        self.assertEqual(service["type"], "ClusterIP")
        self.assertEqual(len(service["ports"]), 1)
        self.assertEqual(service["ports"][0]["targetPort"], "http")
        self.assertFalse(any(doc["kind"] == "Ingress" for doc in docs))

    def test_keycloak_credentials_are_secret_references(self):
        docs = render(profile=True)
        container = resource(docs, "Deployment")["spec"]["template"]["spec"]["containers"][0]
        env = {entry["name"]: entry for entry in container["env"]}
        for name in ["KC_DB_URL", "KC_DB_USERNAME", "KC_DB_PASSWORD",
                     "KC_BOOTSTRAP_ADMIN_USERNAME", "KC_BOOTSTRAP_ADMIN_PASSWORD"]:
            self.assertNotIn("value", env[name])
            self.assertIn("secretKeyRef", env[name]["valueFrom"])
        self.assertFalse(resource(docs, "ServiceAccount")["automountServiceAccountToken"])
        self.assertTrue(container["securityContext"]["runAsNonRoot"])

    def test_keycloak_public_ingress_excludes_admin_and_management(self):
        docs = render({"ingress": {"enabled": True}}, profile=True)
        ingress = resource(docs, "Ingress")["spec"]
        paths = ingress["rules"][0]["http"]["paths"]
        self.assertEqual({p["path"] for p in paths}, {"/realms", "/resources", "/.well-known"})
        self.assertTrue(all(p["pathType"] == "Prefix" for p in paths))
        self.assertTrue(all(p["backend"]["service"]["port"]["number"] == 80 for p in paths))
        self.assertTrue(ingress["tls"][0]["secretName"])

    def test_keycloak_policy_allows_only_selected_proxy_on_application_port(self):
        docs = render(profile=True)
        policy = resource(docs, "NetworkPolicy")["spec"]
        labels = resource(docs, "Deployment")["spec"]["selector"]["matchLabels"]
        self.assertEqual(policy["podSelector"]["matchLabels"], labels)
        self.assertEqual(policy["policyTypes"], ["Ingress"])
        self.assertEqual(len(policy["ingress"]), 1)
        rule = policy["ingress"][0]
        self.assertEqual(rule["ports"], [{"protocol": "TCP", "port": 8080}])
        self.assertEqual(len(rule["from"]), 1)
        self.assertEqual(set(rule["from"][0]), {"namespaceSelector", "podSelector"})

    def test_empty_network_policy_denies_ingress(self):
        policy = resource(render({"networkPolicy": {"enabled": True}}), "NetworkPolicy")
        self.assertEqual(policy["spec"]["ingress"], [])

    def test_existing_cronjob_init_container_contract(self):
        job = {"enabled": True, "schedule": "*/5 * * * *",
               "image": {"repository": "example", "tag": "1"}}
        for init in [None, [{"name": "prepare", "image": "example:1"}]]:
            with self.subTest(init=init):
                configured = dict(job)
                if init:
                    configured["initContainers"] = init
                docs = render({"cronjobs": {"jobs": {"example": configured}}})
                pod = resource(docs, "CronJob")["spec"]["jobTemplate"]["spec"]["template"]["spec"]
                if init:
                    self.assertEqual(pod["initContainers"], init)
                else:
                    self.assertNotIn("initContainers", pod)


if __name__ == "__main__":
    unittest.main()
