# Helm charts

`simple-service` is the shared application chart. Version 0.1.18 adds opt-in
startup probes, additional pod ports, a termination grace period and ingress
NetworkPolicy support, with a Keycloak deployment example. Existing Service and
Ingress ports are unchanged. `containerPort` now defaults to 80 so the default
Deployment has a valid port; existing explicit port overrides take precedence.

## Keycloak preparation

Render the example before supplying environment-specific overrides:

```sh
helm template keycloak ./simple-service -f simple-service/examples/keycloak.values.yaml
```

This prepares chart support only. It does not deploy Keycloak, provision its
database, connect Weavers accounts, configure OAuth clients or publish plugins.
The example uses one replica, local caching and Recreate upgrades: it accepts
downtime and is not an HA configuration. Do not increase replicas or enable HPA
until distributed caching, cluster network access and upgrade behavior are designed.

Before deploying through the infrastructure workflow:

1. Review/pin the Keycloak release and scan its image. The example uses the standard
   `quay.io/keycloak/keycloak:26.8.1` image with production `start`, not `start-dev`.
   It performs build configuration during startup. Prefer a separately built,
   immutable optimized image for the final release; bake PostgreSQL, health and
   metrics options into that image before changing args to `start --optimized`.
2. Provision a dedicated PostgreSQL database/user and backups. Provide the existing
   Secret `keycloak-database` with `jdbc-url`, `username`, `password` keys. Configure
   verified database TLS according to the actual database endpoint and mount its
   trust material as needed; the chart does not infer TLS from secret contents.
   Keycloak manages its vendor schema on startup; validate upgrades against a
   restored copy and back up before upgrading. Image rollback alone cannot undo
   a database migration. Weavers-owned schema changes remain in
   `Weavers/apps/shared/migrations`; this chart adds no application schema.
3. Provide `keycloak-bootstrap` with `username` and `password` keys through the
   secrets manager. Establish permanent administrative access and remove the
   bootstrap environment references/temporary account after initial setup.
   Never commit actual credentials or use `--set` for secrets.
4. Set the real `KC_HOSTNAME`, matching ingress host, TLS Secret and ingress class.
   Enable ingress only after TLS is ready. The example assumes edge TLS termination
   and a trusted proxy that overwrites incoming `X-Forwarded-*` headers. Configure
   trusted proxy addresses for the selected version/environment as appropriate.
5. Replace the example NetworkPolicy selectors with the actual ingress controller's
   namespace and pod labels. The CNI must enforce policies. This policy permits
   ingress only on 8080 from that controller; it does not constrain egress. Check
   existing additive policies for broader grants. Add explicit permitted peers for
   internal callers or metrics scraping when needed; do not broadly open port 9000.
6. Keep the public ingress restricted to `/realms`, `/resources`, `/.well-known`.
   Keycloak's admin console/API is on the application port under `/admin`, not on
   management port 9000. Do not add a public `/` catch-all. Use a separately secured
   private admin route or authorized port-forwarding; an admin hostname alone is
   not an access control. Check other ingress resources do not expose these paths.
7. Verify startup/readiness/liveness, login discovery, admin-path denial and actual
   network isolation in the cluster. Health/metrics on 9000 are pod-only, with no
   Service/Ingress exposure. Kubernetes HTTP probes avoid needing curl in the image.
   Tune the 10-minute startup allowance and resource budget using measured startup
   and load. Configure alerts, DB recovery and operator ownership before user traffic.

No secrets or database are created by the profile, and ingress starts disabled.
Existing `extraEnv`, `envFrom`, volume and affinity options remain available.
The external OAuth/MCP integration and preservation of Weavers account identities
are separate application work; a running Keycloak server does not establish that
ChatGPT or Claude account linking works.

## New generic values

| Value | Default | Behavior |
| --- | --- | --- |
| `containerPort` | `80` | Existing primary named `http` port |
| `extraContainerPorts` | `[]` | Additional Kubernetes container ports; does not create Service ports; use unique names other than `http` |
| `startupProbe` | `{}` | Optional Kubernetes startup probe; protects slow starts from liveness restarts |
| `terminationGracePeriodSeconds` | `null` | Omitted by default; explicit values, including zero, are rendered |
| `networkPolicy.enabled` | `false` | Creates ingress-only isolation for this release's pods |
| `networkPolicy.ingress` | `[]` | Kubernetes ingress rules; empty means no allowed ingress under this policy |

## Verification

Requires Helm 3 and Python with the pinned test dependency:

```sh
python -m pip install -r tests/requirements.txt
helm lint simple-service --strict
helm lint simple-service --strict -f simple-service/examples/keycloak.values.yaml
python -m unittest discover -s tests -v
```

The validation workflow runs these commands on PRs and main. Tests render actual
Helm output and cover default/existing overrides, probe ports, secret references,
public route restrictions, NetworkPolicy selectors and the existing CronJob init
container behavior. The original Helm unittest suite also remains available at
`simple-service/tests` for environments with the plugin installed. These checks
do not substitute for a live Keycloak/PostgreSQL integration or cluster network test.
No chart archives/indexes are regenerated by this change; release packaging is a
separate step. The pre-existing publish workflow's root chart path/version handling
must be checked before publishing this repository's nested chart.

Official references:

- [Keycloak containers](https://www.keycloak.org/server/containers)
- [Health checks](https://www.keycloak.org/observability/health)
- [Reverse proxy and exposed paths](https://www.keycloak.org/server/reverseproxy)
