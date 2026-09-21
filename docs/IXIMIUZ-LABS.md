# iximiuz Labs Packaging

# Container image

Build the image from the repository root:

```bash
docker build -t k8squest:latest .
```

The image contains the engine, mission content, Python dependencies, and
`kubectl`. A lab runtime should provide:

- `K8SQUEST_WEB=true`
- `K8SQUEST_LEVEL=level-1-pods` (or another level directory name)
- `K8SQUEST_NAMESPACE` for the per-session namespace
- `KUBECONFIG` or a Kubernetes context available to the container

## Published image

The current public Docker Hub image is:

```text
docker.io/mmengineer42/k8squest:latest
```

For a reproducible deployment, use the published digest:

```text
docker.io/mmengineer42/k8squest@sha256:5ff1107461484e25f19b28a843763ee140baa2abf07c706f29e6fbeac
```

Use `mmengineer42/k8squest:latest` as the image reference in iximiuz Labs,
or use the digest reference when the platform supports pinned images.

The image is a runtime artifact for an iximiuz Labs challenge submission;
publishing it still requires an iximiuz Labs creator account and the platform's
challenge metadata and registry configuration.