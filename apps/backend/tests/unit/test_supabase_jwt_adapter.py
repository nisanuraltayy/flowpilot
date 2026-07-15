"""SupabaseJwtAuthAdapter güvenlik testleri — NETWORK YOK.

Test RSA/EC anahtar çiftleri RUNTIME'DA üretilir; repository'ye hiçbir private
key fixture COMMIT EDİLMEZ. JWKS, PyJWKClient'ın fetch_data'sı override edilerek
lokal olarak servis edilir — kid eşleme, cache ve rotation gerçek PyJWT kod
yolundan geçer.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt import PyJWKClient
from jwt.algorithms import ECAlgorithm, RSAAlgorithm
from jwt.exceptions import PyJWKClientConnectionError

from flowpilot.modules.identity.application.auth import (
    AuthenticationError,
    AuthProviderUnavailable,
    ExpiredAccessToken,
    InvalidAccessToken,
)
from flowpilot.modules.identity.domain.auth_provider import AuthProvider
from flowpilot.modules.identity.infrastructure.supabase_jwt import SupabaseJwtAuthAdapter

SUPABASE_URL = "https://example-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"


# ------------------------------------------------------------------ test keys


def _pem(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _rsa_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    return {**public, "kid": kid, "alg": "RS256", "use": "sig"}


def _ec_jwk(key: ec.EllipticCurvePrivateKey, kid: str) -> dict[str, Any]:
    public = json.loads(ECAlgorithm.to_jwk(key.public_key()))
    return {**public, "kid": kid, "alg": "ES256", "use": "sig"}


class LocalJWKClient(PyJWKClient):
    """JWKS'i network yerine bellekten servis eder; fetch sayısını izler."""

    def __init__(self, jwks: dict[str, Any], **kwargs: Any) -> None:
        self.jwks = jwks
        self.fetch_count = 0
        self.fail_connection = False
        super().__init__("https://jwks.invalid/keys", **kwargs)

    def fetch_data(self) -> Any:
        if self.fail_connection:
            raise PyJWKClientConnectionError("baglanti kurulamadi")
        self.fetch_count += 1
        # Gerçek PyJWKClient.fetch_data gibi: sonuç cache'e de yazılır.
        if self.jwk_set_cache is not None:
            self.jwk_set_cache.put(self.jwks)
        return self.jwks


def _claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "sub": "supabase-user-123",
        "iss": ISSUER,
        "aud": "authenticated",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "email": "user@example.com",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def ec_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(scope="module")
def other_rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _adapter(jwks: dict[str, Any], **kwargs: Any) -> tuple[SupabaseJwtAuthAdapter, LocalJWKClient]:
    client = LocalJWKClient(jwks, cache_jwk_set=kwargs.pop("cache_jwk_set", True), lifespan=300)
    adapter = SupabaseJwtAuthAdapter(supabase_url=SUPABASE_URL, jwk_client=client, **kwargs)
    return adapter, client


# ------------------------------------------------------------------ happy path


def test_valid_rs256_token_is_accepted(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(_claims(), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"})

    identity = adapter.verify_token(token)

    assert identity.provider is AuthProvider.SUPABASE
    assert identity.provider_subject == "supabase-user-123"
    assert identity.email == "user@example.com"
    assert identity.token_expires_at > datetime.now(UTC)


def test_valid_es256_token_is_accepted(ec_key: ec.EllipticCurvePrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_ec_jwk(ec_key, "kid-ec")]})
    token = jwt.encode(_claims(), _pem(ec_key), algorithm="ES256", headers={"kid": "kid-ec"})

    identity = adapter.verify_token(token)

    assert identity.provider_subject == "supabase-user-123"


# ------------------------------------------------------------------ rejections


def test_expired_token_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    past = int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    token = jwt.encode(
        _claims(exp=past), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"}
    )

    with pytest.raises(ExpiredAccessToken):
        adapter.verify_token(token)


def test_wrong_issuer_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(
        _claims(iss="https://evil.example/auth/v1"),
        _pem(rsa_key),
        algorithm="RS256",
        headers={"kid": "kid-rsa"},
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_wrong_audience_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(
        _claims(aud="service_role"),
        _pem(rsa_key),
        algorithm="RS256",
        headers={"kid": "kid-rsa"},
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_wrong_signature_is_rejected(
    rsa_key: rsa.RSAPrivateKey, other_rsa_key: rsa.RSAPrivateKey
) -> None:
    # JWKS'te kid-rsa olarak DOĞRU anahtar yayınlanır; token BAŞKA anahtarla imzalanır.
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(
        _claims(), _pem(other_rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"}
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_missing_sub_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(
        _claims(sub=None), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"}
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_hs256_token_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    # Algorithm confusion saldırısı: HS256 ile imzalanmış token allow-list'e takılır.
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    token = jwt.encode(
        _claims(),
        "a-sufficiently-long-shared-secret-for-hs256!",  # >=32 bayt (PyJWT uyarısı)
        algorithm="HS256",
        headers={"kid": "kid-rsa"},
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_hs256_cannot_be_configured_as_allowed_algorithm() -> None:
    with pytest.raises(ValueError, match="asimetrik"):
        SupabaseJwtAuthAdapter(supabase_url=SUPABASE_URL, allowed_algorithms=("RS256", "HS256"))


def test_unsupported_algorithm_is_rejected(ec_key: ec.EllipticCurvePrivateKey) -> None:
    # Adapter yalniz RS256'ya izin verir; ES256 token reddedilir — `algorithms`
    # token header'indan ASLA alinmaz.
    client = LocalJWKClient({"keys": [_ec_jwk(ec_key, "kid-ec")]})
    adapter = SupabaseJwtAuthAdapter(
        supabase_url=SUPABASE_URL, allowed_algorithms=("RS256",), jwk_client=client
    )
    token = jwt.encode(_claims(), _pem(ec_key), algorithm="ES256", headers={"kid": "kid-ec"})

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)


def test_garbage_token_is_rejected(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token("not-a-jwt")


# ------------------------------------------------------- availability & hygiene


def test_jwks_connection_failure_maps_to_provider_unavailable(
    rsa_key: rsa.RSAPrivateKey,
) -> None:
    adapter, client = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    client.fail_connection = True
    token = jwt.encode(_claims(), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"})

    # Gecici altyapi hatasi invalid-token DEGILDIR.
    with pytest.raises(AuthProviderUnavailable):
        adapter.verify_token(token)


def test_token_never_appears_in_raised_errors(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    past = int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    secret_marker = "SECRET-TOKEN-MARKER"
    token = jwt.encode(
        _claims(exp=past, email=f"{secret_marker}@example.com"),
        _pem(rsa_key),
        algorithm="RS256",
        headers={"kid": "kid-rsa"},
    )

    with pytest.raises(AuthenticationError) as exc_info:
        adapter.verify_token(token)

    rendered = f"{exc_info.value!s} {exc_info.value!r} {exc_info.value.args!r}"
    assert token not in rendered
    assert secret_marker not in rendered


# ------------------------------------------------------- cache & key rotation


def test_jwks_is_cached_across_verifications(rsa_key: rsa.RSAPrivateKey) -> None:
    adapter, client = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]}, cache_jwk_set=True)
    token = jwt.encode(_claims(), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-rsa"})

    adapter.verify_token(token)
    adapter.verify_token(token)
    adapter.verify_token(token)

    assert client.fetch_count == 1  # cache calisti; her istek JWKS cekmedi


def test_key_rotation_is_picked_up(
    rsa_key: rsa.RSAPrivateKey, other_rsa_key: rsa.RSAPrivateKey
) -> None:
    # cache_jwk_set=False: her dogrulama guncel JWKS'i gorur (rotation senaryosu).
    adapter, client = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-old")]}, cache_jwk_set=False)

    old_token = jwt.encode(_claims(), _pem(rsa_key), algorithm="RS256", headers={"kid": "kid-old"})
    assert adapter.verify_token(old_token).provider_subject == "supabase-user-123"

    # Anahtar rotasyonu: eski kid kaldirilir, yeni kid yayinlanir.
    client.jwks = {"keys": [_rsa_jwk(other_rsa_key, "kid-new")]}

    new_token = jwt.encode(
        _claims(), _pem(other_rsa_key), algorithm="RS256", headers={"kid": "kid-new"}
    )
    assert adapter.verify_token(new_token).provider_subject == "supabase-user-123"

    # Eski anahtarla imzalanmis token artik dogrulanamaz.
    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(old_token)


def test_time_moves_forward_between_tokens(rsa_key: rsa.RSAPrivateKey) -> None:
    # iat gelecekte olan token reddedilir (iat dogrulanir).
    adapter, _ = _adapter({"keys": [_rsa_jwk(rsa_key, "kid-rsa")]})
    future = int(time.time()) + 3600
    token = jwt.encode(
        _claims(iat=future, exp=future + 600),
        _pem(rsa_key),
        algorithm="RS256",
        headers={"kid": "kid-rsa"},
    )

    with pytest.raises(InvalidAccessToken):
        adapter.verify_token(token)
