-- Bridge Hub — Draft Comments & Assignment Migration
-- append-only, არსებულ ცხრილებს არ ცვლის

-- Comments ცხრილი
CREATE TABLE IF NOT EXISTS draft_comments (
    id              SERIAL PRIMARY KEY,
    draft_id        INTEGER NOT NULL REFERENCES journal_drafts(id) ON DELETE CASCADE,
    tenant_id       VARCHAR(100) NOT NULL DEFAULT 'default',
    author          VARCHAR(200) NOT NULL DEFAULT 'system',
    author_role     VARCHAR(50) NOT NULL DEFAULT 'accountant',
    comment_text    TEXT NOT NULL,
    comment_type    VARCHAR(50) NOT NULL DEFAULT 'note',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_draft_comments_draft_id 
    ON draft_comments(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_comments_tenant_id 
    ON draft_comments(tenant_id);

-- journal_drafts-ში assignment ველები
ALTER TABLE journal_drafts 
    ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(200) DEFAULT NULL;
ALTER TABLE journal_drafts 
    ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE journal_drafts 
    ADD COLUMN IF NOT EXISTS assigned_by VARCHAR(200) DEFAULT NULL;
ALTER TABLE journal_drafts 
    ADD COLUMN IF NOT EXISTS priority VARCHAR(20) DEFAULT 'normal';