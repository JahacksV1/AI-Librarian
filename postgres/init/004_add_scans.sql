-- Phase 1.7: Scan architecture — scan records + file enrichments
-- Must run AFTER 001_create_enums.sql and 002_create_tables.sql

CREATE TYPE scan_status_enum AS ENUM ('RUNNING', 'COMPLETED', 'FAILED');
CREATE TYPE scan_depth_enum  AS ENUM ('ROOT', 'DEEP', 'CONTENT');

CREATE TABLE scans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES sessions(id),
    device_id       UUID NOT NULL REFERENCES devices(id),
    root_path       TEXT NOT NULL,
    scan_depth      scan_depth_enum NOT NULL DEFAULT 'DEEP',
    recursive       BOOLEAN NOT NULL DEFAULT true,
    file_count      INTEGER,
    folder_count    INTEGER,
    new_files       INTEGER DEFAULT 0,
    deleted_files   INTEGER DEFAULT 0,
    modified_files  INTEGER DEFAULT 0,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          scan_status_enum NOT NULL DEFAULT 'RUNNING',
    summary_json    JSONB,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_scans_session_id ON scans(session_id);
CREATE INDEX idx_scans_device_id  ON scans(device_id);

-- Enrich file_entities with persisted category + preview + scan link
ALTER TABLE file_entities ADD COLUMN guessed_category TEXT;
ALTER TABLE file_entities ADD COLUMN content_preview  TEXT;
ALTER TABLE file_entities ADD COLUMN last_scan_id     UUID REFERENCES scans(id);
