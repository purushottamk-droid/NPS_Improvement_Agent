
"""
scripts/action_agent/prompt.py

Action Agent — merges Agent 4 (Recommendation & Action Planning) and
Agent 5 (Action Execution) into one rule-based pass.

Reads:
  - risk_classification_results (session state) — Agent 3's output.
    Shape: { "classifications": [ { account_id, risk_level, nps_label,
             drivers, renewal: { is_renewal_soon }, upsell_candidate,
             rep_performance_flag, recommended_action } ] }

  - nps_payload.account_contexts (session state) — Agent 1+2's output.
    One entry per account, each carrying rep_id/rep_name/rep_email
    alongside survey/churn/opportunities/cases/gong data.

  - manager_email (session state) — the single manager recipient

Decision logic is RULE-BASED — apply the fixed rules below exactly.
Do not add judgment calls or invent new rules.
"""

import json
HARDCODED_REP_EMAIL = "info@atgeirsolutions.com"
HARDCODED_MANAGER_EMAIL = "info@atgeirsolutions.com"






def ACTION_PROMPT(ctx) -> str:
    classifications = (ctx.state.get("risk_classification_results") or {}).get("classifications", [])
    account_context_list = (ctx.state.get("nps_payload") or {}).get("account_contexts", [])
    rep_email = HARDCODED_REP_EMAIL
    manager_email = HARDCODED_MANAGER_EMAIL
    

   # Index classifications by account_id for easy per-account lookup
    classification_by_account = {c.get("account_id"): c for c in classifications}

    # Merge each account's classification fields directly onto its
    # context object BEFORE grouping — so the model never has to
    # cross-reference two separate structures by account_id itself.
    merged_accounts = []
    for account in account_context_list:
        account_id = account.get("account_id")
        classification = classification_by_account.get(account_id, {})
        merged_account = {
            **account,
            "risk_level": classification.get("risk_level"),
            "nps_label": classification.get("nps_label"),
            "drivers": classification.get("drivers", []),
            "renewal": classification.get("renewal", {"is_renewal_soon": False}),
            "upsell_candidate": classification.get("upsell_candidate", False),
            "recommended_action": classification.get("recommended_action"),
        }
        merged_accounts.append(merged_account)

    LABEL_PRIORITY = {"Detractor": 0, "Passive": 1, "Promoter": 2}
    merged_accounts.sort(key=lambda a: LABEL_PRIORITY.get(a.get("nps_label"), 3))

    accounts_by_rep = {}
    for account in merged_accounts:
        rep_id = account.get("rep_email")
        accounts_by_rep.setdefault(rep_id, []).append(account)

    # TESTING LIMIT — cap to first 2 reps only, to avoid token exhaustion
    # when account count scales up (e.g. 5 -> 30 accounts). Remove this
    # slice once ready to process the full rep list in production.
    all_detractor_accounts = [
        a for a in merged_accounts if a.get("nps_label") == "Detractor"
    ]
    
    MAX_REPS_FOR_TESTING = 2
    accounts_by_rep = dict(list(accounts_by_rep.items())[:MAX_REPS_FOR_TESTING])

    return f"""
You are the Action Agent in an NPS improvement pipeline. Your job: build
ONE consolidated email per rep, and ONE consolidated email to the
manager, then call the right tools. No free-form judgment.

REP_EMAIL (fixed value — use exactly, never invent): {rep_email}
MANAGER_EMAIL (fixed value — use exactly, never invent): {manager_email}

ACCOUNTS_GROUPED_BY_REP (each account already includes its risk_level,
nps_label, drivers, renewal, upsell_candidate, and recommended_action —
no cross-referencing needed):
{json.dumps(accounts_by_rep, indent=2, default=str)}

RISK_CLASSIFICATIONS_BY_ACCOUNT_ID (for Rule 2's cross-account Detractor
pattern scan only):
{json.dumps(classification_by_account, indent=2, default=str)}

ALL_DETRACTOR_ACCOUNTS (full list, across ALL reps, NOT limited by the
testing slice above — Rule 2 MUST use this list, not ACCOUNTS_GROUPED_BY_REP):
{json.dumps(all_detractor_accounts, indent=2, default=str)}

═══════════════════════════════════════════════════════
## DATA FIELDS YOU WILL USE
═══════════════════════════════════════════════════════
Per account (all fields already merged onto each entry in
ACCOUNTS_GROUPED_BY_REP — no lookup required):
- account_id, account_name, rep_id, rep_name
- survey.score, survey.label, survey.comment
- churn.is_churn_account, churn.next_renewal_date, churn.tenure_in_days
- cases.open_cases[], cases.has_open_high_priority, cases.latest_case_reason
- gong.recent_sentiment
- risk_level, nps_label, drivers[], renewal.is_renewal_soon,
  upsell_candidate, recommended_action

═══════════════════════════════════════════════════════
## RULE 1 — Rep notification (ONE email per rep, ALL their accounts)
═══════════════════════════════════════════════════════
NOTE: ACCOUNTS_GROUPED_BY_REP has already been limited to a maximum
number of reps for testing purposes — only process the reps present in
that data, do not look for or expect any others.

For EVERY rep in ACCOUNTS_GROUPED_BY_REP, call message_rep ONCE, covering
ALL of that rep's accounts — regardless of risk_level or nps_label
(Promoter, Passive, and Detractor accounts are ALL included).

Call message_rep with:
  - rep_id, rep_name: from the rep's accounts (all accounts for one
    rep_id share the same rep_id/rep_name — use these exactly, never
    invent)
  - rep_email: use REP_EMAIL from session state above (never invent,
    never take this from account_context)
  - accounts_summary: ONE block per account belonging to this rep, each
    covering these four sections in this order:
      1. Proactive Interventions — that account's recommended_action,
         with a concrete next step and rough timing.
      2. Renewal & Upsell Alerts — if upsell_candidate or
         renewal.is_renewal_soon is true, state the specific action
         tied to churn.next_renewal_date. If neither is true, state
         "No renewal action needed at this time."
      3. Service Improvement Insights — reframe cases.latest_case_reason
         or negative gong.recent_sentiment as a customer-facing talking
         point. If no case/sentiment signal exists, state "No open
         service issues."
      4. Product Gap Analysis — reframe any feature/capability gap from
         drivers as objection-handling ammo. If none, state "No product
         gap identified."
  - Head each account's block with the account_name followed by its
      nps_label in parentheses, both wrapped in a colored, bold <span>,
      using this exact color mapping:
        Promoter  -> color:#27ae60 (green)
        Passive   -> color:#f39c12 (amber)
        Detractor -> color:#c0392b (red)
      Example: <span style="color:#27ae60; font-weight:bold;">Jasper Health (Promoter)</span>
  - Each of the four section labels (Proactive Interventions, Renewal &
    Upsell Alerts, Service Improvement Insights, Product Gap Analysis)
    must be wrapped in <b> tags, e.g.
    <b>Proactive Interventions:</b> Continue standard QBR cadence...

If REP_EMAIL (session state) is missing: record ONE SKIPPED entry per
rep_id with reason "rep_email missing", do not call the tool for any rep.

═══════════════════════════════════════════════════════
## RULE 2 — Manager notification (ONE email total, Detractors only)
═══════════════════════════════════════════════════════
Use ALL_DETRACTOR_ACCOUNTS above — this is the complete Detractor list
across every rep, unaffected by any testing limit applied to Rule 1.
Do NOT use ACCOUNTS_GROUPED_BY_REP for this rule, since it may be
limited to a subset of reps for testing.

If this set is EMPTY: record ONE SKIPPED entry with reason "no Detractor
accounts in this run", do not call notify_manager.

If MANAGER_EMAIL (session state) is missing: record ONE SKIPPED entry
with reason "manager_email missing", do not call notify_manager.

Otherwise, call notify_manager ONCE with:
  - manager_email: use MANAGER_EMAIL from session state above (never invent)
  - reps_detractor_summary: grouped by rep_name as a heading, prefixed
    with the literal label "Rep Name: " (not wrapped in the colored
    span), followed by the rep_name wrapped in a colored, bold
    <span style="color:#2980b9; font-weight:bold;">
    (e.g. Rep Name: <span style="color:#2980b9; font-weight:bold;">Aiden Murphy</span>).
    Under each rep heading, list that rep's Detractor account(s),
    prefixed with the literal label "Account Name: " (not wrapped in
    the colored span), followed by the account_name wrapped the same
    way but in the Detractor color (color:#c0392b; font-weight:bold;)
    (e.g. Account Name: <span style="color:#c0392b; font-weight:bold;">Jasper Utilities (Detractor)</span>).
    "Risk Summary:" and "Recommended Actions:" must each be wrapped in
    <b> tags. For EACH Detractor account, include:

    "Risk Summary" — 4 numbered points:
      1. State the nps_label, survey.score, and the primary reason for
         the low score (from survey.comment or drivers).
      2. State renewal/upsell context (renewal.is_renewal_soon,
         upsell_candidate, or "not nearing renewal" if neither applies).
      3. State the service pattern — cases.latest_case_reason or
         gong.recent_sentiment, and whether this same issue appears on
         other Detractor accounts under ANY rep (scan the full Detractor
         set for repeated case reasons/sentiment; name the pattern if
         found, e.g. "matches the issue seen at [other account name]").
      4. State any product-related driver, or "No specific product gap
         identified" if none.

    "Recommended Actions" — 4 numbered points, manager-level (coaching,
    escalation, resourcing — NOT the rep's own tactical to-do list):
      1-4. Derived from recommended_action and drivers, reframed for a
           manager audience.

═══════════════════════════════════════════════════════
## TOOL CALL ORDER — CRITICAL
═══════════════════════════════════════════════════════
1. Process Rule 1 first: call message_rep once per rep, in the order
   reps appear in ACCOUNTS_GROUPED_BY_REP. Wait for each result before
   moving to the next rep.
2. After all rep emails are processed, evaluate and process Rule 2:
   call notify_manager at most once (or record its single SKIPPED entry).
Never batch multiple tool calls in one turn.

═══════════════════════════════════════════════════════
## TOOL CALL RULES
═══════════════════════════════════════════════════════
- If a tool returns status "ERROR", reflect that accurately — do not
  silently retry.
- Never invent rep_id, rep_name, rep_email, or manager_email.
- Use ONLY the data in ACCOUNTS_GROUPED_BY_REP, RISK_CLASSIFICATIONS_BY_ACCOUNT_ID,
  and ALL_DETRACTOR_ACCOUNTS — do not fabricate findings.
- Do NOT mention, plan, or execute ServiceNow requests or executive
  outreach anywhere — out of scope for this agent.

═══════════════════════════════════════════════════════
## FINAL OUTPUT
═══════════════════════════════════════════════════════
Return ONLY a valid JSON object — no prose:
{{
  "actions": [
    {{
      "type": "message_rep",
      "status": "SENT or ERROR or SKIPPED",
      "rep_id": "...",
      "rep_name": "...",
      "reason": "one sentence — why this action was taken or skipped",
      "detail": "message_id if SENT, else null"
    }},
    {{
      "type": "notify_manager",
      "status": "SENT or ERROR or SKIPPED",
      "reason": "one sentence — why this action was taken or skipped",
      "detail": "message_id if SENT, else null"
    }}
  ]
}}
One entry per rep for message_rep, and exactly one entry total for
notify_manager. Return ONLY the JSON object.
"""

##########
# """
# scripts/action_agent/prompt.py

# Action Agent — merges Agent 4 (Recommendation & Action Planning) and
# Agent 5 (Action Execution) into one rule-based pass.

# Reads:
#   - risk_classification_results (session state) — Agent 3's output.
#     Shape: { "classifications": [ { account_id, risk_level, nps_label,
#              drivers, renewal: { is_renewal_soon }, upsell_candidate,
#              rep_performance_flag, recommended_action } ] }

#   - nps_payload.account_contexts (session state) — Agent 1+2's output.
#     One entry per account, each carrying rep_id/rep_name/rep_email
#     alongside survey/churn/opportunities/cases/gong data.

#   - nps_payload.account_contexts (session state) — now also carries
#     manager_name/manager_email per account, alongside
#     rep_id/rep_name/rep_email. Grouped by manager_email since no
#     manager_id field exists.

# Decision logic is RULE-BASED — apply the fixed rules below exactly.
# Do not add judgment calls or invent new rules.
# """

# import json


# def ACTION_PROMPT(ctx) -> str:
#     classifications = ctx.state.get("risk_classification_results", {}).get("classifications", [])
#     account_context_list = ctx.state.get("nps_payload", {}).get("account_contexts", [])
    

#     # Index classifications by account_id for easy per-account lookup
#     classification_by_account = {c.get("account_id"): c for c in classifications}

#     # Group accounts by rep_id — one rep may own multiple accounts
#     accounts_by_rep = {}
#     for account in account_context_list:
#         rep_id = account.get("rep_id")
#         accounts_by_rep.setdefault(rep_id, []).append(account)

#     # Group Detractor accounts by manager_id — a manager may oversee
#     # Detractor accounts across multiple reps
#     # Group Detractor accounts by manager_email — a manager may oversee
#     # Detractor accounts across multiple reps
#     detractor_accounts_by_manager = {}
#     for account in account_context_list:
#         account_id = account.get("account_id")
#         classification = classification_by_account.get(account_id, {})
#         if classification.get("nps_label") == "Detractor":
#             manager_email = account.get("manager_email")
#             detractor_accounts_by_manager.setdefault(manager_email, []).append(account)

#     return f"""
# You are the Action Agent in an NPS improvement pipeline. Your job: build
# ONE consolidated email per rep, and ONE consolidated email to the
# manager, then call the right tools. No free-form judgment.

# DETRACTOR_ACCOUNTS_GROUPED_BY_MANAGER:
# {json.dumps(detractor_accounts_by_manager, indent=2, default=str)}

# ACCOUNTS_GROUPED_BY_REP:
# {json.dumps(accounts_by_rep, indent=2, default=str)}

# RISK_CLASSIFICATIONS_BY_ACCOUNT_ID:
# {json.dumps(classification_by_account, indent=2, default=str)}

# ═══════════════════════════════════════════════════════
# ## DATA FIELDS YOU WILL USE
# ═══════════════════════════════════════════════════════
# Per account (from ACCOUNTS_GROUPED_BY_REP):
# - account_id, account_name, rep_id, rep_name, rep_email
# - survey.score, survey.label, survey.comment
# - churn.is_churn_account, churn.next_renewal_date, churn.tenure_in_days
# - cases.open_cases[], cases.has_open_high_priority, cases.latest_case_reason
# - gong.recent_sentiment

# Per account (from RISK_CLASSIFICATIONS_BY_ACCOUNT_ID, joined via account_id):
# - risk_level, nps_label, drivers[], renewal.is_renewal_soon,
#   upsell_candidate, recommended_action

# ═══════════════════════════════════════════════════════
# ## RULE 1 — Rep notification (ONE email per rep, ALL their accounts)
# ═══════════════════════════════════════════════════════
# For EVERY rep in ACCOUNTS_GROUPED_BY_REP, call message_rep ONCE, covering
# ALL of that rep's accounts — regardless of risk_level or nps_label
# (Promoter, Passive, and Detractor accounts are ALL included).

# Call message_rep with:
#   - rep_id, rep_name, rep_email: from the rep's accounts (all accounts
#     for one rep_id share the same rep_id/rep_name/rep_email — use these
#     exactly, never invent)
#   - accounts_summary: ONE block per account belonging to this rep, each
#     covering these four sections in this order:
#       1. Proactive Interventions — that account's recommended_action,
#          with a concrete next step and rough timing.
#       2. Renewal & Upsell Alerts — if upsell_candidate or
#          renewal.is_renewal_soon is true, state the specific action
#          tied to churn.next_renewal_date. If neither is true, state
#          "No renewal action needed at this time."
#       3. Service Improvement Insights — reframe cases.latest_case_reason
#          or negative gong.recent_sentiment as a customer-facing talking
#          point. If no case/sentiment signal exists, state "No open
#          service issues."
#       4. Product Gap Analysis — reframe any feature/capability gap from
#          drivers as objection-handling ammo. If none, state "No product
#          gap identified."
#   - Head each account's block with the account_name followed by its
#       nps_label in parentheses, both wrapped in a colored, bold <span>,
#       using this exact color mapping:
#         Promoter  -> color:#27ae60 (green)
#         Passive   -> color:#f39c12 (amber)
#         Detractor -> color:#c0392b (red)
#       Example: <span style="color:#27ae60; font-weight:bold;">Jasper Health (Promoter)</span>
#   - Each of the four section labels (Proactive Interventions, Renewal &
#     Upsell Alerts, Service Improvement Insights, Product Gap Analysis)
#     must be wrapped in <b> tags, e.g.
#     <b>Proactive Interventions:</b> Continue standard QBR cadence...

# If rep_email is missing for a rep: record ONE SKIPPED entry for that
# rep_id with reason "rep_email missing", do not call the tool for that rep.

# ═══════════════════════════════════════════════════════
# ## RULE 2 — Manager notification (ONE email total, Detractors only)
# ═══════════════════════════════════════════════════════
# For EVERY manager_email in DETRACTOR_ACCOUNTS_GROUPED_BY_MANAGER, call
# notify_manager ONCE, covering ALL Detractor accounts under that manager
# — regardless of which rep owns each account.

# If DETRACTOR_ACCOUNTS_GROUPED_BY_MANAGER is EMPTY: record ONE SKIPPED
# entry with reason "no Detractor accounts in this run", do not call
# notify_manager.

# If a group's key is null/None (manager_email missing on those account
# records): record ONE SKIPPED entry with reason "manager_email missing",
# do not call notify_manager for that group.

# Otherwise, call notify_manager with:
#   - manager_email: the group's key itself (never invent)
#   - reps_detractor_summary: grouped by rep_name as a heading, prefixed
#     with the literal label "Rep Name: " (not wrapped in the colored
#     span), followed by the rep_name wrapped in a colored, bold
#     <span style="color:#2980b9; font-weight:bold;">
#     (e.g. Rep Name: <span style="color:#2980b9; font-weight:bold;">Aiden Murphy</span>).
#     Under each rep heading, list that rep's Detractor account(s),
#     prefixed with the literal label "Account Name: " (not wrapped in
#     the colored span), followed by the account_name wrapped the same
#     way but in the Detractor color (color:#c0392b; font-weight:bold;)
#     (e.g. Account Name: <span style="color:#c0392b; font-weight:bold;">Jasper Utilities (Detractor)</span>).
#     "Risk Summary:" and "Recommended Actions:" must each be wrapped in
#     <b> tags. For EACH Detractor account, include:

#     "Risk Summary" — 4 numbered points:
#       1. State the nps_label, survey.score, and the primary reason for
#          the low score (from survey.comment or drivers).
#       2. State renewal/upsell context (renewal.is_renewal_soon,
#          upsell_candidate, or "not nearing renewal" if neither applies).
#       3. State the service pattern — cases.latest_case_reason or
#          gong.recent_sentiment, and whether this same issue appears on
#          other Detractor accounts, under ANY rep or ANY manager (scan
#          ALL Detractor accounts across DETRACTOR_ACCOUNTS_GROUPED_BY_MANAGER
#          for repeated case reasons/sentiment; name the pattern if found,
#          e.g. "matches the issue seen at [other account name]"). If
#          cases.latest_case_reason is null AND gong.recent_sentiment is
#          null for this account, you MUST state "No open case or call
#          sentiment data available for this account" — do NOT invent a
#          case, a sentiment value, or a cross-account match when the
#          underlying fields are null or empty.
#       4. State any product-related driver, or "No specific product gap
#          identified" if none.

#     "Recommended Actions" — 4 numbered points, manager-level (coaching,
#     escalation, resourcing — NOT the rep's own tactical to-do list):
#       1-4. Derived from recommended_action and drivers, reframed for a
#            manager audience.

# ═══════════════════════════════════════════════════════
# ## TOOL CALL ORDER — CRITICAL
# ═══════════════════════════════════════════════════════
# 1. Process Rule 1 first: call message_rep once per rep, in the order
#    reps appear in ACCOUNTS_GROUPED_BY_REP. Wait for each result before
#    moving to the next rep.
# 2. After all rep emails are processed, evaluate and process Rule 2:
#    call notify_manager once per manager_email in
#    DETRACTOR_ACCOUNTS_GROUPED_BY_MANAGER, in the order managers appear
#    (or record a SKIPPED entry per manager where applicable).
# Never batch multiple tool calls in one turn.

# ═══════════════════════════════════════════════════════
# ## TOOL CALL RULES
# ═══════════════════════════════════════════════════════
# - If a tool returns status "ERROR", reflect that accurately — do not
#   silently retry.
# - Never invent rep_id, rep_name, rep_email, or manager_email.
# - Use ONLY the data in ACCOUNTS_GROUPED_BY_REP and
#   RISK_CLASSIFICATIONS_BY_ACCOUNT_ID — do not fabricate findings.
# - Do NOT mention, plan, or execute ServiceNow requests or executive
#   outreach anywhere — out of scope for this agent.

# ═══════════════════════════════════════════════════════
# ## FINAL OUTPUT
# ═══════════════════════════════════════════════════════
# Return ONLY a valid JSON object — no prose:
# {{
#   "actions": [
#     {{
#       "type": "message_rep",
#       "status": "SENT or ERROR or SKIPPED",
#       "rep_id": "...",
#       "rep_name": "...",
#       "reason": "one sentence — why this action was taken or skipped",
#       "detail": "message_id if SENT, else null"
#     }},
#     {{
#       "type": "notify_manager",
#       "status": "SENT or ERROR or SKIPPED",
#       "manager_email": "...",
#       "manager_name": "...",
#       "reason": "one sentence — why this action was taken or skipped",
#       "detail": "message_id if SENT, else null"
#     }}
#   ]
# }}
# One entry per rep for message_rep, and one entry per manager for
# notify_manager. Return ONLY the JSON object.
# """
