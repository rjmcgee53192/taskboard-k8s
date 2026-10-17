# Taskboard

A tiny task-list web app, packaged for Kubernetes. This is a learning
project: the app itself is deliberately simple (Flask + a single HTML page)
so the focus stays on the container and Kubernetes pieces around it.

What the app does:

- `GET /` serves a small page where you can add, check off, and delete tasks
- `GET/POST /api/tasks`, `PATCH/DELETE /api/tasks/<id>` is the JSON API
- `GET /healthz` and `GET /readyz` are the health endpoints the Kubernetes
  probes hit
- `GET /metrics` exposes a few Prometheus metrics (request count, task
  count, uptime)

Tasks are stored in process memory. Restart the container and they are
gone. That is fine for this project; persistence is on the to-learn list.

## Layout

```
.
├── app/
│   ├── app.py              # Flask app: API, health endpoints, /metrics, JSON logging
│   ├── requirements.txt    # Flask, gunicorn, pytest (pinned)
│   └── static/index.html   # the one-page frontend
├── tests/
│   └── test_app.py         # 9 pytest unit tests for the API
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml      # PORT, LOG_LEVEL
│   ├── secret.yaml         # PLACEHOLDER values only, see below
│   ├── deployment.yaml     # 2 replicas, probes, resources, securityContext
│   ├── service.yaml        # ClusterIP
│   ├── ingress.yaml        # taskboard.local via nginx ingress (example)
│   ├── hpa.yaml            # scales 2-5 replicas on CPU
│   └── servicemonitor.yaml # for clusters with the Prometheus Operator
├── observability/
│   └── grafana-dashboard.json  # small dashboard for the /metrics metrics
├── Dockerfile
└── taskboard-image.tar     # prebuilt image (gitignored), see "Run it"
```

Architecture (traffic flow):

```
browser -> Ingress (taskboard.local) -> Service (ClusterIP, port 80)
                                        -> Deployment pods (2 replicas, port 8080)
                                           each pod: gunicorn -> Flask app
                                                      |
                                                      v
                                              stdout: JSON logs
                                              /metrics: Prometheus scrape
```

## Run it with Docker

Build the image (needs Docker with normal network access):

```
docker build -t taskboard:local .
```

Or, if you have the prebuilt image tar (a local build artifact, not
committed to git), load it instead of building:

```
docker load -i taskboard-image.tar
```

Then run it:

```
docker run --rm -p 8080:8080 taskboard:local
```

Open http://localhost:8080. Try:

```
curl localhost:8080/healthz
curl -X POST localhost:8080/api/tasks -H 'Content-Type: application/json' \
  -d '{"title":"learn HPA"}'
curl localhost:8080/api/tasks
curl localhost:8080/metrics
```

Run the tests:

```
python3 -m venv .venv && .venv/bin/pip install -r app/requirements.txt
.venv/bin/python -m pytest tests/ -v
```

## Deploy it to a cluster

1. Push the image to a registry you can reach, and put that tag in
   `k8s/deployment.yaml` (it currently says `taskboard:local`).
2. Replace the placeholder secret. The one in `k8s/secret.yaml` contains
   dummy base64 values (`dummy-user`, `dummy-password`) and is labeled as
   a placeholder. For anything real, create the secret with
   `kubectl create secret` or a secret manager instead of committing values.
3. Apply the manifests:

```
kubectl apply -f k8s/namespace.yaml -f k8s/configmap.yaml -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml -f k8s/hpa.yaml
# only if the Prometheus Operator is installed:
kubectl apply -f k8s/servicemonitor.yaml
```

Without the operator, Prometheus can still scrape the pods: the Deployment
sets the standard `prometheus.io/scrape`, `prometheus.io/port`, and
`prometheus.io/path` annotations.

4. Check it:

```
kubectl -n taskboard get pods
kubectl -n taskboard port-forward svc/taskboard 8080:80
# then curl localhost:8080/healthz
```

To try the autoscaler: `kubectl -n taskboard get hpa -w` while sending
traffic. CPU target is 70%, min 2 / max 5 replicas.

Import `observability/grafana-dashboard.json` into Grafana to see request
rate, task count, and uptime (it queries the `taskboard_*` metrics).

## What was verified on 2026-10-14

On the build VM (Ubuntu 24.04, no Docker/Podman preinstalled):

- `pytest tests/ -v`: 9 passed.
- All 7 core manifests pass `kubeconform` schema validation
  (namespace, configmap, secret, deployment, service, ingress, hpa).
  The ServiceMonitor was not schema-checked (it is a Prometheus Operator
  CRD, not a built-in Kubernetes type).
- The image builds to `taskboard:local` (132 MB, python:3.12-slim base)
  and the container runs: `/healthz`, `/readyz`, `/metrics`, and the full
  task CRUD were all exercised with curl against the running container,
  including 400 and 404 cases. Logs come out as one-JSON-object-per-line.
- The frontend page loads and the add/check/delete buttons work.

Two sandbox-specific notes, so nothing is overstated:

- This VM's sandbox blocks the syscalls container runtimes need to start
  build containers, so `docker build` could not run here. The image was
  assembled from the exact same pieces the Dockerfile describes (same
  python:3.12-slim base layers, same pinned Flask/gunicorn, same app
  files, same uid 10001 user, same env and CMD), then verified with
  `docker load` and a real container run. On a normal machine,
  `docker build -t taskboard:local .` works as written.
- No live cluster deploy was done here. kind/k3d need a working Docker,
  and k3s refuses to start on this VM (`failed to find cpu cgroup (v2)`);
  the sandbox does not provide the cgroups a kubelet needs. The
  manifests are validated but have not been applied to a real cluster
  yet. That step is still to do.

## Learning in progress

Honest status, not resume language:

- I have real container experience (a merged Podman PR at Red Hat) but I
  am still learning Kubernetes itself. I wrote these manifests by reading
  the docs for each field, and I validated them with kubeconform, but I
  have not yet watched them run on a live cluster or debugged a real
  CrashLoopBackOff.
- Still to learn by doing: applying this to a local kind/k3d cluster,
  watching the HPA actually scale under load, reading `kubectl describe`
  output for a failing pod, and setting up Prometheus + Grafana for real
  instead of just shipping the dashboard JSON.
- Known simplifications in this project: in-memory storage (no database),
  one gunicorn worker (so the in-memory state stays consistent), a
  placeholder secret, and an example Ingress hostname (`taskboard.local`)
  that only works with a local hosts entry and an ingress controller.
