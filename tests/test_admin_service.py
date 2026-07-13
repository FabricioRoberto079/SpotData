import pytest

from src.enums.user_role import UserRole
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.user import User
from src.services.admin_service import AdminService, normalize_category_name


def _seed_user(session, user_id, role=UserRole.VIEWER):
    user = User(
        id=user_id,
        name=user_id,
        email=f"{user_id}@x.com",
        role=role.value,
        password_hash="!disabled!",
    )
    session.add(user)
    session.commit()
    return user


def test_normalize_category_name():
    assert normalize_category_name("Recursos Humanos") == "RECURSOS_HUMANOS"
    assert normalize_category_name("   Recursos    Humanos   ") == "RECURSOS_HUMANOS"
    assert normalize_category_name("Jurídico/Contratos!") == "JURIDICOCONTRATOS"
    assert normalize_category_name("Pós-Vendas") == "POSVENDAS"
    assert normalize_category_name("financeiro") == "FINANCEIRO"
    assert normalize_category_name("  @#$  ") == ""


def test_create_category_normalizes_name_and_slug(session):
    svc = AdminService(session)
    cat = svc.create_category("  Recursos   Humanos!  ")
    assert cat["name"] == "RECURSOS_HUMANOS"
    assert cat["slug"] == "recursos_humanos"


def test_create_category_empty_after_normalization_raises(session):
    svc = AdminService(session)
    with pytest.raises(ValidationError):
        svc.create_category("@#$%")


def test_create_category_duplicate_conflicts(session):
    svc = AdminService(session)
    svc.create_category("Financeiro")
    with pytest.raises(ConflictError):
        svc.create_category("  financeiro ")


def test_update_category_renames_and_renormalizes(session):
    svc = AdminService(session)
    cat = svc.create_category("Financeiro")
    updated = svc.update_category(cat["id"], {"name": "Contas a Pagar"})
    assert updated["name"] == "CONTAS_A_PAGAR"
    assert updated["slug"] == "contas_a_pagar"


def test_delete_missing_category_raises(session):
    svc = AdminService(session)
    with pytest.raises(NotFoundError):
        svc.delete_category("nope")


def test_set_user_role_and_active(session):
    svc = AdminService(session)
    _seed_user(session, "u1")
    promoted = svc.set_user_role("u1", UserRole.EDITOR)
    assert promoted["role"] == "editor"
    disabled = svc.set_user_active("u1", False)
    assert disabled["is_active"] is False
