-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create patents table
CREATE TABLE patents (
    patent_id VARCHAR(20) PRIMARY KEY,
    patent_title TEXT NOT NULL,
    patent_date DATE NOT NULL,
    summary_text TEXT,
    assignee_organization VARCHAR(500),
    assignee_country VARCHAR(2),
    assignee_type VARCHAR(10),
    cpc_groups JSONB,
    wipo_field_id VARCHAR(10),
    inventor_count INT,
    inventor_names JSONB,
    raw_data JSONB,
    embedding VECTOR(1536),
    search_topic VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX idx_patent_date ON patents(patent_date);
CREATE INDEX idx_assignee_org ON patents(assignee_organization);
CREATE INDEX idx_assignee_country ON patents(assignee_country);
CREATE INDEX idx_search_topic ON patents(search_topic);
CREATE INDEX idx_cpc_groups ON patents USING GIN(cpc_groups);

-- Index for vector similarity search (will be useful later)
-- Note: ivfflat requires training data, so we'll add this after inserting patents
-- CREATE INDEX idx_embedding ON patents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Create a view for easy querying without raw_data
CREATE VIEW patents_summary AS
SELECT
    patent_id,
    patent_title,
    patent_date,
    LEFT(summary_text, 200) AS summary_preview,
    assignee_organization,
    assignee_country,
    inventor_count,
    search_topic,
    created_at
FROM patents;
