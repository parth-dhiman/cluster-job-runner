# Cluster Job Runner

A small Flask service that creates, monitors, reruns and deletes Kubernetes Jobs on a local cluster. It talks to the real cluster through the official Kubernetes Python client. Nothing is mocked or cached. It also has a simple web page for doing all of this from the browser.

## What you need

- Python 3.13
- Docker, plus minikube (or k3s)
- `kubectl` pointed at that cluster

Check the cluster is up before starting:

```
kubectl get nodes      # should show one node, Ready
```

On Windows, run everything (Python, minikube, kubectl) inside WSL, so the app and kubectl read the same kubeconfig.

## Run it

```
git clone https://github.com/parth-dhiman/shakudo-cluster-job-runner
cd shakudo-cluster-job-runner

minikube start
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

python run.py
```

- Web UI: http://127.0.0.1:3000
- API: http://127.0.0.1:3000/api/jobs

The app uses your current kubeconfig context (`~/.kube/config`, or whatever `$KUBECONFIG` points to). For k3s, that means `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` before running.

## The web UI

Open http://127.0.0.1:3000. You can:

- see every Job with a coloured status (there's a legend at the top)
- click a Job to see its conditions and pods: phase, restarts, container state, node
- rerun or delete a Job
- create a Job from JSON. The **New Job** dialog has one-click presets for the three demo runs below.

The page refreshes every 3 seconds, so you can watch a Job go from PENDING to its final state.

## API

| Method | Path | What it does | Success |
|---|---|---|---|
| `POST` | `/api/jobs` | Create a Job from a JSON spec. Creates the namespace if it doesn't exist. | `201` |
| `GET` | `/api/jobs?namespace=` | List the Jobs this service created. Leave out `namespace` to list all namespaces. | `200` |
| `GET` | `/api/jobs/<name>?namespace=` | Counts, conditions, start and completion times, and every pod's phase, restarts, container states and node. | `200` |
| `DELETE` | `/api/jobs/<name>?namespace=` | Delete the Job and its pods. | `204` |
| `POST` | `/api/jobs/<name>/rerun?namespace=` | Start a fresh Job with the same spec. | `201` |

For the last three, `namespace` defaults to `default` if you leave it out.

### Example

```
curl -X POST localhost:3000/api/jobs -H "Content-Type: application/json" -d '{
  "name": "hello",
  "namespace": "demo",
  "image": "busybox:1.36",
  "command": ["sh", "-c", "echo hello from k8s"]
}'
```

```json
{"name": "hello", "namespace": "demo", "uid": "99fcdc3d-...", "status": "PENDING"}
```

### Job spec

| Field | Required | Default | Rule |
|---|---|---|---|
| `name` | yes | none | lowercase letters, digits and `-`; starts and ends with a letter or digit; max 63 characters |
| `image` | yes | none | a well-formed image reference, like `busybox:1.36` or `ghcr.io/org/app:v1` |
| `namespace` | no | `default` | same rule as `name` |
| `command` | no | the image's own entrypoint | list of strings |
| `args` | no | the image's own arguments | list of strings |
| `env` | no | none | object of string → string, e.g. `{"GREETING": "hi"}` |
| `completions` | no | `1` | integer, at least 1 |
| `parallelism` | no | `1` | integer, at least 1 |
| `resources.requests.cpu` / `.memory` | no | none | Kubernetes quantity, like `100m`, `0.5`, `64Mi` |
| `resources.limits.cpu` / `.memory` | no | none | same; a request can't be bigger than its limit |

Any field not in this table is rejected. A typo like `parallism` gets a 400 instead of being silently ignored.

### Errors

Every error has the same shape:

```json
{"error": {"code": "INVALID_PAYLOAD", "message": "Payload sent was invalid.",
           "details": [{"field": "name", "message": "Must be lowercase letters, digits, or '-', ..."}]}}
```

`details` only shows up for validation errors, with one entry per bad field.

| Status | Code | When |
|---|---|---|
| `400` | `INVALID_PAYLOAD` | Bad input: a non-DNS name, a malformed image, `completions` below 1, a bad resource quantity, an unknown field. Also used when Kubernetes rejects a value the schema let through. |
| `404` | `NOT_FOUND` | The Job doesn't exist, or wasn't created by this service. |
| `409` | `CONFLICT` | A Job with that name already exists in that namespace. |
| `500` | `KUBERNETES_ERROR` | Kubernetes refused the call for a reason that isn't the caller's fault, such as permissions. The message is Kubernetes' own. |
| `503` | `K8S_UNREACHABLE` | The cluster can't be reached. |
| `500` | `INTERNAL_ERROR` | A bug on our side. The details go to the logs, not the response. |

## Status

Each Job gets one status, worked out live from the Job and its pods on every request. The rules are checked in this order, and the first match wins:

| # | If… | Status |
|---|---|---|
| 1 | the Job has a `Complete` condition | `SUCCEEDED` |
| 2 | the Job has a `Failed` condition | `FAILED` |
| 3 | any container is waiting with `ImagePullBackOff`, `ErrImagePull`, `InvalidImageName` or `CrashLoopBackOff` | `STUCK` |
| 4 | any pod is `Running` | `RUNNING` |
| 5 | any pod is `Unknown` (its node lost contact) | `UNKNOWN` |
| 6 | anything else (not started yet, or waiting to retry) | `PENDING` |

Two details matter here:

- **STUCK is checked before RUNNING.** A pod that can't pull its image still counts as "active" in the Job's own numbers, so a check based on `active` alone would call it RUNNING.
- **A missing image is STUCK, not FAILED.** Kubernetes never marks that Job as failed. It just keeps retrying the pull forever. The only sign of trouble is on the pod.

## Demo: the three runs

With the app running, create one Job that succeeds, one with an image that doesn't exist, and one that exits with an error:

```
curl -s -X POST localhost:3000/api/jobs -H "Content-Type: application/json" \
  -d '{"name": "ok", "namespace": "demo", "image": "busybox:1.36", "command": ["sh", "-c", "echo hi"]}'

curl -s -X POST localhost:3000/api/jobs -H "Content-Type: application/json" \
  -d '{"name": "bad-image", "namespace": "demo", "image": "doesnotexist/nope:1.0"}'

curl -s -X POST localhost:3000/api/jobs -H "Content-Type: application/json" \
  -d '{"name": "fails", "namespace": "demo", "image": "busybox:1.36", "command": ["sh", "-c", "exit 1"]}'
```

Then watch them in the UI, or with `curl -s "localhost:3000/api/jobs?namespace=demo"`:

| Job | What you'll see |
|---|---|
| `ok` | PENDING → RUNNING → **SUCCEEDED**, within a few seconds |
| `bad-image` | PENDING → **STUCK**, and it stays there |
| `fails` | PENDING → RUNNING → PENDING (waiting to retry) → RUNNING → **FAILED**, in about 30 seconds |

Clean up with `kubectl delete namespace demo`.

## Tests

```
python -m pytest tests/unit           # no cluster needed
python -m pytest tests/integration    # needs the cluster running
python -m pytest                      # everything
```

- **`tests/unit/test_input.py`** covers input validation: required fields, names and namespaces (including the 63/64-character edge), image formats, counts, resource quantities, requests vs limits, wrong types and unknown fields.
- **`tests/integration/test_lifecycle.py`** runs a Job through create → list → fetch → rerun → delete against the real cluster.
- **`tests/integration/test_duplicate.py`** creates the same Job twice and expects `409 CONFLICT` the second time.

Each integration test runs in its own throwaway namespace (`test-xxxxxx`). The namespace is deleted afterwards, even if the test fails, so your own Jobs are never touched.

## How it's put together

```
app/
  api/jobs.py          routes, plus serving the web page
  api/errors.py        turns any exception into the JSON error shape above
  schema/jobs.py       request validation (pydantic)
  services/jobs.py     does the work: talks to Kubernetes
  services/status.py   maps live Job and pod state to one status
  k8s/client.py        Kubernetes API clients; config is loaded on first use
  k8s/builders.py      turns a validated spec into a Job manifest
  config.py            label and annotation names, retry limit
  exceptions.py        NotFoundError
  ui/                  the web page (plain HTML, CSS and JavaScript)
tests/
  unit/                no cluster needed
  integration/         real cluster, throwaway namespaces
run.py                 starts the app on 127.0.0.1:3000
```

A request goes through three steps: the route validates the input, the service talks to Kubernetes, and the response comes back. Routes have no try/except. Anything that goes wrong is raised and turned into a proper error by `errors.py`, in one place.

## Decisions and assumptions

- **"Managed" Jobs.** Every Job this service creates gets the label `app.kubernetes.io/managed-by=cluster-job-runner`. The list only shows those. Get, delete and rerun return 404 for any other Job, so the API can't touch Jobs it didn't create.
- **Rerun.** A finished Job can't be restarted, so rerun creates a new one. The original request is saved on each Job in the annotation `cluster-job-runner/spec`. Rerun reads it back and creates `<name>-<6 random hex characters>`, and the old Job stays as history.
- **Fail fast.** Jobs use `restartPolicy: Never` with `backoffLimit: 1`. A failing command is marked FAILED after one retry, in about 30 seconds. With the default of 6 retries it takes around 10 minutes, and with `OnFailure` it would crash-loop instead of failing.
- **Delete takes the pods with it.** Delete uses background propagation. Without it, deleting a Job through the API leaves its pods behind.
- **Namespaces.** Get, delete and rerun default to `default`, like `kubectl` does. List with no namespace shows all namespaces. POST creates the namespace if it's missing.
- **Image check is format only.** It uses the same naming rules Docker uses. A well-formed image that doesn't exist is accepted, and shows up as STUCK.
- **Names are DNS labels (63 characters max).** Kubernetes allows longer Job names, but the name gets copied into pod labels, which are limited to 63.
- **503 for an unreachable cluster.** The brief says 500. I used 503 because it's more accurate, and it tells a client that retrying later makes sense.
- **Failed Jobs have no completion time** in Kubernetes. The UI takes the end time from the `Failed` condition instead.

## Known limitations

- **No authentication.**
- **It runs on Flask's development server.** For real use, run it under gunicorn.
- **The list endpoint looks up pods once per Job.** That's fine at this scale; for many Jobs, I'd fetch all managed pods in one call and group them.
- **Status is polled, not streamed.** There's no Kubernetes watch.
- **`env` only takes plain values,** not references to Secrets or ConfigMaps.
- **Rerunning a rerun stacks suffixes,** e.g. `hello-a1b2c3-d4e5f6`.
- **There's no unit test for the status mapping yet.** It was checked by hand against the three demo runs above.

## Troubleshooting

- **Every request returns `503 K8S_UNREACHABLE`.** The cluster is down. Run `minikube status`, and `minikube start` if it's stopped. **Then restart the app**: the kubeconfig is loaded once and cached, and minikube's API port can change when it restarts.
- **A Job you just created in `demo` returns 404.** Add `?namespace=demo`. Without it, the API looks in `default`.

## How AI was used

I built this with Claude Code as a pair programmer.

- **I wrote** the backend and tests myself. Claude reviewed each step and explained the Kubernetes and Python concepts as we went.
- **Claude supplied a few pieces directly:** the image-reference regex, parts of the error handling and Job builder, and some test cases.
- **The web UI was generated by Claude Code** from a detailed spec I wrote, then reviewed.

Everything was run against a real minikube cluster before it was committed.
