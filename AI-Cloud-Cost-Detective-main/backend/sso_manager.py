"""AWS SSO device authorization flow — per-user browser-based authentication."""

import logging
import time
import uuid

import boto3

logger = logging.getLogger(__name__)


# In-memory sessions — cleared on server restart, never written to disk
_sso_sessions: dict[str, dict] = {}


def _verify_session_owner(session_id: str, user_id: int) -> dict:
    """Return session dict if it belongs to user_id; raise RuntimeError otherwise."""
    session = _sso_sessions.get(session_id)
    if not session:
        raise RuntimeError("Session not found. Please start the SSO login again.")
    if session.get("user_id") != user_id:
        raise PermissionError("Access denied — this SSO session belongs to another user.")
    return session


def start_sso_login(start_url: str, region: str, user_id: int) -> dict:
    """
    Register a temporary OIDC client and start the device authorization flow.
    Returns session_id + display info (user_code, verification URLs).
    """
    oidc = boto3.client("sso-oidc", region_name=region)

    client_reg = oidc.register_client(
        clientName="CostDetectiveApp",
        clientType="public",
    )

    device_auth = oidc.start_device_authorization(
        clientId=client_reg["clientId"],
        clientSecret=client_reg["clientSecret"],
        startUrl=start_url,
    )

    session_id = str(uuid.uuid4())
    _sso_sessions[session_id] = {
        "user_id": user_id,
        "client_id": client_reg["clientId"],
        "client_secret": client_reg["clientSecret"],
        "device_code": device_auth["deviceCode"],
        "region": region,
        "start_url": start_url,
        "interval": max(device_auth.get("interval", 5), 5),
        "expires_at": time.time() + device_auth["expiresIn"],
        "access_token": None,
        "status": "pending",
    }

    return {
        "session_id": session_id,
        "user_code": device_auth["userCode"],
        "verification_uri": device_auth["verificationUri"],
        "verification_uri_complete": device_auth["verificationUriComplete"],
        "expires_in": device_auth["expiresIn"],
        "interval": max(device_auth.get("interval", 5), 5),
    }


def poll_sso_token(session_id: str, user_id: int) -> dict:
    """
    Try to exchange the device code for an SSO access token.
    Returns {"status": "pending"|"authorized"|"expired"|"error", "message": "..."}
    """
    try:
        session = _verify_session_owner(session_id, user_id)
    except PermissionError as e:
        return {"status": "error", "message": str(e)}
    except RuntimeError:
        return {"status": "error", "message": "Session not found. Please start the SSO login again."}

    if session["status"] == "authorized":
        return {"status": "authorized"}

    if time.time() > session["expires_at"]:
        session["status"] = "expired"
        return {"status": "expired", "message": "Code expired. Please start the SSO login again."}

    oidc = boto3.client("sso-oidc", region_name=session["region"])
    try:
        token_resp = oidc.create_token(
            clientId=session["client_id"],
            clientSecret=session["client_secret"],
            grantType="urn:ietf:params:oauth:grant-type:device_code",
            deviceCode=session["device_code"],
        )
        session["access_token"] = token_resp["accessToken"]
        session["status"] = "authorized"
        return {"status": "authorized"}

    except oidc.exceptions.AuthorizationPendingException:
        return {"status": "pending"}

    except oidc.exceptions.SlowDownException:
        session["interval"] = min(session["interval"] + 5, 30)
        return {"status": "pending"}

    except oidc.exceptions.ExpiredTokenException:
        session["status"] = "expired"
        return {"status": "expired", "message": "Code expired. Please start the SSO login again."}

    except Exception as e:
        session["status"] = "error"
        logger.error("sso.poll.error", extra={"session_id": session_id, "error": str(e)})
        return {"status": "error", "message": f"Authorization failed: {e}"}


def list_sso_accounts(session_id: str, user_id: int) -> list[dict]:
    """
    List all AWS accounts and their available roles for the authenticated SSO user.
    Raises RuntimeError if the session is not yet authorized.
    """
    session = _verify_session_owner(session_id, user_id)
    if session["status"] != "authorized":
        raise RuntimeError("SSO session not authorized. Please log in first.")

    sso = boto3.client("sso", region_name=session["region"])
    access_token = session["access_token"]
    accounts = []

    try:
        paginator = sso.get_paginator("list_accounts")
        for page in paginator.paginate(accessToken=access_token):
            for acct in page["accountList"]:
                account_id = acct["accountId"]
                account_name = acct.get("accountName", account_id)
                email = acct.get("emailAddress", "")

                roles: list[str] = []
                try:
                    role_pager = sso.get_paginator("list_account_roles")
                    for rp in role_pager.paginate(accountId=account_id, accessToken=access_token):
                        roles.extend(r["roleName"] for r in rp["roleList"])
                except Exception:
                    pass

                accounts.append({
                    "account_id": account_id,
                    "account_name": account_name,
                    "email": email,
                    "roles": roles,
                })
    except Exception as e:
        raise RuntimeError(f"Could not list SSO accounts: {e}")

    return accounts


def get_role_credentials(session_id: str, account_id: str, role_name: str, user_id: int) -> dict:
    """
    Get temporary AWS credentials (access_key, secret_key, session_token)
    for a specific account + role using the SSO access token.
    """
    session = _verify_session_owner(session_id, user_id)
    if session["status"] != "authorized":
        raise RuntimeError("SSO session not authorized.")

    sso = boto3.client("sso", region_name=session["region"])
    try:
        resp = sso.get_role_credentials(
            accountId=account_id,
            roleName=role_name,
            accessToken=session["access_token"],
        )
        creds = resp["roleCredentials"]
        return {
            "access_key": creds["accessKeyId"],
            "secret_key": creds["secretAccessKey"],
            "session_token": creds["sessionToken"],
            "expiration": creds.get("expiration"),
        }
    except Exception as e:
        raise RuntimeError(f"Could not get credentials for {account_id}/{role_name}: {e}")


def cleanup_expired_sessions() -> None:
    """Drop stale/expired sessions from memory."""
    cutoff = time.time() - 3600
    stale = [
        sid for sid, s in list(_sso_sessions.items())
        if s["status"] in ("expired", "error") or s["expires_at"] < cutoff
    ]
    for sid in stale:
        _sso_sessions.pop(sid, None)
