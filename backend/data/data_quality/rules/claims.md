---
id: dq_rules_claims
title: Claims Quality Rules
topic: dataset_rules
dataset: claims
---
# Claims rules

`claim_external_id` is required and unique. Member and provider relationships must resolve, while
the encounter relationship may be absent. Service date and claim status are required. Submitted,
allowed, and paid amounts are non-negative; allowed should not exceed submitted, and paid should
not exceed allowed. Claim status and payer type use controlled vocabularies.
