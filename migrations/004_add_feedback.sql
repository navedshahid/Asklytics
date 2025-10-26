CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY,
  ts DATETIME DEFAULT CURRENT_TIMESTAMP,
  xp_id INTEGER,
  user_id TEXT,
  verdict TEXT CHECK(verdict IN ('correct','incorrect')),
  comment TEXT,
  sql_hash TEXT,
  confidence REAL,
  masked BOOLEAN DEFAULT 1,
  retrain_used BOOLEAN DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_feedback_xp ON feedback(xp_id);
CREATE INDEX IF NOT EXISTS idx_feedback_ts ON feedback(ts);

