from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import require_sections
from app.models import (
    ApprovalStatus,
    DailyNeed,
    InventoryItem,
    MenuItem,
    NeedSource,
    Notification,
    Order,
    OrderStatus,
    PaymentMethod,
    PriceChangeRequest,
    PurchaseReceipt,
    PurchaseStatus,
    SectionKey,
    StockMovement,
    User,
)
from app.schemas import DashboardSummary
from app.services.business_time import (
    business_date,
    business_datetime,
    business_today,
    day_bounds,
    local_day_bounds,
)
from app.services.system_settings import get_system_settings

router = APIRouter(tags=["reports"])
dashboard_access = require_sections(SectionKey.DASHBOARD)
reports_access = require_sections(SectionKey.REPORTS)


def empty_payment_breakdown() -> dict[str, dict[str, Decimal | int | str]]:
    return {
        method.value: {
            "method": method.value,
            "amount": Decimal("0"),
            "orders": 0,
        }
        for method in PaymentMethod
    }


def add_payment(
    breakdown: dict[str, dict[str, Decimal | int | str]], order: Order
) -> None:
    if order.is_staff_meal or order.is_system_waste:
        return
    method = order.payment_method.value
    breakdown[method]["amount"] += order.total
    breakdown[method]["orders"] += 1


def finalize_payment_breakdown(
    breakdown: dict[str, dict[str, Decimal | int | str]], total: Decimal
) -> list[dict[str, Decimal | int | str]]:
    return [
        {
            **breakdown[method.value],
            "amount": Decimal(breakdown[method.value]["amount"]).quantize(
                Decimal("0.01")
            ),
            "share_percent": (
                Decimal(breakdown[method.value]["amount"]) / total * 100
            ).quantize(Decimal("0.01"))
            if total > 0
            else Decimal("0"),
        }
        for method in PaymentMethod
    ]


def successful_orders_query(start: datetime, end: datetime, *, include_staff_meals: bool = False):
    query = select(Order).where(
        Order.created_at.between(start, end),
        Order.status != OrderStatus.CANCELLED,
        Order.is_system_waste.is_(False),
        Order.is_deleted.is_(False),
    )
    return query if include_staff_meals else query.where(Order.is_staff_meal.is_(False))


def order_cost(order: Order) -> Decimal:
    return sum((line.line_cost for line in order.items), Decimal("0")) + Decimal(order.takeaway_cost)


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(
    actor: User = Depends(dashboard_access), db: Session = Depends(get_db)
) -> DashboardSummary:
    current_date = business_today()
    today_start, today_end = day_bounds(current_date)
    yesterday_start, yesterday_end = day_bounds(current_date - timedelta(days=1))
    today_orders = list(db.scalars(successful_orders_query(today_start, today_end)))
    yesterday_orders = list(
        db.scalars(successful_orders_query(yesterday_start, yesterday_end))
    )
    sales_today = sum((order.total for order in today_orders), Decimal("0"))
    sales_yesterday = sum((order.total for order in yesterday_orders), Decimal("0"))
    sales_change = (
        ((sales_today - sales_yesterday) / sales_yesterday * 100)
        if sales_yesterday > 0
        else (Decimal("100") if sales_today > 0 else Decimal("0"))
    )
    recent = list(
        db.scalars(
            select(Order)
            .options(selectinload(Order.items))
            .where(
                Order.is_staff_meal.is_(False),
                Order.is_system_waste.is_(False),
                Order.is_deleted.is_(False),
            )
            .order_by(Order.created_at.desc())
            .limit(6)
        ).unique()
    )
    low_stock = list(
        db.scalars(
            select(InventoryItem)
            .options(selectinload(InventoryItem.category))
            .where(
                InventoryItem.is_active.is_(True),
                InventoryItem.current_quantity <= InventoryItem.reorder_level,
            )
            .order_by((InventoryItem.current_quantity - InventoryItem.reorder_level))
            .limit(8)
        )
    )
    system_settings = get_system_settings(db)
    return DashboardSummary(
        sales_today=sales_today,
        orders_today=len(today_orders),
        average_order_value=sales_today / len(today_orders) if today_orders else 0,
        low_stock_count=db.scalar(
            select(func.count())
            .select_from(InventoryItem)
            .where(
                InventoryItem.is_active.is_(True),
                InventoryItem.current_quantity <= InventoryItem.reorder_level,
            )
        )
        or 0,
        pending_price_approvals=db.scalar(
            select(func.count())
            .select_from(PriceChangeRequest)
            .where(PriceChangeRequest.status == ApprovalStatus.PENDING)
        )
        or 0,
        pending_daily_needs=db.scalar(
            select(func.count())
            .select_from(DailyNeed)
            .where(DailyNeed.status == ApprovalStatus.PENDING)
        )
        or 0,
        automatic_purchase_needs=db.scalar(
            select(func.count())
            .select_from(DailyNeed)
            .where(
                DailyNeed.status == ApprovalStatus.PENDING,
                DailyNeed.source == NeedSource.AUTOMATIC,
            )
        )
        or 0,
        unread_notifications=db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.recipient_user_id == actor.id,
                Notification.is_read.is_(False),
            )
        )
        or 0,
        active_users=db.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        )
        or 0,
        orders_in_kitchen=db.scalar(
            select(func.count())
            .select_from(Order)
            .where(
                Order.status.in_([OrderStatus.CONFIRMED, OrderStatus.PREPARING]),
                Order.is_deleted.is_(False),
            )
        )
        or 0,
        kitchen_workflow_enabled=system_settings.kitchen_workflow_enabled,
        sales_change_percent=sales_change.quantize(Decimal("0.01")),
        recent_orders=recent,
        low_stock_items=low_stock,
    )


@router.get("/reports/overview")
def reports_overview(
    days: int = Query(default=30, ge=1, le=365),
    start_date: date | None = None,
    end_date: date | None = None,
    include_staff_meals: bool = False,
    search: str | None = Query(default=None, max_length=100),
    order_status: OrderStatus | None = Query(default=None, alias="status"),
    _: User = Depends(reports_access),
    db: Session = Depends(get_db),
) -> dict:
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=422, detail="Select both start and end dates")
    end_date = end_date or business_today()
    start_date = start_date or end_date - timedelta(days=days - 1)
    days = (end_date - start_date).days + 1
    if not 1 <= days <= 365:
        raise HTTPException(status_code=422, detail="Report range must be between 1 and 365 days")
    previous_start = start_date - timedelta(days=days)
    start_dt, _ = day_bounds(start_date)
    _, end_dt = day_bounds(end_date)
    previous_start_dt, _ = day_bounds(previous_start)
    previous_end_dt = start_dt - timedelta(microseconds=1)

    def filtered(query):
        if search:
            term = f"%{search.strip()}%"
            query = query.where(or_(Order.order_number.ilike(term), Order.customer_name.ilike(term)))
        if order_status:
            query = query.where(Order.status == order_status)
        return query

    orders = list(
        db.scalars(
            filtered(successful_orders_query(start_dt, end_dt, include_staff_meals=include_staff_meals)).options(selectinload(Order.items))
        ).unique()
    )
    previous_orders = list(
        db.scalars(filtered(successful_orders_query(previous_start_dt, previous_end_dt, include_staff_meals=include_staff_meals)))
    )
    waste_orders = list(db.scalars(filtered(select(Order).where(
        Order.created_at.between(start_dt, end_dt),
        Order.is_system_waste.is_(True),
        Order.is_deleted.is_(False),
        Order.status != OrderStatus.CANCELLED,
    )).options(selectinload(Order.items))).unique())
    staff_orders = [order for order in orders if order.is_staff_meal]
    staff_cost = sum((order_cost(order) for order in staff_orders), Decimal("0"))
    waste_cost = sum((order_cost(order) for order in waste_orders), Decimal("0"))
    revenue = sum((order.total for order in orders), Decimal("0"))
    previous_revenue = sum((order.total for order in previous_orders), Decimal("0"))
    revenue_growth = (
        (revenue - previous_revenue) / previous_revenue * 100
        if previous_revenue > 0
        else (Decimal("100") if revenue > 0 else Decimal("0"))
    )

    menu_ids = {line.menu_item_id for order in [*orders, *waste_orders] for line in order.items}
    cogs = sum((order_cost(order) for order in orders), Decimal("0")) + waste_cost
    purchase_start_dt, _ = local_day_bounds(start_date)
    _, purchase_end_dt = local_day_bounds(end_date)
    purchase_spend = db.scalar(
        select(func.coalesce(func.sum(PurchaseReceipt.total_cost), 0)).where(
            PurchaseReceipt.purchased_at.between(purchase_start_dt, purchase_end_dt),
            PurchaseReceipt.status == PurchaseStatus.POSTED,
        )
    ) or Decimal("0")
    daily = {
        (start_date + timedelta(days=index)).isoformat(): {
            "date": (start_date + timedelta(days=index)).isoformat(),
            "revenue": Decimal("0"),
            "orders": 0,
            "staff_orders": 0,
            "waste_orders": 0,
            "estimated_cost": Decimal("0"),
            "waste_cost": Decimal("0"),
            "payment_breakdown": empty_payment_breakdown(),
        }
        for index in range(days)
    }
    payment_breakdown = empty_payment_breakdown()
    product_stats: dict[int, dict] = {}
    hourly = {
        hour: {"hour": hour, "revenue": Decimal("0"), "orders": 0, "staff_orders": 0, "waste_orders": 0, "estimated_cost": Decimal("0")} for hour in range(24)
    }
    category_stats: dict[str, dict] = defaultdict(
        lambda: {"revenue": Decimal("0"), "quantity": 0, "waste_quantity": 0, "estimated_cost": Decimal("0")}
    )
    customer_counts: Counter[int] = Counter()

    menu_lookup = {
        item.id: item
        for item in db.scalars(select(MenuItem).where(MenuItem.id.in_(menu_ids)))
    }
    for order in [*orders, *waste_orders]:
        local_created_at = business_datetime(order.created_at)
        key = business_date(order.created_at).isoformat()
        daily[key]["revenue"] += order.total
        daily[key]["orders"] += int(not order.is_system_waste)
        daily[key]["staff_orders"] += int(order.is_staff_meal)
        daily[key]["waste_orders"] += int(order.is_system_waste)
        daily[key]["estimated_cost"] += order_cost(order)
        if order.is_system_waste:
            daily[key]["waste_cost"] += order_cost(order)
        add_payment(payment_breakdown, order)
        add_payment(daily[key]["payment_breakdown"], order)
        hourly[local_created_at.hour]["revenue"] += order.total
        hourly[local_created_at.hour]["orders"] += int(not order.is_system_waste)
        hourly[local_created_at.hour]["staff_orders"] += int(order.is_staff_meal)
        hourly[local_created_at.hour]["waste_orders"] += int(order.is_system_waste)
        hourly[local_created_at.hour]["estimated_cost"] += order_cost(order)
        if order.customer_id:
            customer_counts[order.customer_id] += 1
        item_count = sum(line.quantity for line in order.items)
        for line in order.items:
            allocated_revenue = (
                line.line_total * order.total / order.subtotal
                if order.subtotal > 0
                else Decimal("0")
            )
            stat = product_stats.setdefault(
                line.menu_item_id,
                {
                    "id": line.menu_item_id,
                    "name": line.name,
                    "quantity": 0,
                    "staff_quantity": 0,
                    "waste_quantity": 0,
                    "waste_cost": Decimal("0"),
                    "revenue": Decimal("0"),
                    "estimated_cost": Decimal("0"),
                },
            )
            stat["quantity"] += 0 if order.is_system_waste else line.quantity
            stat["staff_quantity"] += line.quantity if order.is_staff_meal else 0
            stat["waste_quantity"] += line.quantity if order.is_system_waste else 0
            stat["revenue"] += allocated_revenue
            allocated_cost = line.line_cost + Decimal(order.takeaway_cost) * line.quantity / item_count
            stat["waste_cost"] += allocated_cost if order.is_system_waste else Decimal("0")
            stat["estimated_cost"] += allocated_cost
            menu = menu_lookup.get(line.menu_item_id)
            category = menu.category if menu else "Unknown"
            category_stats[category]["revenue"] += allocated_revenue
            category_stats[category]["quantity"] += 0 if order.is_system_waste else line.quantity
            category_stats[category]["waste_quantity"] += line.quantity if order.is_system_waste else 0
            category_stats[category]["estimated_cost"] += allocated_cost

    for stat in product_stats.values():
        stat["gross_profit"] = stat["revenue"] - stat["estimated_cost"]
        stat["margin_percent"] = (
            stat["gross_profit"] / stat["revenue"] * 100
            if stat["revenue"] > 0
            else Decimal("0")
        )

    inventory_items = list(
        db.scalars(select(InventoryItem).where(InventoryItem.is_active.is_(True)))
    )
    inventory_value = sum(
        (item.current_quantity * item.average_cost for item in inventory_items),
        Decimal("0"),
    )
    low_stock = [
        item for item in inventory_items if item.current_quantity <= item.reorder_level
    ]
    moving_ids = set(
        db.scalars(
            select(StockMovement.item_id).where(
                StockMovement.created_at.between(start_dt, end_dt),
                StockMovement.quantity < 0,
            )
        )
    )
    slow_moving_value = sum(
        (
            item.current_quantity * item.average_cost
            for item in inventory_items
            if item.id not in moving_ids
        ),
        Decimal("0"),
    )

    daily_sales = [
        {
            **summary,
            "gross_profit": summary["revenue"] - summary["estimated_cost"],
            "payment_breakdown": finalize_payment_breakdown(
                summary["payment_breakdown"], Decimal(summary["revenue"])
            ),
        }
        for summary in daily.values()
    ]

    return {
        "period": {"days": days, "start": start_date, "end": end_date, "include_staff_meals": include_staff_meals},
        "kpis": {
            "revenue": revenue,
            "revenue_growth_percent": revenue_growth.quantize(Decimal("0.01")),
            "orders": len(orders),
            "staff_orders": len(staff_orders),
            "staff_cost": staff_cost,
            "staff_menu_value": sum((order.subtotal for order in staff_orders), Decimal("0")),
            "waste_orders": len(waste_orders),
            "waste_cost": waste_cost,
            "waste_menu_value": sum((order.subtotal for order in waste_orders), Decimal("0")),
            "average_order_value": revenue / len(orders) if orders else Decimal("0"),
            "estimated_cogs": cogs.quantize(Decimal("0.01")),
            "purchase_spend": Decimal(purchase_spend).quantize(Decimal("0.01")),
            "gross_profit": (revenue - cogs).quantize(Decimal("0.01")),
            "gross_margin_percent": ((revenue - cogs) / revenue * 100).quantize(
                Decimal("0.01")
            )
            if revenue > 0
            else Decimal("0"),
            "known_customer_rate_percent": (
                Decimal(sum(1 for order in orders if order.customer_id))
                / len(orders)
                * 100
            ).quantize(Decimal("0.01"))
            if orders
            else Decimal("0"),
            "repeat_customers": sum(
                1 for count in customer_counts.values() if count > 1
            ),
        },
        "payment_breakdown": finalize_payment_breakdown(payment_breakdown, revenue),
        "daily_sales": daily_sales,
        "hourly_demand": list(hourly.values()),
        "product_performance": sorted(
            product_stats.values(), key=lambda item: item["revenue"], reverse=True
        ),
        "category_performance": [
            {"category": name, **values, "gross_profit": values["revenue"] - values["estimated_cost"]}
            for name, values in sorted(
                category_stats.items(),
                key=lambda item: item[1]["revenue"],
                reverse=True,
            )
        ],
        "inventory_health": {
            "total_value": inventory_value.quantize(Decimal("0.01")),
            "active_items": len(inventory_items),
            "low_stock_items": len(low_stock),
            "automatic_purchase_needs": db.scalar(
                select(func.count())
                .select_from(DailyNeed)
                .where(
                    DailyNeed.source == NeedSource.AUTOMATIC,
                    DailyNeed.status == ApprovalStatus.PENDING,
                )
            )
            or 0,
            "slow_moving_value": slow_moving_value.quantize(Decimal("0.01")),
            "slow_moving_percent": (slow_moving_value / inventory_value * 100).quantize(
                Decimal("0.01")
            )
            if inventory_value > 0
            else Decimal("0"),
        },
        "insights": build_insights(
            revenue=revenue,
            growth=revenue_growth,
            products=list(product_stats.values()),
            low_stock_count=len(low_stock),
            slow_moving_value=slow_moving_value,
            peak_hour=max(hourly.values(), key=lambda item: item["revenue"])["hour"]
            if orders
            else None,
        ),
    }


def build_insights(
    *,
    revenue: Decimal,
    growth: Decimal,
    products: list[dict],
    low_stock_count: int,
    slow_moving_value: Decimal,
    peak_hour: int | None,
) -> list[dict[str, str]]:
    insights: list[dict[str, str]] = []
    if growth >= 10:
        insights.append(
            {
                "tone": "positive",
                "title": "Revenue momentum",
                "message": f"Revenue grew {growth:.1f}% versus the previous period.",
            }
        )
    elif growth <= -10:
        insights.append(
            {
                "tone": "warning",
                "title": "Revenue needs attention",
                "message": f"Revenue fell {abs(growth):.1f}% versus the previous period.",
            }
        )
    if products:
        best = max(products, key=lambda item: item["revenue"])
        insights.append(
            {
                "tone": "info",
                "title": "Top revenue product",
                "message": f"{best['name']} generated the most revenue in this period.",
            }
        )
        low_margin = [item for item in products if item.get("margin_percent", 100) < 30]
        if low_margin:
            insights.append(
                {
                    "tone": "warning",
                    "title": "Margin opportunity",
                    "message": f"{len(low_margin)} product(s) have an estimated gross margin below 30%.",
                }
            )
    if peak_hour is not None:
        insights.append(
            {
                "tone": "info",
                "title": "Peak sales hour",
                "message": f"Sales are strongest around {peak_hour:02d}:00; align staffing and preparation with this window.",
            }
        )
    if low_stock_count:
        insights.append(
            {
                "tone": "critical",
                "title": "Stock risk",
                "message": f"{low_stock_count} inventory item(s) are at or below their reorder level.",
            }
        )
    if slow_moving_value > 0:
        insights.append(
            {
                "tone": "neutral",
                "title": "Idle inventory",
                "message": "Some inventory value has had no consumption in the last 30 days; consider purchasing adjustments.",
            }
        )
    if revenue == 0:
        insights.append(
            {
                "tone": "neutral",
                "title": "Start collecting signal",
                "message": "Record orders and recipe costs to unlock sales and margin recommendations.",
            }
        )
    return insights[:6]
