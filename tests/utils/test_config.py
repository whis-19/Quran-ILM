import os
import pytest
from unittest.mock import patch, MagicMock
from utils import config
import streamlit as st

def test_get_env_from_os():
    with patch.dict(os.environ, {"MOCK_KEY": "os_value"}):
        assert config.get_env("MOCK_KEY") == "os_value"

def test_get_env_from_secrets():
    # Streamlit secrets mock
    mock_secrets = {"level1": {"level2": "secret_value"}}
    with patch("os.getenv", return_value=None):
        with patch("streamlit.secrets", mock_secrets):
            assert config.get_env("MOCK_KEY", secret_path=("level1", "level2")) == "secret_value"

def test_get_env_secrets_key_error():
    mock_secrets = {"level1": {"wrong_key": "secret_value"}}
    with patch("os.getenv", return_value=None):
        with patch("streamlit.secrets", mock_secrets):
            assert config.get_env("MOCK_KEY", default="default_val", secret_path=("level1", "level2")) == "default_val"

def test_get_env_secrets_no_attribute():
    with patch("os.getenv", return_value=None):
        with patch("streamlit.secrets", object()):
            assert config.get_env("MOCK_KEY", default="val", secret_path=("level1",)) == "val"

def test_get_env_default():
    with patch("os.getenv", return_value=None):
        assert config.get_env("NON_EXISTENT", default="fallback") == "fallback"
