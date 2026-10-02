# Label that marks Jobs created by this service, so the list endpoint can find "managed" Jobs.
MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
MANAGED_BY_VALUE = "cluster-job-runner"

# Annotation that stores the original request, so a Job can be re-run with the same spec.
SPEC_ANNOTATION = "cluster-job-runner/spec"

# Retries before a Job counts as Failed. The Kubernetes default is 6, which takes ~10 minutes to fail.
BACKOFF_LIMIT = 1
