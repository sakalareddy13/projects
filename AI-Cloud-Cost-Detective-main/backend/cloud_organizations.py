import boto3
import configparser
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ─── base session ─────────────────────────────────────────────────────────────

def _base_session() -> boto3.Session:
    """
    Return a boto3 Session for Organizations/SSO mode.
    Uses AWS_PROFILE for SSO, then falls through to the default
    credential chain (instance profile, ECS task role, etc.).
    Static credentials are supplied per-scan via the UI, not here.
    """
    profile = os.getenv("AWS_PROFILE")
    if profile:
        return boto3.Session(profile_name=profile)
    return boto3.Session()


# ─── credentials dataclass ────────────────────────────────────────────────────

@dataclass
class AccountCredentials:
    account_id: str
    account_name: str
    # Exactly one of (access_key/secret_key/session_token) or profile_name will be set
    access_key: str = ""
    secret_key: str = ""
    session_token: str = ""
    profile_name: str = ""   # set when using an SSO/named profile for the management account

    def get_client(self, service: str, region: str):
        if self.profile_name:
            session = boto3.Session(profile_name=self.profile_name)
            return session.client(service, region_name=region)

        if self.access_key:
            return boto3.client(
                service,
                region_name=region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                aws_session_token=self.session_token or None,
            )

        # Fall back to default credential chain
        return boto3.client(service, region_name=region)


# ─── management-account credentials ──────────────────────────────────────────

def get_default_credentials(account_id: str = "", account_name: str = "default") -> AccountCredentials:
    """
    Return credentials for the management account using SSO profiles (Organizations mode).
    Static scan credentials are provided per-scan via the UI, not resolved here.
    """
    profile = os.getenv("AWS_PROFILE")
    if profile:
        return AccountCredentials(
            account_id=account_id,
            account_name=account_name,
            profile_name=profile,
        )
    return AccountCredentials(account_id=account_id, account_name=account_name)


# ─── cross-account role assumption ───────────────────────────────────────────

def assume_role(account_id: str, account_name: str, role_name: str = "CostDetectiveRole") -> Optional[AccountCredentials]:
    """
    Assume a cross-account IAM role from the management account session.
    Works with both SSO profiles and static credentials.
    """
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        sts = _base_session().client("sts")
        assume_kwargs: dict = {
            "RoleArn": role_arn,
            "RoleSessionName": "CostDetectiveSession",
            "DurationSeconds": 3600,
        }
        # Only include ExternalId if explicitly configured (not needed for same-org trust)
        ext_id = os.getenv("AWS_ORGANIZATIONS_EXTERNAL_ID")
        if ext_id:
            assume_kwargs["ExternalId"] = ext_id

        response = sts.assume_role(**assume_kwargs)
        c = response["Credentials"]
        return AccountCredentials(
            account_id=account_id,
            account_name=account_name,
            access_key=c["AccessKeyId"],
            secret_key=c["SecretAccessKey"],
            session_token=c["SessionToken"],
        )
    except Exception as e:
        logger.warning("iam.assume_role.failed", extra={"account_id": account_id, "role_arn": role_arn, "error": str(e)})
        return None


# ─── SSO profile auto-detection ──────────────────────────────────────────────

def _build_sso_profile_map() -> dict:
    """
    Parse ~/.aws/config and return {sso_account_id: profile_name}.
    Prefers profiles with AdministratorAccess; first match wins per account.
    """
    config_path = os.path.expanduser("~/.aws/config")
    if not os.path.exists(config_path):
        return {}

    cfg = configparser.ConfigParser()
    cfg.read(config_path)

    # Two passes: AdministratorAccess profiles first, then anything else
    admin: dict = {}
    other: dict = {}
    for section in cfg.sections():
        account_id = cfg.get(section, "sso_account_id", fallback=None)
        if not account_id:
            continue
        profile_name = section[len("profile "):] if section.startswith("profile ") else section
        role = cfg.get(section, "sso_role_name", fallback="")
        if role == "AdministratorAccess":
            admin.setdefault(account_id, profile_name)
        else:
            other.setdefault(account_id, profile_name)

    merged = {**other, **admin}  # admin wins
    return merged


# ─── account discovery ────────────────────────────────────────────────────────

def load_accounts_from_file(filepath: str = None) -> list[dict]:
    """Load accounts config from cloud_accounts.json."""
    if filepath is None:
        filepath = os.getenv("AWS_ACCOUNTS_FILE", "/app/cloud_accounts.json")
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath) as f:
            data = json.load(f)
        return data.get("accounts", [])
    except Exception as e:
        logger.warning("accounts_file.load_failed", extra={"filepath": filepath, "error": str(e)})
        return []


def get_org_accounts() -> list[dict]:
    """Discover active accounts from AWS Organizations API (management account must have orgs permissions)."""
    try:
        orgs = _base_session().client("organizations")
        paginator = orgs.get_paginator("list_accounts")
        accounts = []
        for page in paginator.paginate():
            for acct in page["Accounts"]:
                if acct["Status"] == "ACTIVE":
                    accounts.append({
                        "account_id": acct["Id"],
                        "name": acct["Name"],
                        "email": acct.get("Email", ""),
                        "role_arn": f"arn:aws:iam::{acct['Id']}:role/CostDetectiveRole",
                    })
        return accounts
    except Exception as e:
        logger.warning("organizations.list_accounts.failed", extra={"error": str(e)})
        return []


# ─── credential resolver ──────────────────────────────────────────────────────

def resolve_scan_credentials(account_ids: list[str] = None, use_organizations: bool = False) -> list[AccountCredentials]:
    """
    Return a list of AccountCredentials to scan.
    - No accounts + no org flag  → scan management account only (single-account mode).
    - account_ids given           → assume role in each specified account.
    - use_organizations=True      → discover all accounts from Organizations API.
    """
    # Identify the management account
    management_id = os.getenv("AWS_MANAGEMENT_ACCOUNT_ID", "")
    try:
        identity = _base_session().client("sts").get_caller_identity()
        management_id = identity.get("Account", management_id)
    except Exception:
        pass

    if not account_ids and not use_organizations:
        return [get_default_credentials(account_id=management_id, account_name="management")]

    # Collect target accounts
    targets: list[dict] = []

    if use_organizations:
        targets = get_org_accounts() or load_accounts_from_file()

    if account_ids:
        file_map = {a["account_id"]: a for a in load_accounts_from_file()}
        targets = []
        for aid in account_ids:
            targets.append(file_map.get(aid) or {
                "account_id": aid,
                "name": aid,
                "role_arn": f"arn:aws:iam::{aid}:role/CostDetectiveRole",
            })

    sso_map = _build_sso_profile_map()

    results: list[AccountCredentials] = []
    for acct in targets:
        acct_id = acct.get("account_id", "")
        acct_name = acct.get("name", acct_id)

        # 1. Explicit profile_name in cloud_accounts.json
        profile = acct.get("profile_name", "")

        # 2. Auto-detected SSO profile from ~/.aws/config
        if not profile:
            profile = sso_map.get(acct_id, "")

        if profile:
            results.append(AccountCredentials(
                account_id=acct_id,
                account_name=acct_name,
                profile_name=profile,
            ))
        elif acct_id == management_id:
            results.append(get_default_credentials(account_id=acct_id, account_name=acct_name))
        else:
            # Last resort: try cross-account role assumption
            creds = assume_role(acct_id, acct_name)
            if creds:
                results.append(creds)
            else:
                logger.warning("account.not_accessible", extra={"account_id": acct_id, "reason": "no SSO profile and role assumption failed"})

    return results
