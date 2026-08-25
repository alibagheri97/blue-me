import argparse
import sys

from sqlalchemy import select

from app.audit import record_audit
from app.core.config import settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import Category, InventoryItem, MenuCategory, MenuItem, User, UserRole


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
]

MENU_CATEGORIES = [
    ("شاورما", "انواع شاورمای مرغ، گوشت و میکس", "#ef4444", 10),
    ("پیش‌غذا", "سیب‌زمینی و مخلفات", "#f59e0b", 20),
    ("سس", "سس‌های قابل سفارش", "#8b5cf6", 30),
    ("نوشیدنی", "نوشیدنی‌های سرد", "#06b6d4", 40),
]

MENU_ITEMS = [
    ("شاورما مرغ ساده", "شاورما", None),
    ("شاورما گوشت ساده", "شاورما", None),
    ("شاورما میکس", "شاورما", None),
    ("شاورما مرغ با پنیر", "شاورما", None),
    ("شاورما گوشت با پنیر", "شاورما", None),
    ("شاورما میکس با پنیر", "شاورما", None),
    ("شاورما عربی مرغ", "شاورما", None),
    ("شاورما عربی گوشت", "شاورما", None),
    ("شاورما عربی میکس", "شاورما", None),
    ("سیب زمینی", "پیش‌غذا", None),
    ("سیب زمینی پنیری", "پیش‌غذا", None),
    ("سس لبنانی", "سس", None),
    ("سس سیر", "سس", None),
    ("سس باربیکیو", "سس", None),
    ("سس کچاپ", "سس", None),
    ("سس مایونز", "سس", None),
    ("نوشابه قوطی فانتا", "نوشیدنی", "نوشابه قوطی فانتا"),
    ("نوشابه قوطی کوکاکولا", "نوشیدنی", "نوشابه قوطی کوکاکولا"),
    ("نوشابه قوطی پپسی", "نوشیدنی", "نوشابه قوطی پپسی"),
    ("نوشابه لیموناد شیشه‌ای", "نوشیدنی", "نوشابه لیموناد شیشه‌ای"),
    ("آب معدنی کوچک", "نوشیدنی", "آب معدنی کوچک"),
    ("آب معدنی بزرگ", "نوشیدنی", "آب معدنی بزرگ"),
    ("دلستر انگور بزرگ", "نوشیدنی", "دلستر انگور بزرگ"),
]


def bootstrap() -> None:
    if len(settings.root_password) < 12:
        raise RuntimeError("ROOT_PASSWORD must contain at least 12 characters")
    if len(settings.app_secret_key) < 32:
        raise RuntimeError("APP_SECRET_KEY must contain at least 32 characters")
    with SessionLocal() as db:
        root = db.scalar(select(User).where(User.role == UserRole.ROOT))
        if root is None:
            if db.scalar(select(User.id).where(User.username == settings.root_username)):
                raise RuntimeError("ROOT_USERNAME is already used by a non-root account")
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
                    Category(name="مواد اولیه", color="#2563eb", description="مواد خام و اولیه آشپزخانه"),
                    Category(name="نوشیدنی", color="#06b6d4", description="نوشیدنی‌ها و ملزومات آن‌ها"),
                    Category(name="بسته‌بندی", color="#8b5cf6", description="لیوان، جعبه، پاکت و ظروف مصرفی"),
                    Category(name="نظافت", color="#10b981", description="مواد شوینده و بهداشتی"),
                ]
            )
            print("Created starter inventory categories")
        db.commit()


def seed_catalog() -> None:
    with SessionLocal() as db:
        root = db.scalar(select(User).where(User.role == UserRole.ROOT))
        if root is None:
            raise RuntimeError("Run bootstrap before seeding the catalog")

        categories = {category.name: category for category in db.scalars(select(Category))}
        created_categories = 0
        for name, description, color in CATALOG_CATEGORIES:
            if name not in categories:
                category = Category(name=name, description=description, color=color)
                db.add(category)
                db.flush()
                categories[name] = category
                created_categories += 1

        inventory_by_name = {
            item.name: item for item in db.scalars(select(InventoryItem))
        }
        created_items = 0
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
                created_items += 1

        menu_categories = {
            category.name: category for category in db.scalars(select(MenuCategory))
        }
        created_menu_categories = 0
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
                created_menu_categories += 1

        existing_menu_names = set(db.scalars(select(MenuItem.name)))
        created_menu_items = 0
        for name, category_name, direct_inventory_name in MENU_ITEMS:
            if name in existing_menu_names:
                continue
            direct_item = inventory_by_name.get(direct_inventory_name) if direct_inventory_name else None
            db.add(
                MenuItem(
                    name=name,
                    category=category_name,
                    category_id=menu_categories[category_name].id,
                    selling_price=0,
                    inventory_item_id=direct_item.id if direct_item else None,
                    stock_quantity_per_sale=1,
                    is_active=False,
                    description="پیش‌نویس اولیه؛ قیمت و دستور پخت را تکمیل کنید.",
                )
            )
            created_menu_items += 1

        record_audit(
            db,
            actor=root,
            action="seed_catalog",
            category="system",
            entity_type="catalog",
            entity_id="shawarma-v1",
            summary="Seeded shawarma inventory and menu catalog",
            details={
                "inventory_categories": created_categories,
                "inventory_items": created_items,
                "menu_categories": created_menu_categories,
                "menu_items": created_menu_items,
            },
        )
        db.commit()
        print(
            "Catalog ready: "
            f"{created_items} inventory items and {created_menu_items} menu drafts created"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Blue Me management commands")
    parser.add_argument("command", choices=["bootstrap", "seed-catalog"], help="Command to run")
    args = parser.parse_args()
    if args.command == "bootstrap":
        bootstrap()
    elif args.command == "seed-catalog":
        seed_catalog()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
