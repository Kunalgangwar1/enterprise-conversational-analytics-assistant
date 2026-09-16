# Data Discovery

Data Discovery answers specific dataset, table, column, schema, and source-location questions. Its
registry contains the seven synthetic tables and only repository identifiers beginning with
`datasets-`.

The small YAML registry stores table-to-repository/domain mappings. At runtime it is validated and
enriched from the existing `MetadataRegistry`, which combines Phase 5 semantic descriptions,
aliases, and columns with the local SQLAlchemy schema definitions without opening a database.

Search is deterministic: exact table or dataset names rank above exact columns and aliases, then
phrases and token overlap. `DATA_DISCOVERY_TOP_K` bounds results. Unknown input returns no matches,
and broad lineage, policy, governance, or business-meaning questions are left to Knowledge Catalog.
There is no LLM, embedding, database-row access, or generated answer.

`POST /api/data-discovery/query` protects the raw question and returns only dataset, repository,
table, domain, description, matched metadata fields, and score.
