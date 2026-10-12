"""Test helpers: stdlib RSA keypairs, a fake team JWKS and signed Access JWTs (no network).

Adapted from culture-rules ``tests/auth/jwks.py`` (cite-don't-import). That helper signs with
the ``cryptography`` package; xteink's privacy job runs ``tests/server`` in a container where
a skip fails the gate and ``cryptography`` is not a dev dependency, so the keys here are made
and used with the standard library only: Miller-Rabin primes from a seeded RNG (deterministic
per ``kid``/seed) and RSASSA-PKCS1-v1_5 / SHA-256 signing with ``pow``. 1024-bit keys are
plenty for tests and keep key generation fast. Test-only code: never use it for real keys.
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import time
from typing import Any

TEAM = "team.cloudflareaccess.example"
AUD = "aud-tag-0123456789abcdef"
KID = "kid-1"
NOW = 1_800_000_000
_E = 65537
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")
_SMALL_PRIMES = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _int(value: int) -> str:
    return b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))


def _probable_prime(n: int, rng: random.Random, rounds: int = 32) -> bool:
    if n < 2 or any(n % p == 0 for p in _SMALL_PRIMES):
        return n in _SMALL_PRIMES
    d, s = n - 1, 0
    while d % 2 == 0:
        d, s = d // 2, s + 1
    for _ in range(rounds):
        x = pow(rng.randrange(2, n - 1), d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int, rng: random.Random) -> int:
    while True:
        candidate = rng.getrandbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if (candidate - 1) % _E and _probable_prime(candidate, rng):
            return candidate


class Keypair:
    """A deterministic 1024-bit RSA keypair (``seed`` defaults to ``kid``)."""

    def __init__(self, kid: str = KID, seed: str | None = None) -> None:
        self.kid = kid
        rng = random.Random(f"xteink-test-rsa:{seed if seed is not None else kid}")  # nosec
        p = _prime(512, rng)
        q = _prime(512, rng)
        while q == p:
            q = _prime(512, rng)
        self.n = p * q
        self.e = _E
        self._d = pow(_E, -1, (p - 1) * (q - 1))

    def jwk(self) -> dict[str, str]:
        return {"kid": self.kid, "kty": "RSA", "alg": "RS256", "use": "sig",
                "n": _int(self.n), "e": _int(self.e)}  # fmt: skip

    def sign(self, data: bytes) -> bytes:
        k = (self.n.bit_length() + 7) // 8
        t = _SHA256_DIGEST_INFO + hashlib.sha256(data).digest()
        em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
        return pow(int.from_bytes(em, "big"), self._d, self.n).to_bytes(k, "big")


_KEYS: dict[str, Keypair] = {}


def keypair(kid: str = KID) -> Keypair:
    """One keypair per kid per process."""
    if kid not in _KEYS:
        _KEYS[kid] = Keypair(kid)
    return _KEYS[kid]


def jwks(*pairs: Keypair) -> dict[str, Any]:
    return {"keys": [p.jwk() for p in (pairs or (keypair(),))]}


def claims(**changes: Any) -> dict[str, Any]:
    base = {
        "aud": [AUD],
        "iss": f"https://{TEAM}",
        "sub": "user-sub-1",
        "email": "alice@example.com",
        "iat": NOW - 10,
        "nbf": NOW - 10,
        "exp": NOW + 600,
        "type": "app",
    }
    base.update(changes)
    return {k: v for k, v in base.items() if v is not None}


def token(
    body: dict[str, Any] | None = None,
    *,
    pair: Keypair | None = None,
    header: dict[str, Any] | None = None,
) -> str:
    pair = pair or keypair()
    head = header if header is not None else {"alg": "RS256", "kid": pair.kid, "typ": "JWT"}
    signing_input = f"{b64(json.dumps(head).encode())}.{b64(json.dumps(body or claims()).encode())}"
    return f"{signing_input}.{b64(pair.sign(signing_input.encode()))}"


def now() -> float:
    return float(NOW)


def wall_clock_token(**changes: Any) -> str:
    """A token valid against the real clock (for tests that use the default clock)."""
    t = int(time.time())
    return token(claims(iat=t - 10, nbf=t - 10, exp=t + 600, **changes))
