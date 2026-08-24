from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.db import get_db
from app.deps import client_ip, require_roles
from app.models import (
    Customer,
    InventoryItem,
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
    MenuItemCreate,
    MenuItemRead,
    MenuItemUpdate,
    OrderCreate,
    OrderRead,
    OrderStatusUpdate,
)

router = APIRouter(tags=["orders"])
sales_roles = require_roles(UserRole.ROOT, UserRole.ACCOUNTING_MANAGER, UserRole.SALES_MANAGER)
order_view_roles = require_roles(
    UserRole.ROOT, UserRole.ACCOUNTING_MANAGER, UserRole.SALES_MANAGER, UserRole.KITCHEN_MANAGER
)
root_only = require_roles(UserRole.ROOT)


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


@router.post("/customers", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CustomerCreate,
    request: Request,
    actor: User = Depends(sales_roles),
    db: Session = Depends(get_db),
) -> Customer:
    existing = db.scalar(select(Customer).where(Customer.phone == payload.phone))
    if existing:
        raise HTTPException(status_code=409, detail="A customer with this phone number already exists")
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


@router.get("/menu-items", response_model=list[MenuItemRead])
def list_menu_items(
    active: bool | None = True,
    search: str | None = Query(default=None, max_length=100),
    _: User = Depends(order_view_roles),
    db: Session = Depends(get_db),
) -> list[MenuItem]:
    query = select(MenuItem)
    if active is not None:
        query = query.where(MenuItem.is_active == active)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(MenuItem.name.ilike(term), MenuItem.category.ilike(term)))
    return list(db.scalars(query.order_by(MenuItem.category, MenuItem.name)))


@router.post("/menu-items", response_model=MenuItemRead, status_code=201)
def create_menu_item(
    payload: MenuItemCreate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> MenuItem:
    menu_item = MenuItem(**payload.model_dump())
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
    db.refresh(menu_item)
    return menu_item


@router.patch("/menu-items/{menu_item_id}", response_model=MenuItemRead)
def update_menu_item(
    menu_item_id: int,
    payload: MenuItemUpdate,
    request: Request,
    actor: User = Depends(root_only),
    db: Session = Depends(get_db),
) -> MenuItem:
    item = db.get(MenuItem, menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Menu item not found")
    changes = payload.model_dump(exclude_unset=True)
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
    db.refresh(item)
    return item


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
            select(MenuItem)
            .options(
                selectinload(MenuItem.recipe)
                .selectinload(Recipe.ingredients)
                .selectinload(RecipeIngredient.inventory_item)
            )
            .where(MenuItem.id.in_(menu_ids), MenuItem.is_active.is_(True))
        )
    }
    if len(menu_items) != len(menu_ids):
        raise HTTPException(status_code=400, detail="One or more menu items are unavailable")

    customer: Customer | None = None
    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if customer is None:
            raise HTTPException(status_code=400, detail="Customer not found")
    elif payload.customer is not None:
        customer = db.scalar(select(Customer).where(Customer.phone == payload.customer.phone))
        if customer is None:
            customer = Customer(**payload.customer.model_dump())
            db.add(customer)
            db.flush()

    subtotal = sum(
        (menu_items[line.menu_item_id].selling_price * line.quantity for line in payload.items),
        Decimal("0"),
    )
    if payload.discount > subtotal:
        raise HTTPException(status_code=422, detail="Discount cannot be greater than subtotal")

    required_stock: dict[int, Decimal] = {}
    for line in payload.items:
        menu_item = menu_items[line.menu_item_id]
        if menu_item.recipe is None:
            continue
        for ingredient in menu_item.recipe.ingredients:
            amount = (ingredient.quantity / menu_item.recipe.yield_quantity) * line.quantity
            required_stock[ingredient.inventory_item_id] = (
                required_stock.get(ingredient.inventory_item_id, Decimal("0")) + amount
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
    shortages = [
        f"{locked_items[item_id].name}: need {needed}, have {locked_items[item_id].current_quantity}"
        for item_id, needed in required_stock.items()
        if item_id not in locked_items or locked_items[item_id].current_quantity < needed
    ]
    if shortages:
        raise HTTPException(status_code=409, detail={"message": "Insufficient ingredients", "items": shortages})

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
        db.add(
            OrderItem(
                order_id=order.id,
                menu_item_id=menu_item.id,
                name=menu_item.name,
                quantity=line.quantity,
                unit_price=menu_item.selling_price,
                line_total=menu_item.selling_price * line.quantity,
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
                quantity_before=before,
                quantity_after=stock_item.current_quantity,
                reason=f"Ingredients used by order {order.order_number}",
                reference_type="order",
                reference_id=order.id,
                created_by_id=actor.id,
            )
        )
    record_audit(
        db,
        actor=actor,
        action="create",
        category="orders",
        entity_type="order",
        entity_id=order.id,
        summary=f"Placed order {order.order_number} for {order.customer_name}",
        details={"total": str(order.total), "items": len(payload.items), "payment": order.payment_method.value},
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
        query = query.where(or_(Order.order_number.ilike(term), Order.customer_name.ilike(term)))
    return list(db.scalars(query.order_by(Order.created_at.desc()).limit(limit)).unique())


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
        raise HTTPException(status_code=403, detail="Kitchen managers can only mark preparing or ready")

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
                select(InventoryItem).where(InventoryItem.id.in_(inventory_ids)).order_by(InventoryItem.id).with_for_update()
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
                    quantity_before=before,
                    quantity_after=stock.current_quantity,
                    reason=f"Stock restored after cancelling order {order.order_number}",
                    reference_type="order_cancel",
                    reference_id=order.id,
                    created_by_id=actor.id,
                )
            )
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
        "customer_copy": {
            "title": "Customer receipt",
            "show_prices": True,
            "footer": "Thank you for your order",
        },
        "kitchen_copy": {
            "title": "Kitchen ticket",
            "show_prices": False,
            "highlight_notes": True,
        },
    }
