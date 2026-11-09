# Fictional Skyle Workspace Guide

This document is an original fictional sample for the Skyle AI local demo. Skyle AI is a local-first research workbench prototype. The fictional workspace stores uploaded document text and search metadata in a local SQLite database. CSV and image uploads are processed in memory and are not retained. The demo knowledge search uses SQLite FTS5 keyword retrieval and returns excerpts with source IDs. It does not use embeddings by default.

For the fictional demo, an operator may remove one document from the Knowledge panel or clear the complete local index. The workspace has no per-user access controls, encryption-at-rest, or multi-user tenancy. It should remain bound to loopback unless an operator has configured a trusted access boundary and bearer key.

Skyle's deterministic chat router can call local text analysis or knowledge retrieval. It is not a self-directed multi-agent system. A remote OpenAI-compatible LLM can be enabled explicitly; when active, the configured endpoint receives the question and retrieved excerpts. No remote provider is contacted by default.
