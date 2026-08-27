from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import (
    Customer,
    InventoryItem,
    MenuCategory,
    MenuItem,
    MovementType,
    Order,
    OrderItem,
    OrderStatus,
    Recipe,
    RecipeIngredient,
    StockMovement,
    User,
    UserRole,
)
from app.schemas import (
    CustomerCreate,
    CustomerRead,
    MenuCategoryCreate,
    MenuCategoryRead,
    MenuItemCreate,
    MenuItemRead,
    MenuItemUpdate,
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
)
from app.services.inventory_alerts import sync_auto_purchase_need
from app.services.persian_quotes import quote_for_order

router = APIRouter(tags=["orders"])
sales_roles = require_roles(
    UserRole.ROOT, UserRole.ACCOUNTING_MANAGER, UserRole.SALES_MANAGER
)
order_view_roles = require_roles(
    UserRole.ROOT,
    UserRole.ACCOUNTING_MANAGER,
    UserRole.SALES_MANAGER,
    UserRole.KITCHEN_MANAGER,
)


def menu_query():
    return select(MenuItem).options(
        selectinload(MenuItem.menu_category),
        selectinload(MenuItem.inventory_item),
        selectinload(MenuItem.recipe)
        .selectinload(Recipe.ingredients)
        .selectinload(RecipeIngredient.inventory_item),
    )


def serialize_menu_item(item: MenuItem) -> dict:
    cost = Decimal("0")
    max_available: int | None = None
    configured = False
    if item.inventory_item is not None:
        configured = True
        per_sale = Decimal(item.stock_quantity_per_sale)
        cost = Decimal(item.inventory_item.average_cost) * per_sale
        max_available = int(Decimal(item.inventory_item.current_quantity) / per_sale)
    elif item.recipe is not None and item.recipe.ingredients:
        configured = True
        yield_quantity = Decimal(item.recipe.yield_quantity)
        cost = (
            sum(
                (
                    Decimal(line.quantity) * Decimal(line.inventory_item.average_cost)
                    for line in item.recipe.ingredients
                ),
                Decimal("0"),
            )
            / yield_quantity
        )
        max_available = min(
            int(
                Decimal(line.inventory_item.current_quantity)
                / (Decimal(line.quantity) / yield_quantity)
            )
            for line in item.recipe.ingredients
        )
    gross_profit = Decimal(item.selling_price) - cost
    margin = (
        gross_profit / Decimal(item.selling_price) * 100
        if Decimal(item.selling_price) > 0
        else Decimal("0")
    )
    return {
        "id": item.id,
        "name": item.name,
        "category": item.menu_category.name if item.menu_category else item.category,
        "category_id": item.category_id,
        "selling_price": item.selling_price,
        "inventory_item_id": item.inventory_item_id,
        "stock_quantity_per_sale": item.stock_quantity_per_sale,
        "description": item.description,
        "image_path": item.image_path,
        "is_active": item.is_active,
        "calculated_cost": cost.quantize(Decimal("0.01")),
        "gross_profit": gross_profit.quantize(Decimal("0.01")),
        "margin_percent": margin.quantize(Decimal("0.01")),
        "recipe_configured": configured,
        "is_available": configured and (max_available or 0) > 0,
        "max_available_quantity": max_available,
    }


def resolve_menu_category(
    db: Session, *, category_id: int | None, category_name: str | None
) -> MenuCategory:
    category = db.get(MenuCategory, category_id) if category_id is not None else None
    if category_id is not None and category is None:
        raise HTTPException(status_code=422, detail="Menu category not found")
    if category is None:
        name = (category_name or "عمومی").strip()
        category = db.scalar(
            select(MenuCategory).where(func.lower(MenuCategory.name) == name.lower())
        )
        if category is None:
            category = MenuCategory(name=name)
            db.add(category)
            db.flush()
    return category


def validate_direct_inventory(db: Session, inventory_item_id: int | None) -> None:
    if inventory_item_id is None:
        return
    item = db.get(InventoryItem, inventory_item_id)
    if item is None or not item.is_active:
        raise HTTPException(
            status_code=422, detail="Inventory item for direct sale is unavailable"
        )


def order_query():
    return select(Order).options(selectinload(Order.items))


def get_order_or_404(db: Session, order_id: int, *, lock: bool = False) -> Order:
    query = order_query().where(Order.id == order_id)
    if lock:
        query = query.with_for_update()
    order = db.scalar(query)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/customers", response_model=list[CustomerRead])
def search_customers(
    search: str = Query(default="", max_length=100),
    _: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> list[Customer]:
    query = select(Customer)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(or_(Customer.name.ilike(term), Customer.phone.ilike(term)))
    return list(db.scalars(query.order_by(Customer.updated_at.desc()).limit(30)))


@router.post(
    "/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED
)
def create_customer(
    payload: CustomerCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> Customer:
    existing = db.scalar(select(Customer).where(Customer.phone == payload.phone))
    if existing:
        raise HTTPException(
            status_code=409, detail="A customer with this phone number already exists"
        )
    customer = Customer(**payload.model_dump())
    db.add(customer)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="customers",
        entity_type="customer",
        entity_id=customer.id,
        summary=f"Registered customer {customer.name}",
        details={"phone": customer.phone},
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/menu-categories", response_model=list[MenuCategoryRead])
def list_menu_categories(
    active: bool | None = True,
    _: User = Depends(order_view_roles),
    db: Session = Depends(get_db),
) -> list[MenuCategory]:
    query = select(MenuCategory)
    if active is not None:
        query = query.where(MenuCategory.is_active == active)
    return list(db.scalars(query.order_by(MenuCategory.sort_order, MenuCategory.name)))


@router.post("/menu-categories", response_model=MenuCategoryRead, status_code=201)
def create_menu_category(
    payload: MenuCategoryCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> MenuCategory:
    if db.scalar(
        select(MenuCategory.id).where(
            func.lower(MenuCategory.name) == payload.name.lower()
        )
    ):
        raise HTTPException(status_code=409, detail="Menu category already exists")
    category = MenuCategory(**payload.model_dump())
    db.add(category)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="menu",
        entity_type="menu_category",
        entity_id=category.id,
        summary=f"Created menu category {category.name}",
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return category


@router.patch("/menu-categories/{category_id}", response_model=MenuCategoryRead)
def update_menu_category(
    category_id: int,
    payload: MenuCategoryCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> MenuCategory:
    category = db.get(MenuCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Menu category not found")
    duplicate = db.scalar(
        select(MenuCategory.id).where(
            func.lower(MenuCategory.name) == payload.name.lower(),
            MenuCategory.id != category_id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Menu category name already exists")
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    for menu_item in db.scalars(
        select(MenuItem).where(MenuItem.category_id == category.id)
    ):
        menu_item.category = category.name
    record_audit(
        db,
        actor=actor,
        action="update",
        category="menu",
        entity_type="menu_category",
        entity_id=category.id,
        summary=f"Updated menu category {category.name}",
        ip_address=client_ip(request),
    )
    db.commit()
    db.refresh(category)
    return category


@router.delete("/menu-categories/{category_id}", status_code=204)
def delete_menu_category(
    category_id: int,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> None:
    category = db.get(MenuCategory, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Menu category not found")
    if db.scalar(
        select(func.count())
        .select_from(MenuItem)
        .where(MenuItem.category_id == category.id)
    ):
        raise HTTPException(
            status_code=409, detail="Move menu items before deleting this category"
        )
    record_audit(
        db,
        actor=actor,
        action="delete",
        category="menu",
        entity_type="menu_category",
        entity_id=category.id,
        summary=f"Deleted menu category {category.name}",
        ip_address=client_ip(request),
    )
    db.delete(category)
    db.commit()


@router.get("/menu-items", response_model=list[MenuItemRead])
def list_menu_items(
    active: bool | None = True,
    include_inactive: bool = False,
    search: str | None = Query(default=None, max_length=100),
    _: User = Depends(order_view_roles),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = menu_query()
    if active is not None and not include_inactive:
        query = query.where(MenuItem.is_active == active)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(MenuItem.name.ilike(term), MenuItem.category.ilike(term))
        )
    return [
        serialize_menu_item(item)
        for item in db.scalars(
            query.order_by(MenuItem.category, MenuItem.name)
        ).unique()
    ]


@router.post("/menu-items", response_model=MenuItemRead, status_code=201)
def create_menu_item(
    payload: MenuItemCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> dict:
    validate_direct_inventory(db, payload.inventory_item_id)
    category = resolve_menu_category(
        db, category_id=payload.category_id, category_name=payload.category
    )
    values = payload.model_dump(exclude={"category_id", "category"})
    menu_item = MenuItem(
        **values,
        category_id=category.id,
        category=category.name,
    )
    db.add(menu_item)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create",
        category="menu",
        entity_type="menu_item",
        entity_id=menu_item.id,
        summary=f"Created menu item {menu_item.name}",
        details={"price": str(menu_item.selling_price), "category": menu_item.category},
        ip_address=client_ip(request),
    )
    db.commit()
    menu_item = db.scalar(menu_query().where(MenuItem.id == menu_item.id))
    return serialize_menu_item(menu_item)


@router.patch("/menu-items/{menu_item_id}", response_model=MenuItemRead)
def update_menu_item(
    menu_item_id: int,
    payload: MenuItemUpdate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> dict:
    item = db.scalar(menu_query().where(MenuItem.id == menu_item_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Menu item not found")
    changes = payload.model_dump(exclude_unset=True)
    if "inventory_item_id" in changes:
        validate_direct_inventory(db, changes["inventory_item_id"])
        if changes["inventory_item_id"] is not None and item.recipe is not None:
            raise HTTPException(
                status_code=409,
                detail="Remove the recipe before linking a direct inventory item",
            )
    if "category_id" in changes or "category" in changes:
        category = resolve_menu_category(
            db,
            category_id=changes.pop("category_id", item.category_id),
            category_name=changes.pop("category", item.category),
        )
        changes["category_id"] = category.id
        changes["category"] = category.name
    for key, value in changes.items():
        setattr(item, key, value)
    record_audit(
        db,
        actor=actor,
        action="update",
        category="menu",
        entity_type="menu_item",
        entity_id=item.id,
        summary=f"Updated menu item {item.name}",
        details={key: str(value) for key, value in changes.items()},
        ip_address=client_ip(request),
    )
    db.commit()
    item = db.scalar(menu_query().where(MenuItem.id == item.id))
    return serialize_menu_item(item)


@router.post("/orders", response_model=OrderRead, status_code=201)
def create_order(
    payload: OrderCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> Order:
    menu_ids = {line.menu_item_id for line in payload.items}
    menu_items = {
        item.id: item
        for item in db.scalars(
            menu_query().where(MenuItem.id.in_(menu_ids), MenuItem.is_active.is_(True))
        ).unique()
    }
    if len(menu_items) != len(menu_ids):
        raise HTTPException(
            status_code=400, detail="One or more menu items are unavailable"
        )

    customer: Customer | None = None
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=400, detail="Customer not found")
    elif payload.customer is not None:
        customer = db.scalar(
            select(Customer).where(Customer.phone == payload.customer.phone)
        )
        if customer is None:
            customer = Customer(**payload.customer.model_dump())
            db.add(customer)
            db.flush()

    subtotal = sum(
        (
            menu_items[line.menu_item_id].selling_price * line.quantity
            for line in payload.items
        ),
        Decimal("0"),
    )
    if payload.discount > subtotal:
        raise HTTPException(
            status_code=422, detail="Discount cannot be greater than subtotal"
        )

    required_stock: dict[int, Decimal] = {}
    unit_costs: dict[int, Decimal] = {}
    unconfigured: list[str] = []
    for line in payload.items:
        menu_item = menu_items[line.menu_item_id]
        if menu_item.inventory_item is not None:
            amount_per_sale = Decimal(menu_item.stock_quantity_per_sale)
            amount = amount_per_sale * line.quantity
            required_stock[menu_item.inventory_item_id] = (
                required_stock.get(menu_item.inventory_item_id, Decimal("0")) + amount
            )
            unit_costs[menu_item.id] = (
                Decimal(menu_item.inventory_item.average_cost) * amount_per_sale
            )
        elif menu_item.recipe is not None and menu_item.recipe.ingredients:
            recipe_cost = Decimal("0")
            for ingredient in menu_item.recipe.ingredients:
                amount_per_sale = Decimal(ingredient.quantity) / Decimal(
                    menu_item.recipe.yield_quantity
                )
                amount = amount_per_sale * line.quantity
                required_stock[ingredient.inventory_item_id] = (
                    required_stock.get(ingredient.inventory_item_id, Decimal("0"))
                    + amount
                )
                recipe_cost += amount_per_sale * Decimal(
                    ingredient.inventory_item.average_cost
                )
            unit_costs[menu_item.id] = recipe_cost
        else:
            unconfigured.append(menu_item.name)

    if unconfigured:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Menu items need a recipe or direct inventory link",
                "items": unconfigured,
            },
        )

    locked_items = {
        item.id: item
        for item in db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id.in_(sorted(required_stock)))
            .order_by(InventoryItem.id)
            .with_for_update()
        )
    }
    shortages = []
    for item_id, needed in required_stock.items():
        stock_item = locked_items.get(item_id)
        if stock_item is None:
            shortages.append(f"کالای انبار #{item_id}: در دسترس نیست")
        elif Decimal(stock_item.current_quantity) < needed:
            shortages.append(
                f"{stock_item.name}: نیاز {needed}، موجودی {stock_item.current_quantity}"
            )
    if shortages:
        raise HTTPException(
            status_code=409,
            detail={"message": "Insufficient ingredients", "items": shortages},
        )

    order = Order(
        order_number=f"BM-{date.today():%y%m%d}-{uuid4().hex[:6].upper()}",
        customer_id=customer.id if customer else None,
        customer_name=customer.name if customer else "Guest",
        subtotal=subtotal,
        discount=payload.discount,
        total=subtotal - payload.discount,
        payment_method=payload.payment_method,
        notes=payload.notes,
        created_by_id=actor.id,
    )
    db.add(order)
    db.flush()
    for line in payload.items:
        menu_item = menu_items[line.menu_item_id]
        unit_cost = unit_costs[menu_item.id]
        db.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                name=menu_item.name,
                quantity=line.quantity,
                unit_price=menu_item.selling_price,
                line_total=menu_item.selling_price * line.quantity,
                unit_cost=unit_cost,
                line_cost=unit_cost * line.quantity,
                notes=line.notes,
            )
        )
    for item_id, amount in required_stock.items():
        stock_item = locked_items[item_id]
        before = stock_item.current_quantity
        stock_item.current_quantity = before - amount
        db.add(
            StockMovement(
                item_id=item_id,
                movement_type=MovementType.SALE,
                quantity=-amount,
                unit_cost=stock_item.average_cost,
                quantity_before=before,
                quantity_after=stock_item.current_quantity,
                reason=f"Ingredients used by order {order.order_number}",
                reference_type="order",
                reference_id=order.id,
                created_by_id=actor.id,
            )
        )
        sync_auto_purchase_need(db, item=stock_item, actor=actor)
    total_cogs = sum(
        (unit_costs[line.menu_item_id] * line.quantity for line in payload.items),
        Decimal("0"),
    )
    record_audit(
        db,
        actor=actor,
        action="create",
        category="orders",
        entity_type="order",
        entity_id=order.id,
        summary=f"Placed order {order.order_number} for {order.customer_name}",
        details={
            "total": str(order.total),
            "cost": str(total_cogs),
            "gross_profit": str(order.total - total_cogs),
            "items": len(payload.items),
            "payment": order.payment_method.value,
        },
        ip_address=client_ip(request),
    )
    db.commit()
    return get_order_or_404(db, order.id)


@router.get("/orders", response_model=list[OrderRead])
def list_orders(
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    day: date | None = None,
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(order_view_roles),
    db: Session = Depends(get_db),
) -> list[Order]:
    query = order_query()
    if order_status:
        query = query.where(Order.status == order_status)
    if day:
        start = datetime.combine(day, datetime.min.time())
        end = datetime.combine(day, datetime.max.time())
        query = query.where(Order.created_at.between(start, end))
    if search:
        term = f"%{search.strip()}%"
        query = query.where(
            or_(Order.order_number.ilike(term), Order.customer_name.ilike(term))
        )
    return list(
        db.scalars(query.order_by(Order.created_at.desc()).limit(limit)).unique()
    )


@router.get("/orders/{order_id}", response_model=OrderRead)
def get_order(
    order_id: int, _: User = Depends(order_view_roles), db: Session = Depends(get_db)
) -> Order:
    return get_order_or_404(db, order_id)


@router.patch("/orders/{order_id}/status", response_model=OrderRead)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    request: Request,
    actor: User = Depends(order_view_roles),
    db: Session = Depends(get_db),
) -> Order:
    order = get_order_or_404(db, order_id, lock=True)
    allowed = {
        OrderStatus.CONFIRMED: {OrderStatus.PREPARING, OrderStatus.CANCELLED},
        OrderStatus.PREPARING: {OrderStatus.READY, OrderStatus.CANCELLED},
        OrderStatus.READY: {OrderStatus.COMPLETED, OrderStatus.CANCELLED},
        OrderStatus.COMPLETED: set(),
        OrderStatus.CANCELLED: set(),
    }
    if payload.status not in allowed[order.status]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot change an order from {order.status.value} to {payload.status.value}",
        )
    if actor.role == UserRole.KITCHEN_MANAGER and payload.status in {
        OrderStatus.CANCELLED,
        OrderStatus.COMPLETED,
    }:
        raise HTTPException(
            status_code=403, detail="Kitchen managers can only mark preparing or ready"
        )

    previous = order.status
    if payload.status == OrderStatus.CANCELLED:
        movements = list(
            db.scalars(
                select(StockMovement)
                .where(
                    StockMovement.reference_type == "order",
                    StockMovement.reference_id == order.id,
                    StockMovement.movement_type == MovementType.SALE,
                )
                .order_by(StockMovement.item_id)
            )
        )
        inventory_ids = sorted({movement.item_id for movement in movements})
        stocks = {
            item.id: item
            for item in db.scalars(
                select(InventoryItem)
                .where(InventoryItem.id.in_(inventory_ids))
                .order_by(InventoryItem.id)
                .with_for_update()
            )
        }
        for movement in movements:
            stock = stocks[movement.item_id]
            restored = abs(movement.quantity)
            before = stock.current_quantity
            stock.current_quantity = before + restored
            db.add(
                StockMovement(
                    item_id=stock.id,
                    movement_type=MovementType.ADJUST,
                    quantity=restored,
                    unit_cost=movement.unit_cost,
                    quantity_before=before,
                    quantity_after=stock.current_quantity,
                    reason=f"Stock restored after cancelling order {order.order_number}",
                    reference_type="order_cancel",
                    reference_id=order.id,
                    created_by_id=actor.id,
                )
            )
            sync_auto_purchase_need(db, item=stock, actor=actor)
    order.status = payload.status
    record_audit(
        db,
        actor=actor,
        action="status_change",
        category="orders",
        entity_type="order",
        entity_id=order.id,
        summary=f"Changed {order.order_number} from {previous.value} to {order.status.value}",
        details={"from": previous.value, "to": order.status.value},
        ip_address=client_ip(request),
    )
    db.commit()
    return get_order_or_404(db, order.id)


@router.get("/orders/{order_id}/receipt")
def receipt_data(
    order_id: int, _: User = Depends(order_view_roles), db: Session = Depends(get_db)
) -> dict:
    order = get_order_or_404(db, order_id)
    return {
        "order": OrderRead.model_validate(order),
        "quote": quote_for_order(order.order_number),
        "customer_copy": {
            "title": "رسید مشتری",
            "show_prices": True,
            "footer": "از خرید شما سپاسگزاریم",
            "paper_width_mm": 80,
            "monochrome": True,
            "high_contrast": True,
            "font_weight": 800,
            "minimum_font_size_pt": 11,
        },
        "kitchen_copy": {
            "title": "فیش آشپزخانه",
            "show_prices": False,
            "highlight_notes": True,
            "paper_width_mm": 80,
            "monochrome": True,
            "high_contrast": True,
            "font_weight": 800,
            "minimum_font_size_pt": 11,
        },
    }
