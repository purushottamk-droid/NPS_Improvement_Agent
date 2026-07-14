"""
salesforce_mcp_server/describe_case_fields.py

One-off script to pull the REAL field list for the Salesforce Case object
from Salesforce's describe API — same purpose as describe_fields.py did
for Opportunity/Account, but for Case, since the NPS Improvement Agent's
design doc now wants Cases pulled from Salesforce (via MCP), not BigQuery.

Run from the repo root:
    python -m salesforce_mcp_server.describe_case_fields
"""

import asyncio

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from .describe_fields import describe_object, _print_fields

# Keywords to flag as "likely relevant" when scanning custom fields — matched
# loosely against label/field name to help spot Case field-map candidates,
# based on the doc's requested clean_names (status, reason, subject, priority,
# description, is_closed, date_time, opportunity_id, account_id, severity,
# root cause, resolution, customer sentiment, nps risk, etc.)
RELEVANT_KEYWORDS = [
    "status", "reason", "subject", "priority", "description", "severity",
    "escalat", "root cause", "root_cause", "resolution", "sentiment",
    "nps", "risk", "recommended", "csm", "success manager", "owner",
    "opportunity", "account", "sla", "response", "closed", "comment",
]


async def main():
    case_describe = await describe_object("Case")
    _print_fields("Case", case_describe)

    print(f"\n{'=' * 60}")
    print("Cross-reference the fields above against the doc's requested")
    print("Case fields (status, reason, subject, priority, description,")
    print("is_closed, date_time, opportunity_id/account_id) to build a")
    print("CASE_FIELD_MAP, same way FIELD_MAP was built for Opportunity.")


if __name__ == "__main__":
    asyncio.run(main())
