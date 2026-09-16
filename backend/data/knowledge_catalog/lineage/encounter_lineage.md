---
id: lineage_encounters
title: Encounter Lineage
node_type: lineage
summary: Generated member, provider, and facility references converge in encounter facts.
parent: domain_clinical_encounters
domain: clinical_encounters
---
# Encounter Lineage

Each encounter references exactly one generated member, provider, and facility. Claims may refer
back to an encounter, while appointments are a separate scheduling fact and should not be assumed
to represent a completed encounter without an explicit relationship.
