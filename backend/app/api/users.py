from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import User
from app.schemas import MeRead

router = APIRouter(prefix="/api", tags=["users"])


@router.get("/me", response_model=MeRead)
async def read_me(current_user: User = Depends(get_current_user)) -> MeRead:
    """The caller's account and personal dashboard link.

    The bot uses it to build the /dashboard reply; the dashboard uses it to
    check its stored token is still valid before rendering the board.
    """
    settings = get_settings()
    base = settings.dashboard_base_url.rstrip("/")
    return MeRead(
        id=current_user.id,
        telegram_id=current_user.telegram_id,
        username=current_user.username,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        access_token=current_user.access_token,
        dashboard_url=f"{base}/?token={current_user.access_token}",
    )
