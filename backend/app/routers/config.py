from fastapi import APIRouter

from app.core.config import settings
from app.schemas import PublicConfig

router = APIRouter(tags=["configuration"])


@router.get("/public/config", response_model=PublicConfig)
def public_config() -> PublicConfig:
    return PublicConfig(
        app_name=settings.app_name,
        business_name=settings.business_name,
        tagline=settings.brand_tagline,
        primary_color=settings.brand_primary_color,
        logo_url=settings.brand_logo_url,
        locale=settings.app_locale,
        timezone=settings.app_timezone,
        currency_label=settings.currency_label,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
