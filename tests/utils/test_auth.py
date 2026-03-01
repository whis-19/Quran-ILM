import pytest
from utils import auth_utils

def test_hash_password():
    h1 = auth_utils.hash_password("MySecurePass123!")
    h2 = auth_utils.hash_password("MySecurePass123!")
    assert type(h1) == str
    assert len(h1) > 0
    assert h1 == h2

def test_validate_password_strength():
    # Weak passwords
    assert auth_utils.validate_password_strength("weak")[0] is False
    assert auth_utils.validate_password_strength("AllUpperNoNumber!")[0] is False
    assert auth_utils.validate_password_strength("WithUpper123")[0] is False # No special
    
    # Strong password
    success, msg = auth_utils.validate_password_strength("Th1sIs!Strong")
    assert success is True

def test_create_user_pending(mock_db_connection):
    success, msg = auth_utils.create_user_pending("test@example.com", "Str0ngPass!@#")
    assert success is True
    
    # Verify in stub
    user = mock_db_connection["users"].find_one({"email": "test@example.com"})
    assert user is not None
    assert user["verified"] is False
    assert "otp" in user
    assert len(user["otp"]) == 6

def test_verify_user_otp(mock_db_connection):
    auth_utils.create_user_pending("verify@example.com", "Str0ngPass!@#")
    user = mock_db_connection["users"].find_one({"email": "verify@example.com"})
    
    # Test valid OTP
    success, msg = auth_utils.verify_user_otp("verify@example.com", user["otp"])
    assert success is True
    
    # Re-fetch from Stub
    user_after = mock_db_connection["users"].find_one({"email": "verify@example.com"})
    assert user_after["verified"] is True
    assert user_after["otp"] is None

def test_authenticate_user(mock_db_connection):
    auth_utils.create_user_pending("auth@example.com", "Str0ngPass!@#")
    user = mock_db_connection["users"].find_one({"email": "auth@example.com"})
    
    # 1. Test Unverified
    success, role, msg = auth_utils.authenticate_user("auth@example.com", "Str0ngPass!@#")
    assert success is False
    assert "not verified" in msg

    # 2. Test Incorrect Password
    auth_utils.verify_user_otp("auth@example.com", user["otp"])
    success, role, msg = auth_utils.authenticate_user("auth@example.com", "WrongPassword!")
    assert success is False
    assert "Incorrect" in msg


    # 3. Test Success
    success, role, msg = auth_utils.authenticate_user("auth@example.com", "Str0ngPass!@#")
    assert success is True
    assert role == "user"

def test_password_strength_missing_cases():
    assert auth_utils.validate_password_strength("alllower123!")[0] is False
    assert auth_utils.validate_password_strength("ALLUPPER123!")[0] is False

from unittest.mock import patch, MagicMock

def test_send_email_mock(capfd):
    with patch("utils.config.SMTP_EMAIL", None):
        res = auth_utils.send_email("test@example.com", "Subj", "<b>HTML</b>")
        assert res is True
        out, err = capfd.readouterr()
        assert "[EMAIL MOCK]" in out

def test_send_email_smtp_success():
    with patch("utils.config.SMTP_EMAIL", "real@test.com"), \
         patch("utils.config.SMTP_PASSWORD", "realpass"), \
         patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server
        res = auth_utils.send_email("test@example.com", "Subj", "<b>HTML</b>")
        assert res is True
        mock_server.starttls.assert_called()
        mock_server.send_message.assert_called()

def test_send_email_smtp_exception(capfd):
    with patch("utils.config.SMTP_EMAIL", "real@test.com"), \
         patch("utils.config.SMTP_PASSWORD", "realpass"), \
         patch("smtplib.SMTP", side_effect=Exception("SMTP Boom")):
        res = auth_utils.send_email("test@example.com", "Subj", "<b>HTML</b>")
        assert res is False
        out, err = capfd.readouterr()
        assert "[EMAIL ERROR]" in out

def test_create_user_pending_invalid_pass():
    success, msg = auth_utils.create_user_pending("test@example.com", "weak")
    assert success is False
    assert "least 8" in msg

def test_create_user_pending_existing(mock_db_connection):
    mock_db_connection["users"].insert_one({"email": "exist@test.com", "verified": True})
    success, msg = auth_utils.create_user_pending("exist@test.com", "Str0ngPass!@#")
    assert success is False
    assert "already exists" in msg

def test_create_user_pending_overwrite_unverified(mock_db_connection):
    mock_db_connection["users"].insert_one({"email": "unv@test.com", "verified": False})
    success, msg = auth_utils.create_user_pending("unv@test.com", "Str0ngPass!@#")
    assert success is True
    assert mock_db_connection["users"].count_documents({"email": "unv@test.com"}) == 1

def test_verify_user_otp_edge_cases(mock_db_connection):
    # Not found
    assert auth_utils.verify_user_otp("ghost@test.com", "123")[0] is False
    
    # Already verified
    mock_db_connection["users"].insert_one({"email": "ver@test.com", "verified": True})
    assert auth_utils.verify_user_otp("ver@test.com", "123")[0] is True
    
    # Invalid Code
    from datetime import datetime, timedelta
    mock_db_connection["users"].insert_one({
        "email": "inv@test.com", "verified": False, "otp": "000000",
        "otp_expiry": datetime.utcnow() + timedelta(minutes=10)
    })
    assert auth_utils.verify_user_otp("inv@test.com", "111111")[0] is False

    # Expired
    mock_db_connection["users"].insert_one({
        "email": "exp@test.com", "verified": False, "otp": "000000",
        "otp_expiry": datetime.utcnow() - timedelta(minutes=10)
    })
    assert auth_utils.verify_user_otp("exp@test.com", "000000")[0] is False

def test_authenticate_user_not_found(mock_db_connection):
    assert auth_utils.authenticate_user("ghost@test.com", "pass")[0] is False

def test_trigger_and_verify_2fa(mock_db_connection, capfd):
    mock_db_connection["users"].insert_one({"email": "2fa@test.com", "verified": True})
    
    auth_utils.trigger_2fa("2fa@test.com")
    user = mock_db_connection["users"].find_one({"email": "2fa@test.com"})
    assert user["otp"] is not None
    
    # Verify valid
    assert auth_utils.verify_2fa("2fa@test.com", user["otp"]) is True
    
    # Verify clears it
    user_after = mock_db_connection["users"].find_one({"email": "2fa@test.com"})
    assert user_after["otp"] is None
    
    # Verify invalid
    assert auth_utils.verify_2fa("2fa@test.com", "wrong") is False

def test_reset_password(mock_db_connection, capfd):
    assert auth_utils.reset_password_request("ghost@test.com")[0] is False
    
    mock_db_connection["users"].insert_one({
        "email": "reset@test.com", "password_hash": "old", "verified": True
    })
    
    success, msg = auth_utils.reset_password_request("reset@test.com")
    assert success is True
    
    user = mock_db_connection["users"].find_one({"email": "reset@test.com"})
    otp = user["otp"]
    
    # Confirm Not Found
    assert auth_utils.reset_password_confirm("ghost@test.com", otp, "NewPass1!")[0] is False
    
    # Confirm Invalid Code
    assert auth_utils.reset_password_confirm("reset@test.com", "wrong", "NewPass1!")[0] is False
    
    # Confirm Expired
    from datetime import datetime, timedelta
    mock_db_connection["users"].update_one(
        {"email": "reset@test.com"}, 
        {"$set": {"otp_expiry": datetime.utcnow() - timedelta(minutes=10)}}
    )
    assert auth_utils.reset_password_confirm("reset@test.com", otp, "NewPass1!")[0] is False
    
    # Confirm Success
    mock_db_connection["users"].update_one(
        {"email": "reset@test.com"}, 
        {"$set": {"otp_expiry": datetime.utcnow() + timedelta(minutes=10)}}
    )
    success, msg = auth_utils.reset_password_confirm("reset@test.com", otp, "NewPass1!@")
    assert success is True
    
    user_after = mock_db_connection["users"].find_one({"email": "reset@test.com"})
    assert user_after["password_hash"] != "old"

# --- Descope Tests ---
class MockDescope:
    class magiclink:
        @staticmethod
        def sign_up_or_in(method, login_id, uri):
            pass
        @staticmethod
        def verify(token):
            return {"user": {"email": "descope@test.com"}}

class MockDeliveryMethod:
    EMAIL = "email"

def test_descope_magic_link_not_configured():
    with patch("utils.auth_utils.descope_client", None):
        assert auth_utils.send_magic_link("test@example.com")[0] is False
        assert auth_utils.verify_magic_link_token("token")[0] is None

def test_send_magic_link_restricted():
    with patch("utils.config.RESTRICTED_EMAILS", ["admin@test.com"]), \
         patch("utils.auth_utils.descope_client", MockDescope()):
        assert auth_utils.send_magic_link("admin@test.com")[0] is False

def test_send_magic_link_intents(mock_db_connection):
    with patch("utils.auth_utils.descope_client", MockDescope()), \
         patch("utils.auth_utils.DeliveryMethod", MockDeliveryMethod, create=True):
        # Login but no user
        assert auth_utils.send_magic_link("new@test.com", intent="login")[0] is False
        
        # Signup but existing user
        mock_db_connection["users"].insert_one({"email": "exist@test.com", "verified": True})
        assert auth_utils.send_magic_link("exist@test.com", intent="signup")[0] is False
        
        # Success Signup
        assert auth_utils.send_magic_link("new@test.com", intent="signup")[0] is True
        
        # Success Login
        assert auth_utils.send_magic_link("exist@test.com", intent="login")[0] is True
        
        # Invalid Intent (Fallthrough)
        assert auth_utils.send_magic_link("new2@test.com", intent="unknown")[0] is True

        # Valid Login with custom redirect_url
        assert auth_utils.send_magic_link("exist@test.com", intent="login", redirect_url="http://custom")[0] is True

import sys
def test_auth_utils_descope_import():
    # Force the try block to succeed for line 283 but fail at 285 to cover lines 284-285
    mock_descope_module = MagicMock()
    mock_descope_module.DescopeClient = MagicMock(side_effect=Exception("Client Error"))
    mock_descope_module.common.DeliveryMethod = MagicMock()
    
    with patch.dict("sys.modules", {"descope": mock_descope_module, "descope.common": mock_descope_module.common}):
        import importlib
        import utils.auth_utils
        
        # Just reloading it executes the top-level block
        reloaded = importlib.reload(utils.auth_utils)
        assert reloaded.descope_client is None

def test_send_magic_link_exception(mock_db_connection):
    mock_descope = MockDescope()
    mock_descope.magiclink.sign_up_or_in = MagicMock(side_effect=Exception("API Fail"))
    with patch("utils.auth_utils.descope_client", mock_descope), \
         patch("utils.auth_utils.DeliveryMethod", MockDeliveryMethod, create=True):
        success, msg = auth_utils.send_magic_link("new@test.com", intent="signup")
        assert success is False
        assert "Failed to send" in msg

def test_verify_magic_link_token_success():
    with patch("utils.auth_utils.descope_client", MockDescope()):
        user_info, msg = auth_utils.verify_magic_link_token("good_token")
        assert user_info["email"] == "descope@test.com"

def test_verify_magic_link_token_exception():
    mock_descope = MockDescope()
    mock_descope.magiclink.verify = MagicMock(side_effect=Exception("Bad Token"))
    with patch("utils.auth_utils.descope_client", mock_descope):
        user_info, msg = auth_utils.verify_magic_link_token("bad_token")
        assert user_info is None
        assert "Failed" in msg

def test_sync_descope_user(mock_db_connection):
    # New user
    success, role, msg = auth_utils.sync_descope_user({"email": "sync@test.com"})
    assert success is True
    assert mock_db_connection["users"].count_documents({"email": "sync@test.com"}) == 1
    
    # Existing user
    success, role, msg = auth_utils.sync_descope_user({"email": "sync@test.com"})
    assert success is True
    assert "Welcome back" in msg
