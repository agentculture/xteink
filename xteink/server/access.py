"""Cloudflare Access JWT verification (``Cf-Access-Jwt-Assertion``), standard-library only.

Provenance: cited (cite-don't-import, NOT imported) from culture-rules
``culture_rules/auth/access.py`` (agentculture/culture-rules @ 7ade10a, file last changed in
0e456ed, culture-rules 0.10.0). xteink owns this copy. Local changes: xteink env names and a
two-variable :class:`AccessConfig` instead of culture-rules' three-variable loopback listener
config; :class:`VerificationError` derives from :class:`Exception` (no culture-rules principal
module); a small ``nbf``/``exp`` clock leeway; :data:`ACCESS_HEADER` / :data:`CSRF_HEADER`.

The token must be a three-part RS256 JWT whose ``kid`` names a key in the team JWKS
(``https://<team>/cdn-cgi/access/certs``), whose signature verifies (RSASSA-PKCS1-v1_5 /
SHA-256, implemented here with ``pow``), whose ``iss`` is ``https://<team>``, whose ``aud``
contains the application's AUD tag, and which is inside ``nbf`` .. ``exp`` (give or take
``leeway`` seconds). Anything else is a :class:`VerificationError` with a short reason
(``malformed``, ``unknown_kid``, ``bad_signature``, ``bad_issuer``, ``bad_audience``,
``expired``, ``not_yet_valid``) that is safe to log and never carries token material.

Keys are cached by ``kid``; an unknown ``kid`` forces at most one JWKS refetch per
``refetch_window`` seconds (key rotation without a refetch storm). While no keys are cached,
a failed load is negative-cached for the same window, so forged tokens cannot drive a fetch
per request. The fetch runs outside the lock, single-flight: concurrent misses wait for the
one fetch in progress instead of starting their own.

Privacy: constructing a verifier makes no network call. The JWKS is fetched lazily, the
first time a request actually carries an Access JWT. With Access unset no verifier exists.

Configuration is all-or-nothing: ``XTEINK_ACCESS_TEAM_DOMAIN`` and ``XTEINK_ACCESS_AUD`` are
set together (Access on) or both unset (Access off); a partial pair is refused with
:class:`AccessConfigError` (a :class:`ValueError`, so ``serve`` exits 2 before binding).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ACCESS_ENV",
    "ACCESS_HEADER",
    "CSRF_HEADER",
    "DEFAULT_LEEWAY",
    "ENV_AUD",
    "ENV_TEAM_DOMAIN",
    "AccessConfig",
    "AccessConfigError",
    "AccessIdentity",
    "AccessVerifier",
    "VerificationError",
    "verify_rs256",
]

ENV_TEAM_DOMAIN = "XTEINK_ACCESS_TEAM_DOMAIN"
ENV_AUD = "XTEINK_ACCESS_AUD"
ACCESS_ENV = (ENV_TEAM_DOMAIN, ENV_AUD)

#: The header Cloudflare Access adds to every request it proxies to the origin.
ACCESS_HEADER = "Cf-Access-Jwt-Assertion"
#: Custom header a browser must send on unsafe methods when authenticated by Access (CSRF).
CSRF_HEADER = "X-Xteink-Request"
#: Seconds of clock skew tolerated on ``nbf`` and ``exp``.
DEFAULT_LEEWAY = 30.0

_JWKS_LIMIT = 1 << 20
#: How long a caller waits for another caller's in-flight JWKS fetch (the fetch's own timeout).
_FETCH_WAIT_S = 10.0
#: Schemes a pasted team-domain URL may carry; dropped, since the JWKS fetch is https-only.
_WEB_SCHEMES = frozenset({"https", "http"})
# DER prefix of DigestInfo for SHA-256 (RFC 8017 section 9.2, note 1).
_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


class AccessConfigError(ValueError):
    """The Access configuration is partial or malformed."""


class VerificationError(Exception):
    """A refused Access JWT; ``reason`` is a short, loggable classification."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"access token verification failed: {reason}")
        self.reason = reason


@dataclass(frozen=True)
class AccessIdentity:
    """What a verified Access JWT asserts. ``kind`` is ``sso`` (a person) or ``service``."""

    subject: str
    email: str
    common_name: str
    kind: str

    @property
    def identity(self) -> str:
        """The audit identity: the email for a person, the common name for a service token."""
        return self.email if self.kind == "sso" else self.common_name


@dataclass(frozen=True)
class AccessConfig:
    """The Cloudflare Access team domain and application AUD tag the main app pins."""

    team_domain: str
    audience: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> AccessConfig | None:
        values = {k: (env.get(k) or "").strip() for k in ACCESS_ENV}
        configured = [k for k, v in values.items() if v]
        if not configured:
            return None
        if len(configured) != len(ACCESS_ENV):
            raise AccessConfigError(
                f"incomplete Cloudflare Access configuration: set {' and '.join(ACCESS_ENV)} "
                "together, or unset both"
            )
        return cls(values[ENV_TEAM_DOMAIN], values[ENV_AUD])

    def verifier(self) -> AccessVerifier:
        """A verifier for this config (no network call until a JWT is verified)."""
        return AccessVerifier(self.team_domain, self.audience)


def _b64(segment: str) -> bytes:
    if not segment or not all(c.isalnum() or c in "-_" for c in segment):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64_int(segment: str) -> int:
    return int.from_bytes(_b64(segment), "big")


def verify_rs256(n: int, e: int, message: bytes, signature: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 verification with SHA-256 (RFC 8017 8.2.2), standard library only."""
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    em = pow(s, e, n).to_bytes(k, "big")
    t = _SHA256_DIGEST_INFO + hashlib.sha256(message).digest()
    pad = k - len(t) - 3
    if pad < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * pad + b"\x00" + t
    return hmac.compare_digest(em, expected)


def _parse_keys(document: Any) -> dict[str, tuple[int, int]]:
    keys: dict[str, tuple[int, int]] = {}
    entries = document.get("keys") if isinstance(document, Mapping) else None
    for jwk in entries if isinstance(entries, list) else []:
        if not isinstance(jwk, Mapping):
            continue
        kid = jwk.get("kid")
        if not kid or jwk.get("kty") != "RSA" or jwk.get("alg") != "RS256":
            continue
        if jwk.get("use") != "sig":
            continue
        try:
            n, e = _b64_int(str(jwk.get("n", ""))), _b64_int(str(jwk.get("e", "")))
        except ValueError:  # binascii.Error is a ValueError
            continue
        if n > 0 and e > 1:
            keys[str(kid)] = (n, e)
    return keys


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


class AccessVerifier:
    """Verify Cloudflare Access RS256 JWTs pinned to one team domain and one AUD tag."""

    def __init__(
        self,
        team_domain: str,
        audience: str,
        *,
        fetch_jwks: Callable[[], Any] | None = None,
        clock: Callable[[], float] | None = None,
        refetch_window: float = 60.0,
        leeway: float = DEFAULT_LEEWAY,
    ) -> None:
        domain = team_domain.strip().rstrip("/")
        # A pasted URL is accepted for convenience: its web scheme is dropped, and the JWKS is
        # always fetched over https (below), whatever scheme the operator wrote.
        scheme, sep, rest = domain.partition("://")
        if sep and scheme.lower() in _WEB_SCHEMES:
            domain = rest
        if not domain or not audience:
            raise AccessConfigError("Access needs both a team domain and an audience")
        self.team_domain = domain
        self.audience = audience
        self.jwks_url = f"https://{domain}/cdn-cgi/access/certs"
        self._fetch = fetch_jwks or self._fetch_over_https
        self._clock = clock or time.time
        self._window = refetch_window
        self._leeway = leeway
        self._keys: dict[str, tuple[int, int]] = {}
        self._last_forced: float | None = None
        self._failed_at: float | None = None
        self._inflight: threading.Event | None = None
        self._lock = threading.Lock()

    def _fetch_over_https(self) -> Any:
        request = urllib.request.Request(self.jwks_url, headers={"Accept": "application/json"})
        # the URL is always https://<configured team domain>/... (built above)
        with urllib.request.urlopen(request, timeout=10) as resp:  # nosec B310
            return json.loads(resp.read(_JWKS_LIMIT))

    def _load(self) -> dict[str, tuple[int, int]]:
        """Fetch and parse the JWKS; any fetch/parse failure means "no usable keys"."""
        try:
            return _parse_keys(self._fetch())
        except Exception:  # noqa: BLE001 - never let a JWKS problem escape as another error
            return {}

    def _fetch_due(self, now: float) -> bool:
        """Whether a miss may trigger a JWKS fetch now (caller holds the lock).

        An empty cache loads at once unless a load failed within the window (negative
        cache); a populated cache refetches for an unknown kid at most once per window.
        """
        if not self._keys:
            return self._failed_at is None or now - self._failed_at >= self._window
        if self._last_forced is None or now - self._last_forced >= self._window:
            self._last_forced = now
            return True
        return False

    def _key(self, kid: str) -> tuple[int, int]:
        with self._lock:
            if kid in self._keys:
                return self._keys[kid]
            inflight = self._inflight
            leader = inflight is None and self._fetch_due(self._clock())
            if leader:
                inflight = self._inflight = threading.Event()
        if leader:
            keys: dict[str, tuple[int, int]] = {}
            try:
                keys = self._load()  # network I/O outside the lock
            finally:
                with self._lock:
                    if keys:
                        self._keys = keys
                        self._failed_at = None
                    elif not self._keys:
                        self._failed_at = self._clock()
                    self._inflight = None
                inflight.set()
        elif inflight is not None:
            inflight.wait(_FETCH_WAIT_S)  # single flight: share the leader's fetch
        with self._lock:
            if kid in self._keys:
                return self._keys[kid]
        raise VerificationError("unknown_kid")

    def verify(self, token: str) -> AccessIdentity:
        """Return the asserted identity, or raise :class:`VerificationError`."""
        parts = token.split(".") if isinstance(token, str) else []
        if len(parts) != 3 or not all(parts):
            raise VerificationError("malformed")
        try:
            header = json.loads(_b64(parts[0]))
            signature = _b64(parts[2])
        except ValueError:  # binascii.Error is a ValueError
            raise VerificationError("malformed") from None
        if not isinstance(header, dict) or header.get("alg") != "RS256":
            raise VerificationError("malformed")
        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise VerificationError("malformed")
        n, e = self._key(kid)
        if not verify_rs256(n, e, f"{parts[0]}.{parts[1]}".encode(), signature):
            raise VerificationError("bad_signature")
        try:
            claims = json.loads(_b64(parts[1]))
        except ValueError:  # binascii.Error is a ValueError
            raise VerificationError("malformed") from None
        if not isinstance(claims, dict):
            raise VerificationError("malformed")
        return self._check_claims(claims)

    def _check_claims(self, claims: dict[str, Any]) -> AccessIdentity:
        if claims.get("iss") != f"https://{self.team_domain}":
            raise VerificationError("bad_issuer")
        self._check_audience(claims)
        self._check_validity(claims)
        return _identity_of(claims)

    def _check_audience(self, claims: dict[str, Any]) -> None:
        aud = claims.get("aud")
        audiences = [aud] if isinstance(aud, str) else aud
        if not isinstance(audiences, list) or not audiences:
            raise VerificationError("malformed")
        if self.audience not in audiences:
            raise VerificationError("bad_audience")

    def _check_validity(self, claims: dict[str, Any]) -> None:
        exp = _num(claims.get("exp"))
        nbf = _num(claims["nbf"]) if "nbf" in claims else None
        if exp is None or ("nbf" in claims and nbf is None):
            raise VerificationError("malformed")
        now = self._clock()
        if now >= exp + self._leeway:
            raise VerificationError("expired")
        if nbf is not None and now < nbf - self._leeway:
            raise VerificationError("not_yet_valid")


def _identity_of(claims: dict[str, Any]) -> AccessIdentity:
    """The person (email + sub) or service token (common_name) a valid assertion names."""
    email = claims.get("email") or ""
    common_name = claims.get("common_name") or ""
    subject = claims.get("sub") or ""
    if not all(isinstance(v, str) for v in (email, common_name, subject)):
        raise VerificationError("malformed")
    if email and subject:
        return AccessIdentity(subject, email, "", "sso")
    if common_name:
        return AccessIdentity(subject, "", common_name, "service")
    raise VerificationError("malformed")
