-- MedScan AI reference schema (PostgreSQL). The application also creates these tables
-- automatically on start-up through SQLAlchemy (Base.metadata.create_all); this file is for review/DBAs.
-- Privacy by design: no patient identifiers, no original filenames, no EXIF/DICOM metadata are stored.
-- No users table: authentication is not implemented in this version.

CREATE TABLE IF NOT EXISTS medical_images (
    id              VARCHAR(36)  PRIMARY KEY,
    category        VARCHAR(40)  NOT NULL,
    stored_path     VARCHAR(300) NOT NULL,
    sha256          VARCHAR(64)  NOT NULL,
    width           INTEGER      NOT NULL,
    height          INTEGER      NOT NULL,
    size_bytes      INTEGER      NOT NULL,
    source_format   VARCHAR(10)  NOT NULL,
    uploaded_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_medical_images_category ON medical_images (category);
CREATE INDEX IF NOT EXISTS ix_medical_images_sha256   ON medical_images (sha256);

CREATE TABLE IF NOT EXISTS analysis_results (
    id             VARCHAR(36)  PRIMARY KEY,
    image_id       VARCHAR(36)  NOT NULL REFERENCES medical_images(id) ON DELETE CASCADE,
    category       VARCHAR(40)  NOT NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'pending',   -- pending | completed | failed
    model_id       VARCHAR(80)  NOT NULL,
    model_info     JSON,
    findings       JSON,
    summary        VARCHAR(40),
    top_finding    VARCHAR(80),
    top_score      DOUBLE PRECISION,
    warnings       JSON,
    heatmap_path   VARCHAR(300),
    heatmap_label  VARCHAR(80),
    error_message  TEXT,
    inference_ms   INTEGER,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_analysis_results_image_id   ON analysis_results (image_id);
CREATE INDEX IF NOT EXISTS ix_analysis_results_status     ON analysis_results (status);
CREATE INDEX IF NOT EXISTS ix_analysis_results_category   ON analysis_results (category);
CREATE INDEX IF NOT EXISTS ix_analysis_results_created_at ON analysis_results (created_at);

CREATE TABLE IF NOT EXISTS reports (
    id           VARCHAR(36)  PRIMARY KEY,
    analysis_id  VARCHAR(36)  NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    file_path    VARCHAR(300) NOT NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_reports_analysis_id ON reports (analysis_id);

CREATE TABLE IF NOT EXISTS analysis_history (   -- append-only audit trail
    id           SERIAL       PRIMARY KEY,
    analysis_id  VARCHAR(36)  NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    event        VARCHAR(40)  NOT NULL,          -- created | started | completed | failed | report_generated
    detail       TEXT,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_analysis_history_analysis_id ON analysis_history (analysis_id);
