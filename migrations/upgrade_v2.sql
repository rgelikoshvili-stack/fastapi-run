-- Bridge Hub upgrade_v2.sql
-- Run once on production DB: psql $DATABASE_URL < migrations/upgrade_v2.sql

ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS validation_errors TEXT[];
ALTER TABLE journal_drafts ADD COLUMN IF NOT EXISTS confidence_score DECIMAL(5,4);

CREATE INDEX IF NOT EXISTS idx_journal_drafts_status     ON journal_drafts(status);
CREATE INDEX IF NOT EXISTS idx_journal_drafts_tenant     ON journal_drafts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_journal_drafts_confidence ON journal_drafts(confidence_score);
CREATE INDEX IF NOT EXISTS idx_journal_drafts_created    ON journal_drafts(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_bank_accounts_tenant      ON bank_accounts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_budgets_tenant_year       ON budgets(tenant_id, year);
