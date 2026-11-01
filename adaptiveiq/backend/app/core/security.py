"""Password hashing and session tokens."""
import secrets
import time
from collections import defaultdict, deque
from threading import Lock

import bcrypt
import jwt

ALGO = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except ValueError:
        return False


# A real hash of a random value, so a login for an unknown email costs the same time as a real one.
_DUMMY_HASH = hash_password(secrets.token_hex(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def make_token(user_id: int, role: str, token_version: int, secret: str, hours: int) -> str:
    now = int(time.time())
    return jwt.encode({"typ": "session", "sub": str(user_id), "role": role, "tv": token_version, "iat": now,
                       "exp": now + hours * 3600}, secret, algorithm=ALGO)


def read_token(token: str, secret: str, typ: str = "session") -> dict | None:
    """Decodes a token and checks its type, so an email-verification link can never be used as a session."""
    try:
        claims = jwt.decode(token, secret, algorithms=[ALGO], options={"require": ["exp", "sub", "typ"]})
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == typ else None


def make_verify_token(user_id: int, email: str, secret: str, hours: int) -> str:
    now = int(time.time())
    return jwt.encode({"typ": "verify_email", "sub": str(user_id), "email": email, "iat": now,
                       "exp": now + hours * 3600}, secret, algorithm=ALGO)


def new_join_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"         # no 0/O or 1/I
    return "".join(secrets.choice(alphabet) for _ in range(8))


class LoginLimiter:
    """Counts failed logins per (email, client) in a sliding window. In-memory: one backend process."""

    def __init__(self, max_failures: int, window_s: int):
        self.max, self.window = max_failures, window_s
        self.fails: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    def _trim(self, key: str, now: float):
        q = self.fails[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> int:
        """Seconds until the key may try again, or 0."""
        now = time.time()
        with self.lock:
            q = self._trim(key, now)
            return int(self.window - (now - q[0])) + 1 if len(q) >= self.max else 0

    def fail(self, key: str):
        with self.lock:
            self.fails[key].append(time.time())

    def reset(self, key: str):
        with self.lock:
            self.fails.pop(key, None)
