from fastapi import APIRouter, Depends

from src.auth import require_user
from src.enums.user_role import UserRole
from src.interfaces.admin_service import IAdminService
from src.models.user import User
from src.schemas.admin import CategoryOut
from src.services.admin_service import get_admin_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(
    "",
    response_model=list[CategoryOut],
    summary="List the categories the current user can access",
)
async def list_my_categories(
    current_user: User = Depends(require_user),
    admin_service: IAdminService = Depends(get_admin_service),
):
    """Admins see every category; everyone else sees only the ones they are linked
    to. Used by the frontend to populate the upload/filter category pickers."""
    if current_user.role == UserRole.ADMIN.value:
        return admin_service.list_categories()
    return admin_service.categories_for_user(current_user.id)
