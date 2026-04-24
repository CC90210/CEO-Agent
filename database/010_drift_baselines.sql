-- ============================================================
-- BRAVO V5.6.1 — Migration 010: Drift detection baselines
-- Apply via: python scripts/apply_migration.py database/010_drift_baselines.sql
-- ============================================================
-- PURPOSE
-- Backing store for scripts/drift_detector.py. Every week we record
-- the rolling baseline for a set of metrics (send volume, reply rate,
-- cooldown-blocked rate, etc.). When this week's value deviates more
-- than 2 standard deviations from baseline, Bravo alerts CC.
-- ============================================================

CREATE TABLE IF NOT EXISTS drift_baselines (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name TEXT NOT NULL,
    dimension_key TEXT,
    baseline_mean NUMERIC,
    baseline_stddev NUMERIC,
    sample_window_days INTEGER DEFAULT 28,
    sample_count INTEGER DEFAULT 0,
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(metric_name, dimension_key)
);
CREATE INDEX IF NOT EXISTS idx_drift_baselines_metric
    ON drift_baselines (metric_name, dimension_key);

CREATE TABLE IF NOT EXISTS drift_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    metric_name TEXT NOT NULL,
    dimension_key TEXT,
    observed_value NUMERIC,
    baseline_mean NUMERIC,
    baseline_stddev NUMERIC,
    z_score NUMERIC,
    severity TEXT CHECK (severity IN ('warn', 'alert', 'critical')),
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_severity
    ON drift_alerts (severity, acknowledged, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_metric
    ON drift_alerts (metric_name, created_at DESC);

COMMENT ON TABLE drift_baselines IS
    'Rolling 28-day baselines per (metric, dimension). Refreshed weekly '
    'by scripts/drift_detector.py recompute_baselines.';
COMMENT ON TABLE drift_alerts IS
    'Firing drift alerts. Severity ladder: warn (z>2), alert (z>3), '
    'critical (z>4). Acknowledged=TRUE once CC has seen them.';

-- ============================================================
-- END OF MIGRATION 010
-- ============================================================
