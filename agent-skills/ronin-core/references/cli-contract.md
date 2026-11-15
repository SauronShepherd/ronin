# Ronin CLI contract used by this skill

Documented command surface from the supplied Ronin analysis:

- `ronin doctor --require core|all`
- `ronin validate PROJECT`
- `ronin plan PROJECT --target TARGET`
- `ronin serve`
- `ronin worker`
- `ronin submit PROJECT -t TARGET [--idempotency-key ...] [--json]`
- `ronin status ID [--wait] [--json]`
- `ronin logs ID [--since ...] [--follow] [--json]`
- `ronin evidence ID [--json]`
- `ronin jobs [--project ...] [--state ...] [--json]`
- `ronin cancel ID [--json]`
- `ronin quality contract get WORKSPACE ASSET VERSION [--json]`
- `ronin quality contract put WORKSPACE ASSET VERSION CONTRACT_JSON [--json]`
- `ronin quality run WORKSPACE REQUEST_JSON [--json]`
- `ronin quality history WORKSPACE ASSET VERSION [--json]`
- `ronin quality state WORKSPACE ASSET VERSION [--json]`
- `ronin alerts rules WORKSPACE [--json]`
- `ronin alerts instances WORKSPACE [--limit N] [--json]`
- `ronin alerts evaluate WORKSPACE RULE_ID [--json]`
- `ronin alerts acknowledge WORKSPACE RULE_ID FINGERPRINT [--json]`

The control-plane catalog, ontology and graph inspection commands are also
available through `catalog`, `ontology` and `graphs`; `catalog assets` and
`catalog lineage` accept `--include-quality` to return the bounded latest
quality state for each governed revision or lineage endpoint. Quality and
alert commands use the same authenticated control-plane client and durable
server contracts.

Do not assume `ronin agent ...`, `ronin projects ...`, `ronin ml ...`, or `ronin deploy ...` exists.

A successful command proves only that operation in that environment. Keep implementation status, qualification evidence, and release status separate.
