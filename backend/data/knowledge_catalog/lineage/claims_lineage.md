---
id: lineage_claims
title: Claims Lineage
node_type: lineage
summary: Generated encounter and participant references flow into claim headers and service lines.
parent: domain_claims
domain: claims
---
# Claims Lineage

## Upstream relationships

A claim references its generated member and provider and can optionally reference an encounter.
Claim lines are children of the claim header and carry procedure, diagnosis, units, and amounts.

## Analytical flow

Aggregate header measures at claim grain. Join claim lines only when service-level detail is needed,
and guard against multiplying header amounts when a claim contains multiple lines.
