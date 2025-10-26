-- Schema changes for xp table (SQLite-first, Postgres-ready semantics)
ALTER TABLE xp
  ADD COLUMN validation_signals TEXT DEFAULT '{}';
ALTER TABLE xp
  ADD COLUMN confidence_score REAL DEFAULT 0.0;
ALTER TABLE xp
  ADD COLUMN confidence_label TEXT DEFAULT 'Low';

-- SQLite does not support CREATE INDEX IF NOT EXISTS on older versions; safe to include
CREATE INDEX IF NOT EXISTS idx_xp_confidence ON xp(confidence_score);

