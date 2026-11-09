# JSON Schema

[`iceberg.schema.json`](schema/iceberg.schema.json) is a
[JSON Schema (draft 2020-12)](https://json-schema.org/draft/2020-12) for the
output of `iceberg --json`. It is also in the repository at
[`docs/schema/iceberg.schema.json`](https://github.com/andrewasheridan/iceberg/blob/main/docs/schema/iceberg.schema.json).
Use it to validate snapshots, or to generate types for consumers written in
other languages.

The schema describes `schema_version` 2. When the JSON format changes in a way
that can break consumers, `schema_version` and this schema change together.

With `--keep-going`, the output also has a top-level `diagnostics` list. The
schema describes it as optional, so output without it still validates.
