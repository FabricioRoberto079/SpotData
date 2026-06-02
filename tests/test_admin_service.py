import pytest

from src.enums.user_role import UserRole
from src.exceptions import ConflictError, NotFoundError, ValidationError
from src.models.user import User
from src.services.access import allowed_category_ids
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
    # two words -> single underscore, UPPERCASE
    assert normalize_category_name("Recursos Humanos") == "RECURSOS_HUMANOS"
    # leading/trailing trimmed, multiple inner spaces collapse to one underscore
    assert normalize_category_name("   Recursos    Humanos   ") == "RECURSOS_HUMANOS"
    # special characters and accents removed
    assert normalize_category_name("Jurídico/Contratos!") == "JURIDICOCONTRATOS"
    assert normalize_category_name("Pós-Vendas") == "POSVENDAS"
    # single word
    assert normalize_category_name("financeiro") == "FINANCEIRO"
    # nothing usable
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
        svc.create_category("  financeiro ")  # normalizes to the same slug


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


def test_assign_is_idempotent_and_listable(session):
    svc = AdminService(session)
    _seed_user(session, "u1")
    cat = svc.create_category("RH")
    svc.assign_category("u1", cat["id"])
    svc.assign_category("u1", cat["id"])  # idempotent
    linked = svc.categories_for_user("u1")
    assert [c["id"] for c in linked] == [cat["id"]]


def test_unassign_removes_link(session):
    svc = AdminService(session)
    _seed_user(session, "u1")
    cat = svc.create_category("RH")
    svc.assign_category("u1", cat["id"])
    svc.unassign_category("u1", cat["id"])
    assert svc.categories_for_user("u1") == []


def test_assign_unknown_user_raises(session):
    svc = AdminService(session)
    cat = svc.create_category("RH")
    with pytest.raises(NotFoundError):
        svc.assign_category("ghost", cat["id"])


def test_set_user_role_and_active(session):
    svc = AdminService(session)
    _seed_user(session, "u1")
    promoted = svc.set_user_role("u1", UserRole.EDITOR)
    assert promoted["role"] == "editor"
    disabled = svc.set_user_active("u1", False)
    assert disabled["is_active"] is False


def test_allowed_category_ids_admin_is_unrestricted(session):
    admin = _seed_user(session, "admin", role=UserRole.ADMIN)
    assert allowed_category_ids(session, admin) is None


def test_allowed_category_ids_scopes_non_admin(session):
    svc = AdminService(session)
    viewer = _seed_user(session, "v1", role=UserRole.VIEWER)
    a = svc.create_category("A")
    b = svc.create_category("B")
    svc.assign_category("v1", a["id"])
    ids = allowed_category_ids(session, viewer)
    assert ids == [a["id"]]
    assert b["id"] not in ids
