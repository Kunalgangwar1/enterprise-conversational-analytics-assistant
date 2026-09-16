---
id: policy_sensitive_data
title: Sensitive Data Handling Policy
node_type: policy
summary: Handling rules for synthetic identifiers and contact-like fields.
parent: catalog_root
domain: governance
---
# Sensitive Data Handling Policy

Even though this repository uses generated records, member and transaction identifiers should be
tokenized before model calls. Email addresses and phone numbers should be irreversibly redacted.
Do not commit credentials, privacy mappings, raw prompts, or generated row-level result artifacts.
