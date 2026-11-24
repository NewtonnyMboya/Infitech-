import unittest
from cloud import CloudService, SecretReference, render_manifests, manifest_document

class CloudTests(unittest.TestCase):
    def service(self, **kwargs):
        defaults = {"name": "infilink-api", "image": "registry.example/infilink@sha256:" + "a" * 64}
        defaults.update(kwargs)
        return CloudService(**defaults)

    def test_renders_hardened_deployment_and_internal_service(self):
        manifests = render_manifests(self.service(environment={
            "MODE": "production", "API_TOKEN": SecretReference("api-secrets", "token")}))
        deployment, service = manifests
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertFalse(deployment["spec"]["template"]["spec"]["automountServiceAccountToken"])
        self.assertEqual(container["env"][0]["name"], "API_TOKEN")
        self.assertIn("secretKeyRef", container["env"][0]["valueFrom"])
        self.assertEqual(service["spec"]["type"], "ClusterIP")

    def test_rejects_mutable_image_tags(self):
        with self.assertRaises(ValueError):
            self.service(image="registry.example/infilink:latest")

    def test_rejects_invalid_replicas_and_port(self):
        with self.assertRaises(ValueError):
            self.service(replicas=11)
        with self.assertRaises(ValueError):
            self.service(container_port=70000)

    def test_rejects_invalid_environment_name_and_secret(self):
        with self.assertRaises(ValueError):
            self.service(environment={"BAD-NAME": "value"})
        with self.assertRaises(ValueError):
            SecretReference("../secret", "token")

    def test_bundle_is_json_serializable(self):
        import json
        self.assertEqual(json.loads(json.dumps(manifest_document(self.service())))["kind"],
                         "DeploymentBundle")

if __name__ == "__main__":
    unittest.main()
