from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.cli import (
    LEGACY_DRAFT_DESCRIPTION,
    MENU_PRODUCT_IMAGES,
    MENU_PRODUCTS,
    seed_catalog_data,
)
from app.models import InventoryItem, MenuItem, Recipe, RecipeIngredient, User, UserRole


EXPECTED_PRICES = {
    "شاورما مرغ": 395000,
    "شاورما گوشت": 495000,
    "شاورما میکس": 450000,
    "شاورما مرغ پنیری": 450000,
    "شاورما گوشت پنیری": 550000,
    "شاورما میکس پنیری": 495000,
    "شاورما مرغ عربی": 550000,
    "شاورما گوشت عربی": 650000,
    "شاورما میکس عربی": 595000,
    "بمب مرغ": 530000,
    "بمب گوشت": 630000,
    "بمب میکس": 595000,
    "سیب زمینی": 190000,
    "نان شاورما اضافه": 35000,
    "سس لبنانی": 15000,
    "سس سیر": 15000,
    "سس باربیکیو": 25000,
    "کچاپ": 15000,
    "آب معدنی": 25000,
    "کوکاکولا": 85000,
    "فانتا": 85000,
    "نوشابه بزرگ زم‌زم": 110000,
    "لیموناد شیشه‌ای": 75000,
}

DIRECT_SALES = {
    "نان شاورما اضافه": ("نان", Decimal("1")),
    "کچاپ": ("سس کچاپ", Decimal("30")),
    "آب معدنی": ("آب معدنی کوچک", Decimal("1")),
    "کوکاکولا": ("نوشابه قوطی کوکاکولا", Decimal("1")),
    "فانتا": ("نوشابه قوطی فانتا", Decimal("1")),
    "نوشابه بزرگ زم‌زم": ("نوشابه بزرگ زم‌زم", Decimal("1")),
    "لیموناد شیشه‌ای": ("نوشابه لیموناد شیشه‌ای", Decimal("1")),
}

PUBLIC_ASSET_ROOT = Path(__file__).resolve().parents[2] / "frontend" / "public"


def _root(db_session: Session) -> User:
    root = db_session.scalar(select(User).where(User.role == UserRole.ROOT))
    assert root is not None
    return root


def _production_menu(db_session: Session) -> dict[str, MenuItem]:
    names = set(EXPECTED_PRICES)
    items = db_session.scalars(
        select(MenuItem)
        .where(MenuItem.name.in_(names))
        .options(
            selectinload(MenuItem.inventory_item),
            selectinload(MenuItem.recipe)
            .selectinload(Recipe.ingredients)
            .selectinload(RecipeIngredient.inventory_item),
        )
    ).unique()
    return {item.name: item for item in items}


def test_seed_installs_exact_production_menu_and_preserves_later_edits(
    db_session: Session,
):
    first = seed_catalog_data(db_session, _root(db_session))
    db_session.commit()

    assert len(MENU_PRODUCTS) == 23
    assert set(MENU_PRODUCT_IMAGES) == set(EXPECTED_PRICES)
    assert first["menu_items_created"] == 23
    assert first["menu_images_configured"] == 23
    assert first["recipes_configured"] == 16

    menu = _production_menu(db_session)
    assert set(menu) == set(EXPECTED_PRICES)
    for name, price in EXPECTED_PRICES.items():
        assert menu[name].selling_price == Decimal(price)
        assert menu[name].is_active is True
        expected_path = f"/menu-images/{MENU_PRODUCT_IMAGES[name]}"
        assert menu[name].image_path == expected_path
        image_file = PUBLIC_ASSET_ROOT / expected_path.lstrip("/")
        image_data = image_file.read_bytes()
        assert image_data[:4] == b"RIFF"
        assert image_data[8:12] == b"WEBP"
        assert len(image_data) <= 150_000

    for name, (inventory_name, quantity) in DIRECT_SALES.items():
        item = menu[name]
        assert item.inventory_item is not None
        assert item.inventory_item.name == inventory_name
        assert item.stock_quantity_per_sale == quantity
        assert item.recipe is None

    recipe_items = set(menu) - set(DIRECT_SALES)
    assert len(recipe_items) == 16
    for name in recipe_items:
        item = menu[name]
        assert item.inventory_item_id is None
        assert item.recipe is not None
        assert item.recipe.yield_quantity == Decimal("1")
        assert item.recipe.ingredients
        assert all(
            ingredient.unit == ingredient.inventory_item.unit
            for ingredient in item.recipe.ingredients
        )

    chicken_recipe = {
        ingredient.inventory_item.name: ingredient.quantity
        for ingredient in menu["شاورما مرغ"].recipe.ingredients
    }
    assert chicken_recipe["سینه مرغ"] == Decimal("100")
    assert chicken_recipe["نان"] == Decimal("1")
    assert chicken_recipe["نمک"] == Decimal("2")
    cheese_recipe = {
        ingredient.inventory_item.name: ingredient.quantity
        for ingredient in menu["شاورما مرغ پنیری"].recipe.ingredients
    }
    assert cheese_recipe["پنیر پیتزا"] == Decimal("20")

    zamzam = db_session.scalar(
        select(InventoryItem).where(InventoryItem.name == "نوشابه بزرگ زم‌زم")
    )
    assert zamzam is not None
    assert zamzam.average_cost == Decimal("0")
    assert zamzam.last_purchase_price == Decimal("0")

    takeaway_supplies = {
        item.name: item
        for item in db_session.scalars(
            select(InventoryItem).where(
                InventoryItem.name.in_(
                    {
                        "ظرف آلومینیومی",
                        "خلال دندان",
                        "دستمال کاغذی",
                        "پاکت بیرون‌بر",
                        "قاشق و چنگال یک‌بارمصرف",
                    }
                )
            )
        )
    }
    assert set(takeaway_supplies) == {
        "ظرف آلومینیومی",
        "خلال دندان",
        "دستمال کاغذی",
        "پاکت بیرون‌بر",
        "قاشق و چنگال یک‌بارمصرف",
    }
    assert all(item.category.name == "بسته‌بندی" for item in takeaway_supplies.values())
    assert all(item.unit == "عدد" for item in takeaway_supplies.values())

    menu["شاورما مرغ"].selling_price = Decimal("410000")
    menu["شاورما مرغ"].image_path = "/menu-images/custom-chicken.webp"
    chicken_ingredient = next(
        ingredient
        for ingredient in menu["شاورما مرغ"].recipe.ingredients
        if ingredient.inventory_item.name == "سینه مرغ"
    )
    chicken_ingredient.quantity = Decimal("110")
    db_session.commit()

    second = seed_catalog_data(db_session, _root(db_session))
    db_session.commit()
    assert not any(second.values())
    preserved = _production_menu(db_session)["شاورما مرغ"]
    assert preserved.selling_price == Decimal("410000")
    assert preserved.image_path == "/menu-images/custom-chicken.webp"
    assert next(
        ingredient.quantity
        for ingredient in preserved.recipe.ingredients
        if ingredient.inventory_item.name == "سینه مرغ"
    ) == Decimal("110")

    forced = seed_catalog_data(db_session, _root(db_session), force=True)
    db_session.commit()
    assert forced["menu_items_configured"] == 23
    assert forced["recipes_configured"] == 16
    restored = _production_menu(db_session)["شاورما مرغ"]
    assert restored.selling_price == Decimal("395000")
    assert restored.image_path == "/menu-images/custom-chicken.webp"
    assert next(
        ingredient.quantity
        for ingredient in restored.recipe.ingredients
        if ingredient.inventory_item.name == "سینه مرغ"
    ) == Decimal("100")


def test_seed_migrates_legacy_draft_without_changing_its_id(db_session: Session):
    legacy = MenuItem(
        name="شاورما مرغ ساده",
        category="شاورما",
        selling_price=Decimal("0"),
        is_active=False,
        description=LEGACY_DRAFT_DESCRIPTION,
    )
    db_session.add(legacy)
    db_session.commit()
    legacy_id = legacy.id

    result = seed_catalog_data(db_session, _root(db_session))
    db_session.commit()

    migrated = db_session.get(MenuItem, legacy_id)
    assert result["legacy_menu_items_migrated"] == 1
    assert migrated is not None
    assert migrated.name == "شاورما مرغ"
    assert migrated.selling_price == Decimal("395000")
    assert migrated.is_active is True
    assert migrated.recipe is not None


def test_seeded_order_deducts_the_full_recipe(
    client: TestClient,
    db_session: Session,
    accounting_headers: dict[str, str],
):
    seed_catalog_data(db_session, _root(db_session))
    for inventory_item in db_session.scalars(select(InventoryItem)):
        inventory_item.current_quantity = Decimal("100000")
    db_session.commit()

    menu = _production_menu(db_session)
    chicken = db_session.scalar(
        select(InventoryItem).where(InventoryItem.name == "سینه مرغ")
    )
    bread = db_session.scalar(select(InventoryItem).where(InventoryItem.name == "نان"))
    assert chicken is not None and bread is not None
    chicken_before = chicken.current_quantity
    bread_before = bread.current_quantity

    visible_menu = client.get("/menu-items?active=true", headers=accounting_headers)
    assert visible_menu.status_code == 200, visible_menu.text
    visible_items = visible_menu.json()
    assert set(EXPECTED_PRICES).issubset({item["name"] for item in visible_items})
    production_items = [
        item for item in visible_items if item["name"] in EXPECTED_PRICES
    ]
    assert len(production_items) == 23
    assert all(
        item["image_path"].startswith("/menu-images/") for item in production_items
    )

    order = client.post(
        "/orders",
        headers=accounting_headers,
        json={
            "items": [{"menu_item_id": menu["شاورما مرغ"].id, "quantity": 2}],
            "payment_method": "cash",
        },
    )
    assert order.status_code == 201, order.text
    assert Decimal(order.json()["total"]) == Decimal("790000")

    db_session.expire_all()
    assert (
        db_session.get(InventoryItem, chicken.id).current_quantity
        == chicken_before - 200
    )
    assert db_session.get(InventoryItem, bread.id).current_quantity == bread_before - 2
