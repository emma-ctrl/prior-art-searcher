# Prior Art Searcher - Patent Database POC

A proof-of-concept system for collecting and storing patent documents with vector search capabilities.

## Overview

This project seeds a PostgreSQL database (with pgvector extension) with patent data from the PatentsView API. It focuses on patents from 2023 onwards across various technical domains.

## Features

- 🐘 PostgreSQL with pgvector for vector similarity search (ready for embeddings)
- 🔍 Automated patent search across multiple topics
- ⚡ Rate-limited API requests (45 requests/minute)
- 📊 Comprehensive metadata storage (assignees, inventors, CPC classifications)
- 🐳 Docker-based setup for easy deployment

## Tech Stack

- **Database**: PostgreSQL 16 + pgvector extension
- **API**: PatentsView API v1
- **Language**: Python 3.x
- **Containerization**: Docker Compose

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.8+
- PatentsView API access (no key required for basic usage)

### 1. Start the Database

```bash
docker-compose up -d
```

This will:
- Start PostgreSQL with pgvector extension
- Create the `patent_db` database
- Run initialization script (`init.sql`)
- Expose database on `localhost:5432`

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Seeding Script

```bash
python seed_patents.py
```

The script will:
- Fetch patents for each configured topic
- Retrieve summary texts (when available)
- Store all data in the database
- Respect API rate limits automatically

Expected runtime: ~30-60 minutes for ~1,000 patents (depending on API response times)

## Configuration

Edit `config.json` to customize:

### Search Topics

```json
{
  "search_topics": [
    {
      "name": "heat_pump",
      "query": "heat pump",
      "max_patents": 150
    }
  ]
}
```

Add or modify topics as needed. Current topics include:
- Heat pumps and thermal systems
- Agricultural robotics
- Video game AI
- Satellite technology

### Database Connection

```json
{
  "database": {
    "host": "localhost",
    "port": 5432,
    "database": "patent_db",
    "user": "patent_user",
    "password": "patent_password"
  }
}
```

## Database Schema

### Main Table: `patents`

| Column | Type | Description |
|--------|------|-------------|
| `patent_id` | VARCHAR(20) | Primary key |
| `patent_title` | TEXT | Patent title |
| `patent_date` | DATE | Grant date |
| `summary_text` | TEXT | Patent summary (when available) |
| `assignee_organization` | VARCHAR(500) | Company/org that owns patent |
| `assignee_country` | VARCHAR(2) | Assignee country code |
| `assignee_type` | VARCHAR(10) | Type code (2=US company, 3=foreign, etc.) |
| `cpc_groups` | JSONB | Array of CPC classification codes |
| `wipo_field_id` | VARCHAR(10) | WIPO technology field |
| `inventor_count` | INT | Number of inventors |
| `inventor_names` | JSONB | Array of inventor names |
| `raw_data` | JSONB | Full API response |
| `embedding` | VECTOR(1536) | Vector embedding (NULL until populated) |
| `search_topic` | VARCHAR(100) | Topic used to find this patent |
| `created_at` | TIMESTAMP | Record creation time |

### View: `patents_summary`

Simplified view without raw data for easier querying.

## Querying the Database

### Connect via psql

```bash
docker exec -it patent_db psql -U patent_user -d patent_db
```

### Example Queries

```sql
-- Count patents by topic
SELECT search_topic, COUNT(*)
FROM patents
GROUP BY search_topic;

-- Find recent heat pump patents
SELECT patent_id, patent_title, patent_date, assignee_organization
FROM patents
WHERE search_topic = 'heat_pump'
  AND patent_date >= '2024-01-01'
ORDER BY patent_date DESC
LIMIT 10;

-- Patents by country
SELECT assignee_country, COUNT(*) as count
FROM patents
GROUP BY assignee_country
ORDER BY count DESC;

-- Patents with summaries
SELECT COUNT(*) as with_summary
FROM patents
WHERE summary_text IS NOT NULL;
```

## API Rate Limiting

The script automatically handles rate limiting:
- **Limit**: 45 requests per minute
- **Implementation**: Uses `@sleep_and_retry` decorator
- **Behavior**: Automatically sleeps when limit is reached

At 45 req/min:
- Fetching 100 patents with summaries: ~2-3 minutes
- Full 1,000 patent collection: ~30-60 minutes

## Adding Vector Embeddings (Future)

The database is ready for vector embeddings. To add them later:

1. Install embedding library (e.g., OpenAI, sentence-transformers)
2. Generate embeddings for `summary_text`
3. Update the `embedding` column
4. Create index for similarity search:

```sql
CREATE INDEX idx_embedding ON patents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

## Troubleshooting

### Database Connection Issues

```bash
# Check if container is running
docker ps

# View logs
docker logs patent_db

# Restart container
docker-compose restart
```

### API Rate Limit Errors

The script should handle this automatically. If you see errors:
- Check your internet connection
- Verify PatentsView API is accessible
- Reduce `rate_limit_per_minute` in `config.json`

### No Summary Text

Not all patents have summaries. Only patents from 2023 onwards typically have `g_brf_sum_text` available. This is expected behavior.

## Project Structure

```
prior-art-searcher/
├── docker-compose.yml      # Docker services configuration
├── init.sql                # Database schema and initialization
├── seed_patents.py         # Main seeding script
├── requirements.txt        # Python dependencies
├── config.json            # Search topics and configuration
└── README.md              # This file
```

## Next Steps

This POC provides the foundation for:
1. **Semantic search**: Add embeddings for similarity search
2. **Web interface**: Build TypeScript/Next.js frontend
3. **Advanced queries**: Implement filtering by CPC codes, dates, etc.
4. **Periodic updates**: Schedule script to fetch new patents regularly
5. **Analytics**: Visualize patent trends and insights

## License

MIT

## Acknowledgments

- Data provided by [PatentsView API](https://search.patentsview.org/)
- Vector search powered by [pgvector](https://github.com/pgvector/pgvector)
