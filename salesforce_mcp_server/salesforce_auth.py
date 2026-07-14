"""
salesforce_mcp_server/salesforce_auth.py

Salesforce JWT Bearer flow — certificate-based, no shared client secret.

Setup required in the Salesforce org (see plan doc):
  1. Generate a self-signed cert + private key.
  2. Upload the cert to the Connected App's "Digital Signature" setting,
     enable the JWT Bearer flow on that Connected App.
  3. Grant the integration user (JWT `sub`) read access across every
     rep's opportunities — this is an org-wide integration user, not a
     per-rep credential.

Env vars:
  SALESFORCE_JWT_CLIENT_ID     — Connected App consumer key (JWT `iss`)
  SALESFORCE_JWT_SUBJECT       — integration user's username (JWT `sub`)
  SALESFORCE_JWT_PRIVATE_KEY   — PEM-encoded private key, injected via
                                 Secret Manager at deploy time — never
                                 committed or hardcoded
  SALESFORCE_JWT_AUDIENCE      — defaults to https://login.salesforce.com
                                 (use https://test.salesforce.com for a sandbox)
  SALESFORCE_TOKEN_URL         — defaults to Salesforce's standard token
                                 endpoint
"""

import os
import time

import httpx
import jwt as pyjwt

_session_cache: dict = {"access_token": None, "instance_url": None, "expires_at": 0}

# Salesforce doesn't return a reliable expires_in for this grant — fall
# back to a conservative TTL and just re-mint a fresh JWT when it lapses.
_DEFAULT_SESSION_TTL_SECONDS = 25 * 60


def _build_jwt_assertion() -> str:
    # Secret Manager values can pick up a trailing CRLF/whitespace depending
    # on how the secret was originally created (e.g. `echo` piped into
    # `gcloud secrets create`) — confirmed directly: a trailing \r\n on
    # SALESFORCE_JWT_CLIENT_ID silently became part of the JWT `iss` claim,
    # causing Salesforce to reject it with "invalid_client_id" even though
    # the value looked identical when printed. .strip() on both id fields
    # is a no-op for an already-clean value.
    client_id = os.environ["SALESFORCE_JWT_CLIENT_ID"].strip()
    subject = os.environ["SALESFORCE_JWT_SUBJECT"].strip()
    # Deployment env vars/secrets commonly flatten a multi-line PEM into a
    # single line with literal "\n" sequences instead of real line breaks
    # (e.g. pasting into a Cloud Run env var field) — PyJWT/cryptography
    # can't parse that as PEM at all, so normalize it back to real newlines.
    # A no-op for a private key that already has real newlines.
    private_key = os.environ["SALESFORCE_JWT_PRIVATE_KEY"].replace("\\n", "\n")
    audience = os.environ.get("SALESFORCE_JWT_AUDIENCE",  "https://login.salesforce.com").strip()

    now = int(time.time())
    claims = {
        "iss": client_id,
        "sub": subject,
        "aud": audience,
        "exp": now + 180,  # short-lived assertion, per JWT Bearer spec convention
    }
    return pyjwt.encode(claims, private_key, algorithm="RS256")


async def get_salesforce_session() -> tuple[str, str]:
    """
    Returns (access_token, instance_url), cached until close to expiry.
    instance_url is org-specific and must be used as the base for all
    subsequent REST/SOQL calls — not a generic Salesforce host.
    """
    now = time.time()
    if _session_cache["access_token"] and now < _session_cache["expires_at"]:
        return _session_cache["access_token"], _session_cache["instance_url"]

    token_url = os.environ.get("SALESFORCE_TOKEN_URL", "https://login.salesforce.com/services/oauth2/token")
    assertion = _build_jwt_assertion()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        if response.is_error:
            # Salesforce's error body (e.g. {"error": "...", "error_description": "..."})
            # is far more useful than raise_for_status()'s generic message —
            # surface it directly rather than losing it.
            raise RuntimeError(
                f"Salesforce token exchange failed ({response.status_code}): {response.text}"
            )
        payload = response.json()

    _session_cache["access_token"] = payload["access_token"]
    _session_cache["instance_url"] = payload["instance_url"]
    _session_cache["expires_at"] = now + _DEFAULT_SESSION_TTL_SECONDS

    return _session_cache["access_token"], _session_cache["instance_url"]
