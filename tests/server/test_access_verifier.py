"""Cloudflare Access JWT verifier + its all-or-nothing config (no third-party packages).

Adapted from culture-rules ``tests/auth/test_access_jwt.py`` (cite-don't-import), with the
listener config replaced by xteink's two-variable :class:`AccessConfig` and a clock leeway.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading

import pytest

from xteink.server import load_config
from xteink.server.access import (
    ACCESS_ENV,
    DEFAULT_LEEWAY,
    AccessConfig,
    AccessConfigError,
    AccessVerifier,
    VerificationError,
    verify_rs256,
)

from .access_jwt import AUD, NOW, TEAM, Keypair, b64, claims, jwks, keypair, now, token


def verifier(fetches: list | None = None, keyset=None, **kw) -> AccessVerifier:
    def fetch():
        if fetches is not None:
            fetches.append(1)
        return keyset if keyset is not None else jwks()

    return AccessVerifier(TEAM, AUD, fetch_jwks=fetch, clock=now, **kw)


def reason(v: AccessVerifier, tok: str) -> str:
    with pytest.raises(VerificationError) as ei:
        v.verify(tok)
    return ei.value.reason


def test_valid_interactive_token_yields_sso_identity():
    ident = verifier().verify(token())
    assert ident.kind == "sso"
    assert ident.email == "alice@example.com"
    assert ident.subject == "user-sub-1"
    assert ident.identity == "alice@example.com"


def test_valid_access_service_token_yields_service_identity():
    body = claims(email=None, common_name="ci.abcdef.access", sub="")
    ident = verifier().verify(token(body))
    assert ident.kind == "service"
    assert ident.identity == "ci.abcdef.access"


def test_audience_may_be_a_single_string():
    assert verifier().verify(token(claims(aud=AUD))).kind == "sso"


def test_forged_signature_is_rejected():
    forger = Keypair(kid="kid-1", seed="forger")  # same kid, different key: a forgery
    assert reason(verifier(), token(pair=forger)) == "bad_signature"


def test_tampered_payload_is_rejected():
    head, _, sig = token().split(".")
    evil = b64(json.dumps(claims(email="root@example.com")).encode())
    assert reason(verifier(), f"{head}.{evil}.{sig}") == "bad_signature"


def test_expired_token_is_rejected_after_the_leeway():
    assert reason(verifier(), token(claims(exp=NOW - DEFAULT_LEEWAY))) == "expired"
    assert reason(verifier(), token(claims(exp=NOW - 3600))) == "expired"


def test_small_clock_skew_is_tolerated():
    assert verifier().verify(token(claims(exp=NOW - 1))).kind == "sso"
    assert verifier().verify(token(claims(nbf=NOW + 1))).kind == "sso"
    assert reason(verifier(leeway=0), token(claims(exp=NOW))) == "expired"


def test_not_yet_valid_token_is_rejected():
    assert reason(verifier(), token(claims(nbf=NOW + DEFAULT_LEEWAY + 1))) == "not_yet_valid"


def test_wrong_audience_is_rejected():
    assert reason(verifier(), token(claims(aud=["someone-else"]))) == "bad_audience"


def test_wrong_issuer_is_rejected():
    assert reason(verifier(), token(claims(iss="https://evil.cloudflareaccess.example"))) == (
        "bad_issuer"
    )


@pytest.mark.parametrize(
    "header",
    [
        {"alg": "none", "kid": "kid-1"},
        {"alg": "HS256", "kid": "kid-1"},
        {"alg": "RS256"},  # no kid
    ],
)
def test_algorithm_confusion_and_missing_kid_are_rejected(header):
    assert reason(verifier(), token(header=header)) == "malformed"


@pytest.mark.parametrize("bad", ["", "a.b", "a.b.c.d", "!!.!!.!!", "x.y.z"])
def test_malformed_tokens_are_rejected(bad):
    assert reason(verifier(), bad) == "malformed"


def test_missing_exp_is_malformed():
    assert reason(verifier(), token(claims(exp=None))) == "malformed"


def test_unknown_kid_refetches_once_per_window_then_refuses():
    fetches: list = []
    v = verifier(fetches)
    v.verify(token())
    assert len(fetches) == 1
    other = keypair("kid-2")
    assert reason(v, token(pair=other)) == "unknown_kid"
    assert reason(v, token(pair=other)) == "unknown_kid"
    assert len(fetches) == 2  # one forced refetch inside the window, not one per request


def test_key_rotation_is_picked_up_on_kid_miss():
    rotated = {"value": jwks()}
    v = AccessVerifier(TEAM, AUD, fetch_jwks=lambda: rotated["value"], clock=now)
    v.verify(token())
    rotated["value"] = jwks(keypair("kid-2"))
    assert v.verify(token(pair=keypair("kid-2"))).kind == "sso"


def test_jwks_fetch_failure_refuses_without_raising_other_errors():
    def boom():
        raise OSError("network down")

    v = AccessVerifier(TEAM, AUD, fetch_jwks=boom, clock=now)
    assert reason(v, token()) == "unknown_kid"


def test_jwks_entries_that_are_not_rs256_signing_keys_are_ignored():
    jwk = keypair().jwk()
    keyset = {"keys": [{**jwk, "use": "enc"}, {**jwk, "kty": "EC"}, {**jwk, "alg": "RS512"}]}
    assert reason(verifier(keyset=keyset), token()) == "unknown_kid"


def test_team_domain_is_normalised():
    v = AccessVerifier(f"https://{TEAM}/", AUD, fetch_jwks=jwks, clock=now)
    assert v.team_domain == TEAM
    assert v.jwks_url == f"https://{TEAM}/cdn-cgi/access/certs"
    assert v.verify(token()).kind == "sso"


@pytest.mark.parametrize("scheme", ["https", "http", "HTTPS"])
def test_team_domain_scheme_is_dropped_and_jwks_is_always_https(scheme):
    v = AccessVerifier(f"{scheme}://{TEAM}", AUD, fetch_jwks=jwks, clock=now)
    assert v.team_domain == TEAM
    assert v.jwks_url == f"https://{TEAM}/cdn-cgi/access/certs"


def test_verify_rs256_is_pure_stdlib_pkcs1_v15():
    pair = keypair()
    sig = pair.sign(b"hello")
    assert verify_rs256(pair.n, pair.e, b"hello", sig)
    assert not verify_rs256(pair.n, pair.e, b"hellO", sig)
    assert not verify_rs256(pair.n, pair.e, b"hello", sig[:-1])
    assert not verify_rs256(pair.n, pair.e, b"hello", b"\x00" * len(sig))


def test_failing_jwks_fetch_is_negative_cached_for_forged_tokens():
    fetches: list = []

    def boom():
        fetches.append(1)
        raise OSError("network down")

    v = AccessVerifier(TEAM, AUD, fetch_jwks=boom, clock=now)
    for i in range(5):
        assert reason(v, token(pair=keypair(f"forged-{i}"))) == "unknown_kid"
    assert len(fetches) == 1


def test_concurrent_forged_tokens_share_one_failing_fetch():
    fetches: list = []
    release = threading.Event()

    def slow_boom():
        fetches.append(1)
        release.wait(2.0)
        raise OSError("network down")

    v = AccessVerifier(TEAM, AUD, fetch_jwks=slow_boom, clock=now)
    reasons: list = []
    tokens = [token(pair=keypair(f"forged-{i}")) for i in range(5)]

    def attempt(tok):
        try:
            v.verify(tok)
        except VerificationError as exc:
            reasons.append(exc.reason)

    threads = [threading.Thread(target=attempt, args=(t,)) for t in tokens]
    for t in threads:
        t.start()
    release.set()
    for t in threads:
        t.join(5.0)
    assert reasons == ["unknown_kid"] * 5
    assert len(fetches) == 1


def test_the_jwks_fetch_runs_outside_the_lock():
    started, release = threading.Event(), threading.Event()
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] > 1:  # the forced refetch for an unknown kid blocks
            started.set()
            release.wait(2.0)
        return jwks()

    v = AccessVerifier(TEAM, AUD, fetch_jwks=fetch, clock=now)
    v.verify(token())  # loads kid-1
    other = token(pair=keypair("kid-9"))
    worker = threading.Thread(target=lambda: reason(v, other))
    worker.start()
    assert started.wait(2.0)
    done = threading.Event()
    checker = threading.Thread(target=lambda: (v.verify(token()), done.set()))
    checker.start()
    try:
        assert done.wait(1.0), "a cached-kid verify blocked behind an in-flight JWKS fetch"
    finally:
        release.set()
        worker.join(5.0)
        checker.join(5.0)


def test_constructing_a_verifier_makes_no_network_call(monkeypatch):
    import xteink.server.access as access

    calls: list = []
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    v = AccessVerifier(TEAM, AUD)
    assert calls == []
    assert v.jwks_url == f"https://{TEAM}/cdn-cgi/access/certs"


def test_access_module_is_stdlib_only():
    code = (
        "import sys\n"
        "sys.modules['cryptography'] = None\nsys.modules['jwt'] = None\n"
        "sys.modules['fastapi'] = None\nsys.modules['pydantic'] = None\n"
        "import xteink.server, xteink.server.access\n"
        "print('ok')\n"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "ok", done.stderr


# --- all-or-nothing configuration ---------------------------------------------------------

ENV = {"XTEINK_ACCESS_TEAM_DOMAIN": TEAM, "XTEINK_ACCESS_AUD": AUD}


def test_env_names():
    assert ACCESS_ENV == ("XTEINK_ACCESS_TEAM_DOMAIN", "XTEINK_ACCESS_AUD")


def test_access_config_both_set():
    cfg = AccessConfig.from_env(ENV)
    assert (cfg.team_domain, cfg.audience) == (TEAM, AUD)
    assert isinstance(cfg.verifier(), AccessVerifier)


def test_access_config_both_unset_is_off():
    assert AccessConfig.from_env({}) is None
    assert AccessConfig.from_env({k: " " for k in ENV}) is None


@pytest.mark.parametrize("missing", sorted(ENV))
def test_access_config_partial_is_refused(missing):
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(AccessConfigError) as ei:
        AccessConfig.from_env(env)
    assert "XTEINK_ACCESS_TEAM_DOMAIN" in str(ei.value) and "XTEINK_ACCESS_AUD" in str(ei.value)


def test_load_config_carries_access_config():
    assert load_config({}).access is None
    assert load_config(ENV).access == AccessConfig(TEAM, AUD)


def test_load_config_refuses_partial_access_config():
    with pytest.raises(ValueError, match="XTEINK_ACCESS_AUD"):
        load_config({"XTEINK_ACCESS_TEAM_DOMAIN": TEAM})


@pytest.mark.parametrize("missing", sorted(ENV))
def test_serve_refuses_to_start_with_partial_access_config(monkeypatch, capsys, missing):
    from xteink.server.__main__ import main as server_main

    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    for name, value in ENV.items():
        if name != missing:
            monkeypatch.setenv(name, value)
    assert server_main(["serve"]) == 2
    err = capsys.readouterr().err
    assert "error:" in err and missing in err
