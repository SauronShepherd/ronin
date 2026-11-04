# Ronin single-operator Kubernetes chart

This chart is for a local, single-node development cluster. It is not a
production Kubernetes deployment, does not support horizontal scaling, and
does not include Ronin Pro multi-user settings.

The Ronin server exposes plaintext HTTP. Because Kubernetes probes and the
ClusterIP Service reach the pod over its non-loopback interface, installation
requires the operator to set
`server.bindPolicy=insecure-plaintext-network` explicitly. The chart does not
enable that policy by default. Use the chart only on a trusted local cluster;
keep the Service private and use `kubectl port-forward` for operator access.
Put an external TLS terminator at any remote client-facing boundary. The
`container-internal` policy is reserved for Ronin's supported private Compose
bridge and is not valid for this chart.

The operator must also provide a non-empty bearer token and non-empty,
project-scoped token grants. The token is rendered only into a Kubernetes
Secret. Protect the cluster's Secret storage and kubeconfig with the same care
as other credentials.

Example values for a local cluster:

```yaml
image:
  repository: ronin
  tag: local
  pullPolicy: IfNotPresent
server:
  replicas: 1
  token: REPLACE_WITH_A_RANDOM_LOCAL_TOKEN
  tokenScopes: '{"version":1,"grants":[{"version":1,"actions":["read","list"],"resource":{"kind":"project","identifier":"examples/demo"},"constraints":{}}]}'
  bindPolicy: insecure-plaintext-network
```
