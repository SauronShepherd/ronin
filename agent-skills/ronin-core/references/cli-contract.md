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

Do not assume `ronin agent ...`, `ronin projects ...`, `ronin ml ...`, or `ronin deploy ...` exists.

A successful command proves only that operation in that environment. Keep implementation status, qualification evidence, and release status separate.
