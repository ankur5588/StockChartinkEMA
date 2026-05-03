"""Fernet encryption helpers for sensitive credentials."""
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv(Path(__file__).parent / ".env")
_cipher = Fernet(os.environ["FERNET_KEY"].encode())


def encrypt_dict(data: dict) -> str:
    return _cipher.encrypt(json.dumps(data).encode()).decode()


def decrypt_dict(token: str) -> dict:
    return json.loads(_cipher.decrypt(token.encode()).decode())
