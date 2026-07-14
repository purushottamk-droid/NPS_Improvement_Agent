"""
salesforce_mcp_server/soql.py

SOQL query construction + response-record parsing for the two tools this
server exposes. FIELD_MAP is the single place mapping our clean field
names to real Salesforce API field names — verified against this org's
actual schema via verify_field_map.py. Four fields have no backing field
anywhere in this org (see the module-level note below FIELD_MAP) and two
have a second plausible candidate field — both flagged inline.

opportunity_id maps to the custom Opportunity_ID__c field, NOT the
Salesforce record Id — Gong's Gong_Calls_Data.OPPORTUNITY_ID joins on that
external-ID field instead, confirmed against real data.

All rep-scoped queries (opportunities, attainment) filter on
Sales_Rep_Name__c, not OwnerId — every Opportunity in this org shares one
OwnerId (a shared/integration user), so OwnerId can't identify an
individual rep. OwnerId is still kept in FIELD_MAP (as owner_id) purely so
callers can recover a real, valid Salesforce User Id for Task-assignment
purposes — Sales_Rep_Name__c has no corresponding Salesforce User record.

Relationship fields (e.g. "Account.Name") come back from Salesforce's
REST query API as NESTED objects, not flat dotted keys — parse_opportunity_record
below walks the dotted path to handle that.
"""

# clean_name -> Salesforce API field path (dotted for relationship traversal)
#
# NOTE — 4 fields below don't exist anywhere in this org's schema (checked
# both standard and custom fields on Opportunity/Account via describe):
# account_segment, discount_pct, days_open, current_stage_duration_days.
# Kept mapped to a (nonexistent) field name as a placeholder — the SOQL
# built from these will error until this is resolved. Options: drop them
# from the output entirely, or confirm the data lives somewhere else.
FIELD_MAP = {
    "opportunity_id":               "Opportunity_ID__c",               # NOT the Salesforce record Id — Gong's Gong_Calls_Data.OPPORTUNITY_ID joins on this external-ID custom field instead, confirmed against real data (Id 006fj00000HU2x4AAD has Opportunity_ID__c 006DMO000000000100200, which matches 5 real Gong call rows)
    "opportunity_name":              "Name",
    "account_id":                    "AccountId",
    "account_name":                  "Account.Name",
    "industry":                      "Account.Industry",
    "account_segment":               "Account.Segment__c",              # NOT FOUND — no such field in this org
    "opportunity_type":              "Type",
    "current_stage":                 "StageName",
    "forecast_category":             "ForecastCategoryName",
    "deal_value_arr":                "ARR__c",                          # confirmed via null_check.py — Amount is 100% null in this org, ARR__c is 100% populated
    "discount_pct":                  "Discount__c",                     # NOT FOUND — no such field in this org
    "created_date":                  "CreatedDate",
    "close_date_target":             "CloseDate",
    "days_open":                     "Days_in_Pipeline__c",             # NOT FOUND — no such field in this org
    "current_stage_duration_days":   "Days_Since_Last_Activity__c",     # substitute — real Days_in_Stage-equivalent field is 100% null in this org, using Days Since Last Activity as the closest available proxy per user direction
    "days_since_last_touch":         "Days_Since_Last_Activity__c",     # confirmed
    "next_step":                     "Next_Step__c",                   # confirmed via null_check.py — NextStep is 100% null in this org, Next_Step__c is 100% populated
    "risks":                         "Risks__c",                       # confirmed
    "cbi_raw_text":                  "CBIs__c",                        # confirmed
    "opportunity_manager_notes":     "Manager_Notes__c",               # confirmed
    "sales_rep_name":                "Sales_Rep_Name__c",              # confirmed — Owner.Name and Sales_Rep_Name__c both 100% populated but disagree on every sampled record; Owner.Name is just the Salesforce login that owns the record (often a shared/admin account), Sales_Rep_Name__c is the actual rep this pipeline is about
    "opportunity_previous_solution": "Previous_Solution__c",           # confirmed
    "contact_name":                  "Contact_Name__c",                # confirmed
    "contact_title":                 "Contact_Title__c",               # confirmed
    "is_won":                        "IsWon",
    "is_closed":                     "IsClosed",
    "owner_id":                      "OwnerId",                        # NOT usable for per-rep scoping — every Opportunity in this org shares one OwnerId (a shared/integration user). Kept here only so callers can recover a real, valid Salesforce User Id for Task-assignment purposes (see create_task) — Sales_Rep_Name__c has no corresponding Salesforce User record to assign Tasks to instead.
}

CASE_FIELD_MAP = {
    "case_id":                    "Case_ID__c",
    "case_number":                "Case_Number__c",
    "account_id":                 "Account_ID__c",
    "account_name":               "Account_Name__c",
    "opportunity_id":              "Opportunity_ID__c",
    "opportunity_name":            "Opportunity_Name__c",
    "case_type":                   "Case_Type__c",
    "product_area":                "Product_Area__c",
    "subject":                     "Subject__c",
    "description":                 "Description__c",
    "priority":                    "Priority__c",
    "severity":                    "Severity__c",
    "status":                      "Status__c",
    "reason":                      "Reason__c",
    "created_date":                "Created_Date__c",
    "first_response_date":         "First_Response_Date__c",
    "last_interaction_date":       "Last_Interaction_Date__c",
    "closed_date":                 "Closed_Date__c",
    "is_closed":                   "Is_Closed__c",
    "is_escalated":                "Is_Escalated__c",
    "escalation_level":            "Escalation_Level__c",
    "root_cause":                  "Root_Cause__c",
    "resolution_summary":          "Resolution_Summary__c",
    "customer_sentiment":          "Customer_Sentiment__c",
    "customer_health":             "Customer_Health__c",
    "nps_risk_level":              "NPS_Risk_Level__c",
    "nps_risk_reason":             "NPS_Risk_Reason__c",
    "recommended_agent_action":    "Recommended_Agent_Action__c",
    "customer_success_manager":    "Customer_Success_Manager__c",
    "case_owner":                  "Case_Owner__c",
    "sales_rep_name":              "Sales_Rep_Name__c",
}

def build_cases_by_account_soql(account_id: str) -> str:
    fields = ", ".join(sorted(set(CASE_FIELD_MAP.values())))
    safe_account_id = _escape_soql_string(account_id)
    return f"SELECT {fields} FROM CASE__c WHERE Account_ID__c = '{safe_account_id}'"


def parse_case_record(record: dict) -> dict:
    return {clean_name: _extract(record, api_field) for clean_name, api_field in CASE_FIELD_MAP.items()}
# Only needed for the WHERE clause itself, not part of the returned shape.
# OwnerId is NOT usable for per-rep scoping — every Opportunity in this
# org shares one OwnerId (a shared/integration user) — so the rep-scoped
# builders below filter on Sales_Rep_Name__c instead, the real per-rep field.
_REP_NAME_FIELD = "Sales_Rep_Name__c"

# clean_names with no backing field in this org — Salesforce rejects the
# ENTIRE query if the SELECT list references a field that doesn't exist
# (confirmed directly: a real query against this org 400'd until these
# were excluded), so these must never appear in a SELECT clause. Downstream
# code still gets these keys via parse_opportunity_record, just always None.
KNOWN_MISSING_FIELDS = {"account_segment", "discount_pct", "days_open"}


def _queryable_fields() -> set[str]:
    return {v for k, v in FIELD_MAP.items() if k not in KNOWN_MISSING_FIELDS}


def _escape_soql_string(value: str) -> str:
    """Minimal SOQL string escaping — Salesforce's REST query endpoint takes
    a raw query string, not parameterized queries, so any interpolated
    value needs its quotes/backslashes escaped by hand."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_opportunities_by_rep_name_soql(rep_name: str) -> str:
    """
    Scoped by Sales_Rep_Name__c, not OwnerId — every Opportunity in this org
    shares one OwnerId (a shared/integration user), so OwnerId can't
    distinguish individual reps. Sales_Rep_Name__c is the only field that
    actually does.
    """
    fields = ", ".join(sorted(_queryable_fields()))
    safe_rep_name = _escape_soql_string(rep_name)
    return f"SELECT {fields} FROM Opportunity WHERE {_REP_NAME_FIELD} = '{safe_rep_name}'"


def build_opportunities_by_account_soql(account_id: str) -> str:
    """
    Every opportunity on this account, regardless of owner or open/closed
    status — used for expansion-whitespace detection (does a Migration/
    Upsell/Cross Sell opportunity exist anywhere for this account), which
    is a different question than "this rep's own open pipeline."
    """
    fields = ", ".join(sorted(_queryable_fields()))
    safe_account_id = _escape_soql_string(account_id)
    return f"SELECT {fields} FROM Opportunity WHERE AccountId = '{safe_account_id}'"


def build_stage_benchmark_soql() -> str:
    stage_field = FIELD_MAP["current_stage"]
    duration_field = FIELD_MAP["current_stage_duration_days"]
    won_field = FIELD_MAP["is_won"]
    return (
        f"SELECT {stage_field} stage, AVG({duration_field}) avgDays "
        f"FROM Opportunity "
        f"WHERE {won_field} = true AND {duration_field} != null "
        f"GROUP BY {stage_field}"
    )


def build_attainment_current_month_soql(rep_name: str) -> str:
    """
    Closed-won ARR for this rep, CloseDate in the current calendar month.
    Scoped by Sales_Rep_Name__c, not OwnerId — see build_opportunities_by_rep_name_soql.

    NOTE: SOQL's SUM() only accepts a plain field reference — there is no
    SUM(CASE WHEN ...) construct in SOQL (unlike BigQuery/ANSI SQL), so the
    single conditional-aggregation query this replaces
    (_fetch_salesforce_attainment_sync) has to become two separate
    aggregate queries here, each filtered by a SOQL date literal
    (THIS_MONTH) instead of a CASE expression inside the SUM.
    """
    arr_field = FIELD_MAP["deal_value_arr"]
    close_date_field = FIELD_MAP["close_date_target"]
    won_field = FIELD_MAP["is_won"]
    safe_rep_name = _escape_soql_string(rep_name)
    return (
        f"SELECT SUM({arr_field}) closedWonArr "
        f"FROM Opportunity "
        f"WHERE {_REP_NAME_FIELD} = '{safe_rep_name}' "
        f"AND {won_field} = true "
        f"AND {close_date_field} = THIS_MONTH"
    )


def build_attainment_trailing_3_months_soql(rep_name: str) -> str:
    """
    Closed-won ARR for this rep, CloseDate within the trailing 3 calendar
    months INCLUDING the current month — matching the original BigQuery
    filter (`CloseDate >= DATE_TRUNC(DATE_SUB(CURRENT_DATE(), INTERVAL 3
    MONTH), MONTH)`, i.e. 3 months back through today). Scoped by
    Sales_Rep_Name__c, not OwnerId — see build_opportunities_by_rep_name_soql.

    NOTE: SOQL's LAST_N_MONTHS:3 date literal starts at the beginning of
    the *previous* month and does NOT include the current month, so on its
    own it would under-count relative to the original logic. THIS_MONTH is
    OR'd in to restore that inclusive range. See
    build_attainment_current_month_soql for why this is a second, separate
    query rather than one conditional-aggregation query.
    """
    arr_field = FIELD_MAP["deal_value_arr"]
    close_date_field = FIELD_MAP["close_date_target"]
    won_field = FIELD_MAP["is_won"]
    safe_rep_name = _escape_soql_string(rep_name)
    return (
        f"SELECT SUM({arr_field}) closedWonArr "
        f"FROM Opportunity "
        f"WHERE {_REP_NAME_FIELD} = '{safe_rep_name}' "
        f"AND {won_field} = true "
        f"AND ({close_date_field} = LAST_N_MONTHS:3 OR {close_date_field} = THIS_MONTH)"
    )


def _extract(record: dict, field_path: str):
    """Walk a dotted relationship path (e.g. 'Account.Name') through the
    nested dicts Salesforce's REST API returns for related objects."""
    value = record
    for part in field_path.split("."):
        if value is None:
            return None
        value = value.get(part)
    return value


def parse_opportunity_record(record: dict) -> dict:
    """Map one raw Salesforce query record into our clean field names."""
    return {clean_name: _extract(record, api_field) for clean_name, api_field in FIELD_MAP.items()}
