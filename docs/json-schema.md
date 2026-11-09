# JSON Schema

[`iceberg.schema.json`](schema/iceberg.schema.json) is a
[JSON Schema (draft 2020-12)](https://json-schema.org/draft/2020-12) for the
output of `iceberg --json`. The repository also has it at
[`docs/schema/iceberg.schema.json`](https://github.com/andrewasheridan/iceberg/blob/main/docs/schema/iceberg.schema.json).
Use it to validate snapshots. You can also use it to make types for programs in
other languages that read the output.

The schema is for `schema_version` 2. If a change to the JSON format can break
the programs that read it, `schema_version` and this schema change together.

With `--keep-going`, the output also has a top-level `diagnostics` list. The
schema shows this list as optional. Thus, output without the list is also valid.
