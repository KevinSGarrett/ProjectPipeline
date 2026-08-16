CREATE TABLE requirements (
    requirement_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    statement TEXT NOT NULL,
    implementation_state TEXT NOT NULL,
    disposition TEXT NOT NULL,
    priority TEXT NOT NULL,
    risk TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    record_json TEXT NOT NULL,
    imported_at_utc TEXT NOT NULL
);

CREATE INDEX idx_requirements_domain_state
ON requirements(domain, implementation_state, priority, requirement_id);

CREATE TABLE traceability_links (
    link_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(requirement_id) ON DELETE CASCADE,
    link_type TEXT NOT NULL,
    target TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    authority TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(requirement_id, link_type, target, authority)
);

CREATE INDEX idx_traceability_links_target
ON traceability_links(link_type, target, requirement_id);

CREATE TABLE catalog_imports (
    import_id TEXT PRIMARY KEY,
    catalog_sha256 TEXT NOT NULL,
    requirement_count INTEGER NOT NULL CHECK (requirement_count >= 0),
    link_count INTEGER NOT NULL CHECK (link_count >= 0),
    imported_at_utc TEXT NOT NULL,
    source_path TEXT NOT NULL,
    UNIQUE(catalog_sha256, source_path)
);

CREATE TABLE traceability_mutations (
    mutation_id TEXT PRIMARY KEY,
    requirement_id TEXT NOT NULL REFERENCES requirements(requirement_id) ON DELETE CASCADE,
    operation TEXT NOT NULL,
    link_type TEXT NOT NULL,
    target TEXT NOT NULL,
    previous_revision INTEGER NOT NULL,
    resulting_revision INTEGER NOT NULL,
    changed INTEGER NOT NULL,
    actor_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);
