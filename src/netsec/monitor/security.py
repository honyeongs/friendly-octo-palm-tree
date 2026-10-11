"""Password hashing, opaque credentials and durable request throttles."""

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def token():
    return secrets.token_urlsafe(32)


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
    return f"scrypt-v1${salt}${value.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt-v1":
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def rate_limit(db, key, *, limit, seconds=60):
    stamp = time.time()
    exceeded = False
    with db.connect(write=True) as conn:
        row = conn.execute("SELECT * FROM rate_limits WHERE key=?", (key,)).fetchone()
        if row is None or stamp - row["started"] >= seconds:
            conn.execute("INSERT OR REPLACE INTO rate_limits VALUES(?,?,1)", (key, stamp))
        else:
            exceeded = row["count"] >= limit
            conn.execute("UPDATE rate_limits SET count=count+1 WHERE key=?", (key,))
        conn.execute("DELETE FROM rate_limits WHERE started<?", (stamp - 86400,))
    if exceeded:
        raise HTTPException(429, "요청이 너무 많습니다. 잠시 후 다시 시도하세요.", headers={"Retry-After": str(seconds)})
