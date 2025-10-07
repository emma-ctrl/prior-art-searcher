#!/usr/bin/env python3
"""
Patent Database Seeding Script

Fetches patent data from PatentsView API and stores in Postgres database.
Respects rate limits (45 requests/minute) and handles errors gracefully.
"""

import json
import time
import sys
import os
from datetime import datetime
from typing import List, Dict, Optional
import requests
import psycopg2
from psycopg2.extras import Json
from ratelimit import limits, sleep_and_retry
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Load configuration
with open("config.json", "r") as f:
    config = json.load(f)

API_BASE_URL = config["api"]["base_url"]
RATE_LIMIT = config["api"]["rate_limit_per_minute"]
MIN_DATE = config["api"]["min_patent_date"]
DB_CONFIG = config["database"]
API_KEY = os.getenv("PATENTSVIEW_API_KEY")

if not API_KEY:
    print("ERROR: PATENTSVIEW_API_KEY not found in .env file")
    sys.exit(1)

# Rate limiting decorator - 45 calls per minute
CALLS_PER_MINUTE = RATE_LIMIT
ONE_MINUTE = 60


@sleep_and_retry
@limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
def rate_limited_request(url: str, params: Optional[Dict] = None) -> requests.Response:
    """Make a rate-limited API request."""
    headers = {"X-Api-Key": API_KEY}
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response


def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
    )


def search_patents(query: str, max_results: int = 100) -> List[Dict]:
    """
    Search for patents matching the query.

    Args:
        query: Search query text
        max_results: Maximum number of patents to retrieve

    Returns:
        List of patent metadata dictionaries
    """
    print(f"  Searching for patents matching '{query}'...")

    # Build API query
    api_query = {
        "_and": [
            {"_text_phrase": {"patent_title": query}},
            {"_gte": {"patent_date": MIN_DATE}},
        ]
    }

    fields = [
        "patent_id",
        "patent_title",
        "patent_date",
        "assignees",
        "cpc_current",
        "inventors",
        "wipo",
    ]

    options = {
        "size": min(max_results, 1000),  # API max is 1000 per request
        "page": 1,
    }

    url = f"{API_BASE_URL}/patent/"
    params = {
        "q": json.dumps(api_query),
        "f": json.dumps(fields),
        "o": json.dumps(options),
    }

    try:
        response = rate_limited_request(url, params)
        data = response.json()

        if data.get("error", True):
            print(f"  ⚠️  API returned error: {data}")
            return []

        patents = data.get("patents", [])
        total_hits = data.get("total_hits", 0)

        print(f"  ✓ Found {len(patents)} patents (total matches: {total_hits})")
        return patents

    except requests.exceptions.RequestException as e:
        print(f"  ✗ Error searching patents: {e}")
        return []


def fetch_patent_summary(patent_id: str) -> Optional[str]:
    """
    Fetch summary text for a specific patent.

    Args:
        patent_id: Patent ID

    Returns:
        Summary text or None if not available
    """
    url = f"{API_BASE_URL}/g_brf_sum_text/"
    params = {"q": json.dumps({"patent_id": patent_id})}

    try:
        response = rate_limited_request(url, params)
        data = response.json()

        if data.get("error", True) or not data.get("g_brf_sum_texts"):
            return None

        summary_text = data["g_brf_sum_texts"][0].get("summary_text")
        return summary_text

    except requests.exceptions.RequestException as e:
        print(f"    ⚠️  Error fetching summary for {patent_id}: {e}")
        return None


def extract_patent_metadata(patent: Dict) -> Dict:
    """Extract relevant metadata from patent API response."""
    # Get first assignee info
    assignees = patent.get("assignees", [])
    first_assignee = assignees[0] if assignees else {}

    # Get CPC groups
    cpc_groups = [
        cpc.get("cpc_group_id")
        for cpc in patent.get("cpc_current", [])
        if cpc.get("cpc_group_id")
    ]

    # Get WIPO field
    wipo_fields = patent.get("wipo", [])
    wipo_field_id = wipo_fields[0].get("wipo_field_id") if wipo_fields else None

    # Get inventor info
    inventors = patent.get("inventors", [])
    inventor_names = [
        f"{inv.get('inventor_name_first', '')} {inv.get('inventor_name_last', '')}".strip()
        for inv in inventors
    ]

    return {
        "patent_id": patent.get("patent_id"),
        "patent_title": patent.get("patent_title"),
        "patent_date": patent.get("patent_date"),
        "assignee_organization": first_assignee.get("assignee_organization"),
        "assignee_country": first_assignee.get("assignee_country"),
        "assignee_type": first_assignee.get("assignee_type"),
        "cpc_groups": cpc_groups,
        "wipo_field_id": wipo_field_id,
        "inventor_count": len(inventors),
        "inventor_names": inventor_names,
        "raw_data": patent,
    }


def insert_patent(cursor, patent_data: Dict, search_topic: str):
    """Insert patent into database."""
    sql = """
        INSERT INTO patents (
            patent_id, patent_title, patent_date, summary_text,
            assignee_organization, assignee_country, assignee_type,
            cpc_groups, wipo_field_id, inventor_count, inventor_names,
            raw_data, search_topic
        ) VALUES (
            %(patent_id)s, %(patent_title)s, %(patent_date)s, %(summary_text)s,
            %(assignee_organization)s, %(assignee_country)s, %(assignee_type)s,
            %(cpc_groups)s, %(wipo_field_id)s, %(inventor_count)s, %(inventor_names)s,
            %(raw_data)s, %(search_topic)s
        )
        ON CONFLICT (patent_id) DO UPDATE SET
            summary_text = EXCLUDED.summary_text,
            search_topic = EXCLUDED.search_topic
    """

    # Convert lists to JSON
    patent_data["cpc_groups"] = Json(patent_data["cpc_groups"])
    patent_data["inventor_names"] = Json(patent_data["inventor_names"])
    patent_data["raw_data"] = Json(patent_data["raw_data"])
    patent_data["search_topic"] = search_topic

    cursor.execute(sql, patent_data)


def process_topic(topic_config: Dict, conn):
    """Process a single search topic."""
    topic_name = topic_config["name"]
    query = topic_config["query"]
    max_patents = topic_config["max_patents"]

    print(f"\n{'=' * 60}")
    print(f"Processing topic: {topic_name}")
    print(f"Query: '{query}' | Max patents: {max_patents}")
    print(f"{'=' * 60}")

    # Search for patents
    patents = search_patents(query, max_patents)

    if not patents:
        print(f"  No patents found for '{query}'")
        return 0

    # Process each patent
    cursor = conn.cursor()
    inserted_count = 0

    for i, patent in enumerate(patents, 1):
        patent_id = patent.get("patent_id")
        patent_title = patent.get("patent_title", "No title")

        print(f"  [{i}/{len(patents)}] Processing {patent_id}: {patent_title[:60]}...")

        # Extract metadata
        patent_data = extract_patent_metadata(patent)

        # Fetch summary (this respects rate limiting)
        print(f"    Fetching summary...")
        summary_text = fetch_patent_summary(patent_id)
        patent_data["summary_text"] = summary_text

        if summary_text:
            print(f"    ✓ Summary fetched ({len(summary_text)} chars)")
        else:
            print(f"    ⚠️  No summary available")

        # Insert into database
        try:
            insert_patent(cursor, patent_data, topic_name)
            conn.commit()
            inserted_count += 1
            print(f"    ✓ Inserted into database")
        except Exception as e:
            conn.rollback()
            print(f"    ✗ Database error: {e}")

    cursor.close()
    print(
        f"\n✓ Topic '{topic_name}' complete: {inserted_count}/{len(patents)} patents inserted"
    )
    return inserted_count


def main():
    """Main seeding process."""
    print("=" * 70)
    print("PATENT DATABASE SEEDING SCRIPT")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Rate limit: {RATE_LIMIT} requests/minute")
    print(f"Topics to process: {len(config['search_topics'])}")

    # Connect to database
    try:
        conn = get_db_connection()
        print("✓ Database connection established")
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        sys.exit(1)

    # Process each topic
    total_inserted = 0
    start_time = time.time()

    for topic in config["search_topics"]:
        inserted = process_topic(topic, conn)
        total_inserted += inserted

    # Close database connection
    conn.close()

    # Summary
    elapsed_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("SEEDING COMPLETE")
    print("=" * 70)
    print(f"Total patents inserted: {total_inserted}")
    print(f"Time elapsed: {elapsed_time / 60:.1f} minutes")
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
