from fastapi import APIRouter, Depends

from src.auth import require_user
from src.interfaces.admin_service import IAdminService
from src.models.user import User
from src.schemas.admin import CategoryOut
from src.services.admin_service import get_admin_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "",
    response_model=list[CategoryOut],
    summary="List all categories",
)
async def list_categories(
    _user: User = Depends(require_user),
    admin_service: IAdminService = Depends(get_admin_service),
):
    """Every authenticated user can access every category. Used by the frontend to
    populate the upload/filter and the chat-creation category pickers."""
    return admin_service.list_categories()
