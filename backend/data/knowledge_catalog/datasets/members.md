---
id: dataset_members
title: Members Dataset
node_type: dataset
summary: One row per synthetic enrolled member with demographics, contact fields, and enrollment dates.
parent: domain_member
domain: member
---
# Members Dataset

## Grain and keys

`members` contains one row per generated member. `id` is the internal key and
`member_external_id` is the unique synthetic business identifier.

## Important columns

Enrollment is bounded by `enrollment_start` and optional `enrollment_end`. `date_of_birth`,
`sex_at_birth`, and `state` support demographic grouping. `first_name`, `last_name`, `email`, and
`phone` are sensitive fields and are not needed for routine aggregate analytics.
