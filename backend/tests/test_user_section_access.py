from fastapi.testclient import TestClient

from app.models import SectionKey

def user_by_username(
    client: TestClient, root_headers: dict[str, str], username: str
) -> dict:
    response = client.get("/users", headers=root_headers)
    assert response.status_code == 200, response.text
    return next(user for user in response.json() if user["username"] == username)


def login_headers(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_accounting_inherits_full_inventory_access_by_default(
    client: TestClient,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    me = client.get("/auth/me", headers=accounting_headers)
    assert me.status_code == 200, me.text
    assert "inventory" in me.json()["section_access"]

    category = client.post(
        "/inventory/categories",
        headers=accounting_headers,
        json={
            "name": "Accounting inventory access",
            "description": "Per-user access verification",
            "color": "#2563eb",
        },
    )
    assert category.status_code == 201, category.text

    item = client.post(
        "/inventory/items",
        headers=accounting_headers,
        json={
            "sku": "ACCOUNTING-ACCESS-001",
            "name": "Accounting managed item",
            "category_id": category.json()["id"],
            "unit": "عدد",
            "reorder_level": "0",
            "target_stock_level": "0",
            "purchase_quantity": "1",
            "purchase_unit": "عدد",
            "purchase_price": 0,
            "selling_quantity": "1",
            "selling_unit": "عدد",
            "selling_price": 0,
        },
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]

    detail = client.get(f"/inventory/items/{item_id}", headers=accounting_headers)
    assert detail.status_code == 200, detail.text
    updated = client.patch(
        f"/inventory/items/{item_id}",
        headers=accounting_headers,
        json={"name": "Accounting updated item"},
    )
    assert updated.status_code == 200, updated.text
    movement = client.post(
        f"/inventory/items/{item_id}/movements",
        headers=accounting_headers,
        json={
            "movement_type": "receive",
            "quantity": "5",
            "unit_cost": "10",
            "reason": "Accounting inventory permission test",
        },
    )
    assert movement.status_code == 201, movement.text

    price_change = client.patch(
        f"/inventory/items/{item_id}",
        headers=accounting_headers,
        json={
            "selling_quantity": "1",
            "selling_unit": "عدد",
            "selling_price": "125000",
            "price_change_reason": "Accounting proposed selling price",
        },
    )
    assert price_change.status_code == 200, price_change.text
    assert price_change.json()["selling_total_price"] == "0.00"
    pending_prices = client.get(
        "/inventory/price-requests?status=pending", headers=root_headers
    )
    assert pending_prices.status_code == 200, pending_prices.text
    assert any(
        request["item_id"] == item_id
        and request["price_type"] == "selling"
        for request in pending_prices.json()
    )

    listed = user_by_username(client, root_headers, "accounting")
    assert "inventory" in listed["section_access"]


def test_section_access_is_individual_and_revokes_existing_session_immediately(
    client: TestClient,
    root_headers: dict[str, str],
):
    granted = client.post(
        "/users",
        headers=root_headers,
        json={
            "username": "kitchen.reports",
            "full_name": "Kitchen Reports",
            "password": "kitchen-reports-password",
            "role": "kitchen_manager",
            "section_access": ["kitchen", "reports"],
        },
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["section_access"] == ["kitchen", "reports"]

    default_peer = client.post(
        "/users",
        headers=root_headers,
        json={
            "username": "kitchen.default",
            "full_name": "Kitchen Default",
            "password": "kitchen-default-password",
            "role": "kitchen_manager",
        },
    )
    assert default_peer.status_code == 201, default_peer.text
    assert default_peer.json()["section_access"] == ["kitchen"]

    granted_headers = login_headers(
        client, "kitchen.reports", "kitchen-reports-password"
    )
    peer_headers = login_headers(
        client, "kitchen.default", "kitchen-default-password"
    )
    assert client.get(
        "/reports/overview?days=7", headers=granted_headers
    ).status_code == 200
    assert client.get(
        "/reports/overview?days=7", headers=peer_headers
    ).status_code == 403

    revoked = client.patch(
        f"/users/{granted.json()['id']}",
        headers=root_headers,
        json={"section_access": ["kitchen"]},
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["section_access"] == ["kitchen"]
    assert client.get(
        "/reports/overview?days=7", headers=granted_headers
    ).status_code == 403


def test_all_operational_sections_can_be_granted_but_user_admin_stays_root_only(
    client: TestClient,
    root_headers: dict[str, str],
    storage_headers: dict[str, str],
):
    storage = user_by_username(client, root_headers, "storage")
    all_sections = [section.value for section in SectionKey]
    updated = client.patch(
        f"/users/{storage['id']}",
        headers=root_headers,
        json={"section_access": all_sections},
    )
    assert updated.status_code == 200, updated.text
    assert set(updated.json()["section_access"]) == set(all_sections)

    allowed_routes = (
        "/dashboard",
        "/staff",
        "/payroll/staff",
        "/inventory/price-requests",
        "/purchases",
        "/menu-items",
        "/customers",
        "/kitchen/orders",
        "/reports/overview?days=7",
        "/audit-logs",
    )
    for route in allowed_routes:
        response = client.get(route, headers=storage_headers)
        assert response.status_code == 200, (route, response.text)

    assert client.get("/users", headers=storage_headers).status_code == 403
    assert client.get("/attendance", headers=storage_headers).status_code == 403
    assert client.patch(
        "/settings",
        headers=storage_headers,
        json={"kitchen_workflow_enabled": False},
    ).status_code == 403


def test_empty_access_denies_sections_and_unknown_keys_are_rejected(
    client: TestClient,
    root_headers: dict[str, str],
    accounting_headers: dict[str, str],
):
    accounting = user_by_username(client, root_headers, "accounting")
    without_inventory = [
        "dashboard",
        "staff",
        "purchases",
        "menu",
        "pos",
        "reports",
    ]
    inventory_revoked = client.patch(
        f"/users/{accounting['id']}",
        headers=root_headers,
        json={"section_access": without_inventory},
    )
    assert inventory_revoked.status_code == 200, inventory_revoked.text
    assert "inventory" not in client.get(
        "/auth/me", headers=accounting_headers
    ).json()["section_access"]
    assert client.get(
        "/inventory/price-requests", headers=accounting_headers
    ).status_code == 403
    assert client.get("/purchases", headers=accounting_headers).status_code == 200

    emptied = client.patch(
        f"/users/{accounting['id']}",
        headers=root_headers,
        json={"section_access": []},
    )
    assert emptied.status_code == 200, emptied.text
    assert emptied.json()["section_access"] == []
    assert client.get("/dashboard", headers=accounting_headers).status_code == 403
    assert client.get("/inventory/items", headers=accounting_headers).status_code == 403
    assert client.get("/purchases", headers=accounting_headers).status_code == 403

    invalid = client.patch(
        f"/users/{accounting['id']}",
        headers=root_headers,
        json={"section_access": ["inventory", "users"]},
    )
    assert invalid.status_code == 422
