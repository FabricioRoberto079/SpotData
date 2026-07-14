from fastapi import APIRouter, Depends

from src.auth import require_admin
from src.models.user import User
from src.schemas.admin import (
    AdminUserOut,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    UserActiveUpdate,
    UserRoleUpdate,
)
from src.schemas.system import MessageResponse
from src.services.admin_service import AdminService, get_admin_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post("/categories", response_model=CategoryOut, summary="Create a category")
async def create_category(
    payload: CategoryCreate,
    current_user: User = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.create_category(payload.name, created_by=current_user.id)


@router.get("/categories", response_model=list[CategoryOut], summary="List all categories")
async def list_categories(
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.list_categories()


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryOut,
    summary="Rename a category and/or change its slug",
)
async def update_category(
    category_id: str,
    payload: CategoryUpdate,
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.update_category(category_id, payload.model_dump(exclude_unset=True))


@router.delete(
    "/categories/{category_id}",
    response_model=MessageResponse,
    summary="Delete a category",
)
async def delete_category(
    category_id: str,
    admin_service: AdminService = Depends(get_admin_service),
):
    admin_service.delete_category(category_id)
    return {"message": "Category removed."}


@router.get("/users", response_model=list[AdminUserOut], summary="List all users")
async def list_users(
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.list_users()


@router.patch(
    "/users/{user_id}/role",
    response_model=AdminUserOut,
    summary="Change a user's role",
)
async def set_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.set_user_role(user_id, payload.role)


@router.patch(
    "/users/{user_id}/active",
    response_model=AdminUserOut,
    summary="Activate or deactivate a user",
)
async def set_user_active(
    user_id: str,
    payload: UserActiveUpdate,
    admin_service: AdminService = Depends(get_admin_service),
):
    return admin_service.set_user_active(user_id, payload.is_active)
