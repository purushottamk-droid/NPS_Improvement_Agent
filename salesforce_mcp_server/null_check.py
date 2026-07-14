"""
salesforce_mcp_server/null_check.py

Pulls a batch of real Opportunity records and reports, per field, how many
are null vs populated — across all fields we currently use PLUS the two
alternative candidates (ARR__c, Next_Step__c) still undecided in FIELD_MAP.
Settles both "which field is actually populated" questions and shows
whether the missing Account on the single-record pull was a one-off or a
pattern.

Run from the repo root:
    python -m salesforce_mcp_server.null_check
"""

import asyncio

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .salesforce_auth import get_salesforce_session
from .soql import FIELD_MAP

SALESFORCE_API_VERSION = "v60.0"
SAMPLE_SIZE = 100

_MISSING_FIELDS = {"account_segment", "discount_pct", "days_open", "current_stage_duration_days"}

# clean_name -> field path, plus the two undecided alternative candidates
FIELDS_TO_CHECK = {k: v for k, v in FIELD_MAP.items() if k not in _MISSING_FIELDS}
FIELDS_TO_CHECK["deal_value_arr__ARR__c_alt"] = "ARR__c"
FIELDS_TO_CHECK["next_step__Next_Step__c_alt"] = "Next_Step__c"


def _extract(record: dict, field_path: str):
    value = record
    for part in field_path.split("."):
        if value is None:
            return None
        value = value.get(part)
    return value


async def main():
    access_token, instance_url = await get_salesforce_session()

    fields = ", ".join(sorted(set(FIELDS_TO_CHECK.values())))
    soql = f"SELECT {fields} FROM Opportunity LIMIT {SAMPLE_SIZE}"

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
    total = len(records)
    print(f"Sampled {total} Opportunity record(s) (org total may be larger — query has no filter/order).\n")

    if total == 0:
        print("No records returned — nothing to check.")
        return

    print(f"{'Field':<38} {'Non-null':>10} {'Null':>8} {'% null':>8}")
    print("-" * 68)

    for clean_name, api_field in FIELDS_TO_CHECK.items():
        non_null = sum(1 for r in records if _extract(r, api_field) is not None)
        null_count = total - non_null
        pct_null = round(null_count / total * 100, 1)
        flag = "  <-- ALL NULL" if non_null == 0 else ("  <-- mostly null" if pct_null >= 80 else "")
        print(f"{clean_name:<38} {non_null:>10} {null_count:>8} {pct_null:>7}%{flag}")


if __name__ == "__main__":
    asyncio.run(main())
