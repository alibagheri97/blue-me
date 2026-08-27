import argparse
import sys
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    Category,
    InventoryItem,
    MenuCategory,
    MenuItem,
    Recipe,
    RecipeIngredient,
    User,
    UserRole,
)


CATALOG_CATEGORIES = [
    ("نان و غلات", "نان و اقلام پایه", "#f59e0b"),
    ("روغن، ادویه و چاشنی", "روغن، ادویه، پودرها و چاشنی‌ها", "#ef4444"),
    ("پروتئین", "گوشت و مرغ", "#dc2626"),
    ("سس‌ها", "سس‌های آماده و مواد پایه سس", "#f97316"),
    ("سبزیجات", "سبزی و صیفی‌جات تازه", "#22c55e"),
    ("لبنیات", "ماست و پنیر", "#8b5cf6"),
    ("نوشیدنی", "نوشیدنی‌های قابل فروش", "#06b6d4"),
]

CATALOG_ITEMS = [
    ("SHW-001", "نان", "نان و غلات", "عدد"),
    ("SHW-002", "روغن", "روغن، ادویه و چاشنی", "میلی‌لیتر"),
    ("SHW-003", "نمک", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-004", "فلفل سیاه", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-005", "فلفل قرمز", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-006", "آویشن", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-007", "گوشت", "پروتئین", "گرم"),
    ("SHW-008", "سینه مرغ", "پروتئین", "گرم"),
    ("SHW-009", "سس مایونز", "سس‌ها", "گرم"),
    ("SHW-010", "سس کچاپ", "سس‌ها", "گرم"),
    ("SHW-011", "ماست", "لبنیات", "گرم"),
    ("SHW-012", "جعفری", "سبزیجات", "گرم"),
    ("SHW-013", "پیاز", "سبزیجات", "گرم"),
    ("SHW-014", "سس تند همدانیان", "سس‌ها", "گرم"),
    ("SHW-015", "سس تند گلوریا", "سس‌ها", "گرم"),
    ("SHW-016", "کلم", "سبزیجات", "گرم"),
    ("SHW-017", "سیر", "سبزیجات", "گرم"),
    ("SHW-018", "فلفل دلمه‌ای", "سبزیجات", "گرم"),
    ("SHW-019", "نوشابه قوطی پپسی", "نوشیدنی", "عدد"),
    ("SHW-020", "نوشابه قوطی کوکاکولا", "نوشیدنی", "عدد"),
    ("SHW-021", "نوشابه قوطی فانتا", "نوشیدنی", "عدد"),
    ("SHW-022", "آب معدنی کوچک", "نوشیدنی", "عدد"),
    ("SHW-023", "آب‌لیمو", "روغن، ادویه و چاشنی", "میلی‌لیتر"),
    ("SHW-024", "گوجه", "سبزیجات", "گرم"),
    ("SHW-025", "خیار", "سبزیجات", "گرم"),
    ("SHW-026", "پنیر پیتزا", "لبنیات", "گرم"),
    ("SHW-027", "ماست سون", "لبنیات", "گرم"),
    ("SHW-028", "پودر سیر", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-029", "پودر گشنیز", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-030", "پودر زنجبیل", "روغن، ادویه و چاشنی", "گرم"),
    ("SHW-031", "سس گوجه", "سس‌ها", "گرم"),
    ("SHW-032", "آب معدنی بزرگ", "نوشیدنی", "عدد"),
    ("SHW-033", "نوشابه لیموناد شیشه‌ای", "نوشیدنی", "عدد"),
    ("SHW-034", "دلستر انگور بزرگ", "نوشیدنی", "عدد"),
    ("SHW-035", "سیب زمینی", "سبزیجات", "گرم"),
    ("SHW-036", "نوشابه بزرگ زم‌زم", "نوشیدنی", "عدد"),
]

MENU_CATEGORIES = [
    ("شاورما", "انواع شاورمای مرغ، گوشت و میکس", "#ef4444", 10),
    ("بمب", "ساندویچ‌های ویژه و حجیم", "#f97316", 15),
    ("پیش‌غذا", "سیب‌زمینی و مخلفات", "#f59e0b", 20),
    ("سس", "سس‌های قابل سفارش", "#8b5cf6", 30),
    ("نوشیدنی", "نوشیدنی‌های سرد", "#06b6d4", 40),
]

LEGACY_DRAFT_DESCRIPTION = "پیش‌نویس اولیه؛ قیمت و دستور پخت را تکمیل کنید."
PRODUCTION_RECIPE_NOTES = (
    "مقادیر برای یک خروجی است و هنگام ثبت سفارش به‌صورت خودکار از انبار کسر می‌شود. "
    "نسخه پایه تولید ۱؛ اصلاحات بعدی از مدیریت دستور پخت انجام شود."
)


@dataclass(frozen=True)
class MenuProductSpec:
    name: str
    selling_price: int
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    direct_inventory_name: str | None = None
    stock_quantity_per_sale: str = "1"
    ingredients: tuple[tuple[str, str], ...] = ()
    preparation_minutes: int = 0
    instructions: str = ""


def _shawarma_ingredients(
    *,
    chicken: str | None = None,
    beef: str | None = None,
    style: str = "standard",
    cheese: bool = False,
) -> tuple[tuple[str, str], ...]:
    protein = tuple(
        (name, quantity)
        for name, quantity in (("سینه مرغ", chicken), ("گوشت", beef))
        if quantity is not None
    )
    if style == "arabic":
        return protein + (
            ("نان", "2"),
            ("سیب زمینی", "120"),
            ("کلم", "30"),
            ("گوجه", "25"),
            ("پیاز", "20"),
            ("سس مایونز", "25"),
            ("سس کچاپ", "15"),
            ("روغن", "10"),
            ("نمک", "2"),
            ("فلفل سیاه", "0.7"),
            ("آویشن", "0.7"),
            ("پودر سیر", "0.5"),
        )
    if style == "bomb":
        return protein + (
            ("نان", "2"),
            ("سیب زمینی", "120"),
            ("پنیر پیتزا", "40"),
            ("کلم", "35"),
            ("گوجه", "25"),
            ("پیاز", "20"),
            ("سس مایونز", "30"),
            ("سس کچاپ", "20"),
            ("سس تند گلوریا", "5"),
            ("روغن", "10"),
            ("نمک", "2"),
            ("فلفل سیاه", "0.7"),
            ("آویشن", "0.7"),
        )
    additions: tuple[tuple[str, str], ...] = (("پنیر پیتزا", "20"),) if cheese else ()
    return (
        protein
        + (
            ("نان", "1"),
            ("کلم", "25"),
            ("گوجه", "20"),
            ("پیاز", "15"),
            ("سس مایونز", "15"),
            ("سس کچاپ", "10"),
            ("روغن", "5"),
            ("نمک", "2"),
            ("فلفل سیاه", "0.5"),
            ("آویشن", "0.5"),
        )
        + additions
    )


def _recipe_product(
    name: str,
    selling_price: int,
    category: str,
    ingredients: tuple[tuple[str, str], ...],
    *,
    aliases: tuple[str, ...] = (),
    preparation_minutes: int,
    instructions: str,
) -> MenuProductSpec:
    return MenuProductSpec(
        name=name,
        selling_price=selling_price,
        category=category,
        description=f"{name}؛ یک خروجی استاندارد با کسر خودکار مواد اولیه از انبار.",
        aliases=aliases,
        ingredients=ingredients,
        preparation_minutes=preparation_minutes,
        instructions=instructions,
    )


def _direct_product(
    name: str,
    selling_price: int,
    category: str,
    inventory_name: str,
    *,
    aliases: tuple[str, ...] = (),
    quantity: str = "1",
) -> MenuProductSpec:
    return MenuProductSpec(
        name=name,
        selling_price=selling_price,
        category=category,
        description=f"{name}؛ کسر مستقیم از موجودی انبار در هر فروش.",
        aliases=aliases,
        direct_inventory_name=inventory_name,
        stock_quantity_per_sale=quantity,
    )


STANDARD_INSTRUCTIONS = (
    "پروتئین وزن‌شده را طبق استاندارد آشپزخانه بپزید؛ نان را گرم کنید، "
    "سبزیجات و سس‌های اندازه‌گیری‌شده را اضافه کنید و یک پرس تحویل دهید."
)
ARABIC_INSTRUCTIONS = (
    "پروتئین وزن‌شده را بپزید، همراه نان برش‌خورده و سیب‌زمینی در ظرف عربی بچینید، "
    "سبزیجات و سس‌های اندازه‌گیری‌شده را اضافه کنید."
)
BOMB_INSTRUCTIONS = (
    "پروتئین و سیب‌زمینی را آماده کنید؛ دو نان را با پنیر، سبزیجات و سس‌های "
    "اندازه‌گیری‌شده پر کنید و پرس بمب را کامل ببندید."
)


MENU_PRODUCTS = (
    _recipe_product(
        "شاورما مرغ",
        395000,
        "شاورما",
        _shawarma_ingredients(chicken="100"),
        aliases=("شاورما مرغ ساده", "شاوما مرغ"),
        preparation_minutes=8,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما گوشت",
        495000,
        "شاورما",
        _shawarma_ingredients(beef="100"),
        aliases=("شاورما گوشت ساده", "گوشت"),
        preparation_minutes=8,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما میکس",
        450000,
        "شاورما",
        _shawarma_ingredients(chicken="50", beef="50"),
        aliases=("میکس",),
        preparation_minutes=8,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما مرغ پنیری",
        450000,
        "شاورما",
        _shawarma_ingredients(chicken="100", cheese=True),
        aliases=("شاورما مرغ با پنیر", "مرغ پنیری"),
        preparation_minutes=9,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما گوشت پنیری",
        550000,
        "شاورما",
        _shawarma_ingredients(beef="100", cheese=True),
        aliases=("شاورما گوشت با پنیر", "گوشت پنیری"),
        preparation_minutes=9,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما میکس پنیری",
        495000,
        "شاورما",
        _shawarma_ingredients(chicken="50", beef="50", cheese=True),
        aliases=("شاورما میکس با پنیر", "میکس پنیری"),
        preparation_minutes=9,
        instructions=STANDARD_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما مرغ عربی",
        550000,
        "شاورما",
        _shawarma_ingredients(chicken="130", style="arabic"),
        aliases=("شاورما عربی مرغ", "مرغ عربی", "موغ عربی"),
        preparation_minutes=12,
        instructions=ARABIC_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما گوشت عربی",
        650000,
        "شاورما",
        _shawarma_ingredients(beef="130", style="arabic"),
        aliases=("شاورما عربی گوشت", "گوشت عربی"),
        preparation_minutes=12,
        instructions=ARABIC_INSTRUCTIONS,
    ),
    _recipe_product(
        "شاورما میکس عربی",
        595000,
        "شاورما",
        _shawarma_ingredients(chicken="65", beef="65", style="arabic"),
        aliases=("شاورما عربی میکس", "میکس عربی"),
        preparation_minutes=12,
        instructions=ARABIC_INSTRUCTIONS,
    ),
    _recipe_product(
        "بمب مرغ",
        530000,
        "بمب",
        _shawarma_ingredients(chicken="150", style="bomb"),
        preparation_minutes=14,
        instructions=BOMB_INSTRUCTIONS,
    ),
    _recipe_product(
        "بمب گوشت",
        630000,
        "بمب",
        _shawarma_ingredients(beef="150", style="bomb"),
        preparation_minutes=14,
        instructions=BOMB_INSTRUCTIONS,
    ),
    _recipe_product(
        "بمب میکس",
        595000,
        "بمب",
        _shawarma_ingredients(chicken="75", beef="75", style="bomb"),
        preparation_minutes=14,
        instructions=BOMB_INSTRUCTIONS,
    ),
    _recipe_product(
        "سیب زمینی",
        190000,
        "پیش‌غذا",
        (("سیب زمینی", "250"), ("روغن", "20"), ("نمک", "2"), ("فلفل سیاه", "0.5")),
        preparation_minutes=10,
        instructions="سیب‌زمینی وزن‌شده را سرخ کنید، روغن اضافه را بگیرید و ادویه اندازه‌گیری‌شده را بیفزایید.",
    ),
    _direct_product("نان شاورما اضافه", 35000, "پیش‌غذا", "نان"),
    _recipe_product(
        "سس لبنانی",
        15000,
        "سس",
        (
            ("ماست", "20"),
            ("سس مایونز", "20"),
            ("آب‌لیمو", "3"),
            ("سیر", "2"),
            ("نمک", "0.5"),
            ("جعفری", "2"),
        ),
        preparation_minutes=2,
        instructions="مواد وزن‌شده را تا بافت یکنواخت مخلوط کرده و یک ظرف سس تحویل دهید.",
    ),
    _recipe_product(
        "سس سیر",
        15000,
        "سس",
        (
            ("سس مایونز", "30"),
            ("ماست", "10"),
            ("سیر", "3"),
            ("آب‌لیمو", "3"),
            ("نمک", "0.5"),
            ("روغن", "2"),
        ),
        preparation_minutes=2,
        instructions="مواد وزن‌شده را کاملاً یکدست کرده و یک ظرف سس تحویل دهید.",
    ),
    _recipe_product(
        "سس باربیکیو",
        25000,
        "سس",
        (
            ("سس گوجه", "25"),
            ("سس کچاپ", "20"),
            ("سس تند گلوریا", "2"),
            ("آب‌لیمو", "2"),
            ("پودر سیر", "0.5"),
            ("فلفل سیاه", "0.2"),
            ("فلفل قرمز", "0.2"),
        ),
        preparation_minutes=2,
        instructions="مواد وزن‌شده را تا رسیدن به رنگ و غلظت یکنواخت مخلوط کرده و یک ظرف تحویل دهید.",
    ),
    _direct_product(
        "کچاپ", 15000, "سس", "سس کچاپ", aliases=("سس کچاپ",), quantity="30"
    ),
    _direct_product(
        "آب معدنی", 25000, "نوشیدنی", "آب معدنی کوچک", aliases=("آب معدنی کوچک",)
    ),
    _direct_product(
        "کوکاکولا",
        85000,
        "نوشیدنی",
        "نوشابه قوطی کوکاکولا",
        aliases=("نوشابه قوطی کوکاکولا",),
    ),
    _direct_product(
        "فانتا", 85000, "نوشیدنی", "نوشابه قوطی فانتا", aliases=("نوشابه قوطی فانتا",)
    ),
    _direct_product("نوشابه بزرگ زم‌زم", 110000, "نوشیدنی", "نوشابه بزرگ زم‌زم"),
    _direct_product(
        "لیموناد شیشه‌ای",
        75000,
        "نوشیدنی",
        "نوشابه لیموناد شیشه‌ای",
        aliases=("نوشابه لیموناد شیشه‌ای",),
    ),
)

MENU_PRODUCT_IMAGES: dict[str, str] = {
    "شاورما مرغ": "shawarma-chicken.webp",
    "شاورما گوشت": "shawarma-beef.webp",
    "شاورما میکس": "shawarma-mixed.webp",
    "شاورما مرغ پنیری": "shawarma-chicken-cheese.webp",
    "شاورما گوشت پنیری": "shawarma-beef-cheese.webp",
    "شاورما میکس پنیری": "shawarma-mixed-cheese.webp",
    "شاورما مرغ عربی": "shawarma-chicken-arabic.webp",
    "شاورما گوشت عربی": "shawarma-beef-arabic.webp",
    "شاورما میکس عربی": "shawarma-mixed-arabic.webp",
    "بمب مرغ": "bomb-chicken.webp",
    "بمب گوشت": "bomb-beef.webp",
    "بمب میکس": "bomb-mixed.webp",
    "سیب زمینی": "french-fries.webp",
    "نان شاورما اضافه": "extra-pita-bread.webp",
    "سس لبنانی": "lebanese-sauce.webp",
    "سس سیر": "garlic-sauce.webp",
    "سس باربیکیو": "barbecue-sauce.webp",
    "کچاپ": "ketchup.webp",
    "آب معدنی": "mineral-water.webp",
    "کوکاکولا": "coca-cola.webp",
    "فانتا": "fanta.webp",
    "نوشابه بزرگ زم‌زم": "zamzam-cola.webp",
    "لیموناد شیشه‌ای": "glass-lemonade.webp",
}


def bootstrap() -> None:
    if len(settings.root_password) < 12:
        raise RuntimeError("ROOT_PASSWORD must contain at least 12 characters")
    if len(settings.app_secret_key) < 32:
        raise RuntimeError("APP_SECRET_KEY must contain at least 32 characters")
    with SessionLocal() as db:
        root = db.scalar(select(User).where(User.role == UserRole.ROOT))
        if root is None:
            if db.scalar(
                select(User.id).where(User.username == settings.root_username)
            ):
                raise RuntimeError(
                    "ROOT_USERNAME is already used by a non-root account"
                )
            root = User(
                username=settings.root_username,
                full_name=settings.root_full_name,
                password_hash=hash_password(settings.root_password),
                role=UserRole.ROOT,
            )
            db.add(root)
            db.flush()
            record_audit(
                db,
                actor=root,
                action="bootstrap",
                category="system",
                entity_type="user",
                entity_id=root.id,
                summary="Created deployment root account",
            )
            print(f"Created root account: {root.username}")
        else:
            print(f"Root account already exists: {root.username}")

        if not db.scalar(select(Category.id).limit(1)):
            db.add_all(
                [
                    Category(
                        name="مواد اولیه",
                        color="#2563eb",
                        description="مواد خام و اولیه آشپزخانه",
                    ),
                    Category(
                        name="نوشیدنی",
                        color="#06b6d4",
                        description="نوشیدنی‌ها و ملزومات آن‌ها",
                    ),
                    Category(
                        name="بسته‌بندی",
                        color="#8b5cf6",
                        description="لیوان، جعبه، پاکت و ظروف مصرفی",
                    ),
                    Category(
                        name="نظافت",
                        color="#10b981",
                        description="مواد شوینده و بهداشتی",
                    ),
                ]
            )
            print("Created starter inventory categories")
        db.commit()


def _configure_recipe(
    db: Session,
    *,
    root: User,
    menu_item: MenuItem,
    spec: MenuProductSpec,
    inventory_by_name: dict[str, InventoryItem],
) -> None:
    recipe = db.scalar(select(Recipe).where(Recipe.menu_item_id == menu_item.id))
    if recipe is None:
        recipe = Recipe(menu_item_id=menu_item.id, created_by_id=root.id)
        db.add(recipe)
        db.flush()
    else:
        recipe.ingredients.clear()

    recipe.yield_quantity = Decimal("1")
    recipe.preparation_minutes = spec.preparation_minutes
    recipe.instructions = spec.instructions
    recipe.notes = PRODUCTION_RECIPE_NOTES
    for inventory_name, quantity in spec.ingredients:
        inventory_item = inventory_by_name.get(inventory_name)
        if inventory_item is None:
            raise RuntimeError(f"Missing recipe inventory item: {inventory_name}")
        recipe.ingredients.append(
            RecipeIngredient(
                inventory_item_id=inventory_item.id,
                quantity=Decimal(quantity),
                unit=inventory_item.unit,
            )
        )


def seed_catalog_data(
    db: Session,
    root: User,
    *,
    force: bool = False,
) -> dict[str, int]:
    result = {
        "inventory_categories_created": 0,
        "inventory_items_created": 0,
        "menu_categories_created": 0,
        "menu_items_created": 0,
        "legacy_menu_items_migrated": 0,
        "menu_items_configured": 0,
        "menu_images_configured": 0,
        "recipes_configured": 0,
    }

    categories = {category.name: category for category in db.scalars(select(Category))}
    for name, description, color in CATALOG_CATEGORIES:
        if name not in categories:
            category = Category(name=name, description=description, color=color)
            db.add(category)
            db.flush()
            categories[name] = category
            result["inventory_categories_created"] += 1

    inventory_by_name = {item.name: item for item in db.scalars(select(InventoryItem))}
    for sku, name, category_name, unit in CATALOG_ITEMS:
        if name not in inventory_by_name:
            item = InventoryItem(
                sku=sku,
                name=name,
                category_id=categories[category_name].id,
                unit=unit,
            )
            db.add(item)
            db.flush()
            inventory_by_name[name] = item
            result["inventory_items_created"] += 1

    menu_categories = {
        category.name: category for category in db.scalars(select(MenuCategory))
    }
    for name, description, color, sort_order in MENU_CATEGORIES:
        if name not in menu_categories:
            category = MenuCategory(
                name=name,
                description=description,
                color=color,
                sort_order=sort_order,
            )
            db.add(category)
            db.flush()
            menu_categories[name] = category
            result["menu_categories_created"] += 1

    menu_by_name = {item.name: item for item in db.scalars(select(MenuItem))}
    for spec in MENU_PRODUCTS:
        menu_item = menu_by_name.get(spec.name)
        is_new = menu_item is None
        should_configure = force

        if menu_item is None:
            legacy_name = next(
                (
                    alias
                    for alias in spec.aliases
                    if alias in menu_by_name
                    and (
                        force
                        or menu_by_name[alias].description == LEGACY_DRAFT_DESCRIPTION
                    )
                ),
                None,
            )
            if legacy_name is not None:
                menu_item = menu_by_name.pop(legacy_name)
                menu_item.name = spec.name
                menu_by_name[spec.name] = menu_item
                result["legacy_menu_items_migrated"] += 1
                should_configure = True
                is_new = False
            else:
                menu_item = MenuItem(
                    name=spec.name,
                    category=spec.category,
                    category_id=menu_categories[spec.category].id,
                    selling_price=Decimal(spec.selling_price),
                    stock_quantity_per_sale=Decimal(spec.stock_quantity_per_sale),
                    description=spec.description,
                    is_active=True,
                )
                db.add(menu_item)
                db.flush()
                menu_by_name[spec.name] = menu_item
                result["menu_items_created"] += 1
                should_configure = True
        elif menu_item.description == LEGACY_DRAFT_DESCRIPTION:
            should_configure = True

        default_image = MENU_PRODUCT_IMAGES.get(spec.name)
        if default_image is not None and not menu_item.image_path:
            menu_item.image_path = f"/menu-images/{default_image}"
            result["menu_images_configured"] += 1

        if not should_configure:
            continue

        menu_item.category = spec.category
        menu_item.category_id = menu_categories[spec.category].id
        menu_item.selling_price = Decimal(spec.selling_price)
        menu_item.stock_quantity_per_sale = Decimal(spec.stock_quantity_per_sale)
        menu_item.description = spec.description
        menu_item.is_active = True

        if spec.direct_inventory_name is not None:
            direct_item = inventory_by_name.get(spec.direct_inventory_name)
            if direct_item is None:
                raise RuntimeError(
                    f"Missing direct-sale inventory item: {spec.direct_inventory_name}"
                )
            menu_item.inventory_item_id = direct_item.id
            existing_recipe = db.scalar(
                select(Recipe).where(Recipe.menu_item_id == menu_item.id)
            )
            if existing_recipe is not None:
                db.delete(existing_recipe)
        else:
            menu_item.inventory_item_id = None
            _configure_recipe(
                db,
                root=root,
                menu_item=menu_item,
                spec=spec,
                inventory_by_name=inventory_by_name,
            )
            result["recipes_configured"] += 1

        if not is_new:
            result["menu_items_configured"] += 1

    db.flush()
    return result


def seed_catalog(*, dry_run: bool = False, force: bool = False) -> None:
    with SessionLocal() as db:
        root = db.scalar(select(User).where(User.role == UserRole.ROOT))
        if root is None:
            raise RuntimeError("Run bootstrap before seeding the catalog")

        result = seed_catalog_data(db, root, force=force)
        changed = sum(result.values())
        if changed and not dry_run:
            record_audit(
                db,
                actor=root,
                action="seed_catalog",
                category="system",
                entity_type="catalog",
                entity_id="shawarma-production-v1",
                summary="Installed the production shawarma menu and recipes",
                details=result,
            )
            db.commit()
        else:
            db.rollback()

        mode = "Dry run" if dry_run else "Catalog ready"
        print(f"{mode}: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Me management commands")
    parser.add_argument(
        "command", choices=["bootstrap", "seed-catalog"], help="Command to run"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview catalog changes and roll them back",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reapply official prices and recipes to the production catalog",
    )
    args = parser.parse_args()
    if args.command == "bootstrap":
        if args.dry_run or args.force:
            parser.error("--dry-run and --force are only valid with seed-catalog")
        bootstrap()
    elif args.command == "seed-catalog":
        seed_catalog(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
