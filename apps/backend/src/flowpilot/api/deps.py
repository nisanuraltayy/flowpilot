"""API dependency wiring — ADAPTER SEÇİMİ YALNIZ BURADA yapılır (ADR-009).

Bu dosya composition root'un izinli wiring noktasıdır; infrastructure
adapter'larını import edebilir. Router'lar YALNIZ buradaki dependency'leri ve
modüllerin application sınırlarını kullanır.

Kurallar:
- Import sırasında engine/DB bağlantısı OLUŞMAZ; her şey ilk istekte, lazy.
- API yalnız `DATABASE_URL` (flowpilot_app, BYPASSRLS'siz) ile bağlanır;
  admin/migrator URL'i ASLA kullanılmaz (ADR-006).
- Raw token yalnız bu katmanda yaşar; router'lara `CurrentActor` gider.
- Development-only actor header YOKTUR; kimlik yalnız doğrulanmış token'dan gelir.
- Testler bu dependency'leri `app.dependency_overrides` ile değiştirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from flowpilot.config.settings import Settings
from flowpilot.modules.identity.application.auth import (
    AuthProviderPort,
    AuthProviderUnavailable,
    ExpiredAccessToken,
    InvalidAccessToken,
)
from flowpilot.modules.identity.application.ensure_user import (
    EnsureAuthenticatedUserHandler,
)
from flowpilot.modules.identity.infrastructure.persistence.unit_of_work import (
    SqlAlchemyIdentityUnitOfWork,
)
from flowpilot.modules.identity.infrastructure.persistence.user_directory import (
    SqlAlchemyUserDirectory,
)
from flowpilot.modules.identity.infrastructure.supabase_jwt import SupabaseJwtAuthAdapter
from flowpilot.modules.organization.application.handler import CreateOrganizationHandler
from flowpilot.modules.organization.infrastructure.persistence.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from flowpilot.shared.clock import SystemClock
from flowpilot.shared.ids import UuidGenerator

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentActor:
    """Doğrulanmış istek aktörü — yalnız internal FlowPilot UserId taşır."""

    user_id: UUID


def _unauthorized(detail: str) -> HTTPException:
    # Dışarı verilen mesaj token/provider detayı SIZDIRMAZ.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_session_factory(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> sessionmaker[Session]:
    """App-scoped, lazy session factory (flowpilot_app rolü).

    Engine ilk ihtiyaçta oluşturulur (import'ta değil); gerçek bağlantı ancak
    bir session iş yaptığında açılır.
    """
    cached: sessionmaker[Session] | None = getattr(request.app.state, "session_factory", None)
    if cached is not None:
        return cached
    if settings.database_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Veritabani yapilandirmasi eksik.",
        )
    engine = create_engine(settings.require_database_url(), pool_pre_ping=True)
    factory = sessionmaker(bind=engine)
    request.app.state.session_factory = factory
    return factory


def get_auth_provider(
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> AuthProviderPort:
    """AuthProviderPort → SupabaseJwtAuthAdapter (production wiring).

    Supabase yapılandırılmamışsa local/test'te import ve health bozulmaz;
    auth gerektiren istek güvenli şekilde 503 alır. Staging/production'da
    eksik yapılandırma zaten `create_app` başlangıcında reddedilir.
    """
    cached: AuthProviderPort | None = getattr(request.app.state, "auth_provider", None)
    if cached is not None:
        return cached
    if settings.supabase_url is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kimlik dogrulama servisi yapilandirilmamis.",
        )
    adapter = SupabaseJwtAuthAdapter(
        supabase_url=settings.supabase_url,
        audience=settings.supabase_jwt_audience,
        allowed_algorithms=settings.supabase_allowed_algorithms,
        jwks_cache_seconds=settings.supabase_jwks_cache_seconds,
        jwks_timeout_seconds=settings.supabase_jwks_timeout_seconds,
    )
    request.app.state.auth_provider = adapter
    return adapter


def get_ensure_user_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> EnsureAuthenticatedUserHandler:
    return EnsureAuthenticatedUserHandler(
        unit_of_work_factory=lambda: SqlAlchemyIdentityUnitOfWork(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_create_organization_handler(
    session_factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> CreateOrganizationHandler:
    return CreateOrganizationHandler(
        unit_of_work=SqlAlchemyUnitOfWork(session_factory),
        user_directory=SqlAlchemyUserDirectory(session_factory),
        clock=SystemClock(),
        id_generator=UuidGenerator(),
    )


def get_current_actor(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    auth_provider: Annotated[AuthProviderPort, Depends(get_auth_provider)],
    ensure_user: Annotated[EnsureAuthenticatedUserHandler, Depends(get_ensure_user_handler)],
) -> CurrentActor:
    """Bearer token → doğrulanmış kimlik → internal user → CurrentActor.

    Token doğrulanmadan hiçbir DB işlemi yapılmaz; `ensure_user` yalnız
    doğrulama başarılıysa çağrılır.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Bearer access token gerekli.")

    try:
        identity = auth_provider.verify_token(credentials.credentials)
    except ExpiredAccessToken as exc:
        raise _unauthorized("Access token suresi dolmus.") from exc
    except InvalidAccessToken as exc:
        raise _unauthorized("Access token gecersiz.") from exc
    except AuthProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kimlik saglayicisina su anda erisilemiyor.",
        ) from exc

    user_id = ensure_user.handle(identity)
    return CurrentActor(user_id=user_id)
