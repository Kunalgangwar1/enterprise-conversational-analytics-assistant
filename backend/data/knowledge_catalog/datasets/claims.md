---
id: dataset_claims
title: Claims Dataset
node_type: dataset
summary: One row per synthetic claim header with service date, payer, status, and monetary amounts.
parent: domain_claims
domain: claims
---
# Claims Dataset

## Grain and relationships

`claims` contains one generated claim header per row. `claim_external_id` is unique. The row joins
to a member and provider; `encounter_id` is optional when no source encounter is linked.

## Financial measures

`submitted_amount` is the amount initially requested. `allowed_amount` is the amount recognized as
eligible under the synthetic payment rules, so it cannot exceed submitted amount. `paid_amount` is
the amount paid and cannot exceed allowed amount. Values use fixed two-decimal precision.

## Status and payer

`claim_status` can be submitted, pending, paid, denied, or adjusted. `payer_type` can be commercial,
medicare, medicaid, or self-pay in this generated dataset.
