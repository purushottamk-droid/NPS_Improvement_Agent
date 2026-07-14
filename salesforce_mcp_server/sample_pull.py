"""
salesforce_mcp_server/sample_pull.py

One-off script: pull a single real Opportunity record and print it, both
raw and normalized through parse_opportunity_record — using only the
fields confirmed to exist (verify_field_map.py flagged 4 that don't).
Useful for sanity-checking the shape of real data before wiring this into
the actual get_opportunities_by_rep_name tool.

Run from the repo root:
    python -m salesforce_mcp_server.sample_pull
"""

import asyncio
import json

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .salesforce_auth import get_salesforce_session
from .soql import FIELD_MAP, parse_opportunity_record

SALESFORCE_API_VERSION = "v60.0"

# The 4 fields verify_field_map.py confirmed don't exist in this org —
# excluded here so the query actually runs.
_MISSING_FIELDS = {"account_segment", "discount_pct", "days_open", "current_stage_duration_days"}
_QUERYABLE_FIELD_MAP = {k: v for k, v in FIELD_MAP.items() if k not in _MISSING_FIELDS}


async def main():
    access_token, instance_url = await get_salesforce_session()

    fields = ", ".join(sorted(set(_QUERYABLE_FIELD_MAP.values())))
    soql = f"SELECT {fields} FROM Opportunity LIMIT 1"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query",
            params={"q": soql},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.is_error:
            raise RuntimeError(f"Query failed ({response.status_code}): {response.text}")
        payload = response.json()

    records = payload.get("records", [])
    if not records:
        print("Query succeeded but returned zero Opportunity records — org has none, or none match.")
        return

    raw = records[0]
    print("=== RAW Salesforce record ===")
    print(json.dumps(raw, indent=2, default=str))

    # Reuses the real production parsing path — the 4 missing fields will
    # just come back None, since raw won't have those keys at all.
    normalized = parse_opportunity_record(raw)
    print("\n=== Normalized (our clean field names, via parse_opportunity_record) ===")
    print(json.dumps(normalized, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
