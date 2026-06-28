"""SSO session isolation — user A must not be able to access user B's session."""
import pytest
from unittest.mock import patch, MagicMock
import sso_manager


def _make_boto3_mocks():
    """Return mocked boto3 OIDC client that simulates a successful device auth start."""
    oidc_mock = MagicMock()
    oidc_mock.register_client.return_value = {
        "clientId": "fake-client-id",
        "clientSecret": "fake-client-secret",
    }
    oidc_mock.start_device_authorization.return_value = {
        "deviceCode": "fake-device-code",
        "userCode": "ABCD-1234",
        "verificationUri": "https://device.sso.us-east-1.amazonaws.com",
        "verificationUriComplete": "https://device.sso.us-east-1.amazonaws.com?user_code=ABCD-1234",
        "expiresIn": 600,
        "interval": 5,
    }
    return oidc_mock


@pytest.mark.asyncio
async def test_poll_another_users_session_is_denied():
    """poll_sso_token must return an error when called with a different user_id."""
    sso_manager._sso_sessions.clear()

    with patch("boto3.client", return_value=_make_boto3_mocks()):
        result = sso_manager.start_sso_login(
            start_url="https://my-org.awsapps.com/start",
            region="us-east-1",
            user_id=1,
        )
    session_id = result["session_id"]

    # user 2 tries to poll user 1's session
    poll_result = sso_manager.poll_sso_token(session_id, user_id=2)
    assert poll_result["status"] == "error"
    assert "denied" in poll_result["message"].lower() or "another user" in poll_result["message"].lower()

    # user 1 can poll their own session without error (status will be "pending")
    poll_result_owner = sso_manager.poll_sso_token(session_id, user_id=1)
    assert poll_result_owner["status"] in ("pending", "authorized", "expired", "error")
    # Crucially, it must NOT be the "access denied" error
    if poll_result_owner["status"] == "error":
        assert "denied" not in poll_result_owner["message"].lower()


@pytest.mark.asyncio
async def test_list_accounts_another_users_session_raises():
    """list_sso_accounts must raise PermissionError for a cross-user access attempt."""
    sso_manager._sso_sessions.clear()

    with patch("boto3.client", return_value=_make_boto3_mocks()):
        result = sso_manager.start_sso_login(
            start_url="https://my-org.awsapps.com/start",
            region="us-east-1",
            user_id=10,
        )
    session_id = result["session_id"]

    with pytest.raises(PermissionError):
        sso_manager.list_sso_accounts(session_id, user_id=99)
