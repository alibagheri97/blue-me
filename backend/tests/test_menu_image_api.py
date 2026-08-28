from fastapi.testclient import TestClient


def test_menu_image_path_can_be_created_and_updated(
    client: TestClient, accounting_headers: dict[str, str]
):
    created = client.post(
        "/menu-items",
        headers=accounting_headers,
        json={
            "name": "Menu image API test",
            "category": "Test",
            "selling_price": "10000",
            "image_path": "/menu-images/original.webp",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["image_path"] == "/menu-images/original.webp"

    updated = client.patch(
        f"/menu-items/{created.json()['id']}",
        headers=accounting_headers,
        json={"image_path": "/menu-images/original.webp?v=20260828a"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["image_path"] == "/menu-images/original.webp?v=20260828a"

    visible = client.get(
        "/menu-items?include_inactive=true", headers=accounting_headers
    )
    assert visible.status_code == 200, visible.text
    saved = next(item for item in visible.json() if item["id"] == created.json()["id"])
    assert saved["image_path"] == "/menu-images/original.webp?v=20260828a"
