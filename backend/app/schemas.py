from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.models import (
    ApprovalStatus,
    NeedSource,
    NeedPriority,
    OrderStatus,
    PaymentMethod,
    PurchaseStatus,
    UserRole,
)

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=80)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
PositiveMoney = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
PositiveQuantity = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PublicConfig(BaseModel):
    app_name: str
    business_name: str
    tagline: str
    primary_color: str
    logo_url: str | None
    locale: str
    timezone: str
    currency_label: str


class LoginRequest(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=128)


class UserBrief(ORMModel):
    id: int
    username: str
    full_name: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserBrief


class UserCreate(BaseModel):
    username: Username
    full_name: str = Field(min_length=2, max_length=160)
    password: Password
    role: UserRole

    @field_validator("role")
    @classmethod
    def no_second_root(cls, value: UserRole) -> UserRole:
        if value == UserRole.ROOT:
            raise ValueError("Create manager accounts here; the deployment root is unique")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    password: Password | None = None
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def no_root_role(cls, value: UserRole | None) -> UserRole | None:
        if value == UserRole.ROOT:
            raise ValueError("Manager accounts cannot be promoted to deployment root")
        return value


class UserRead(UserBrief):
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")


class CategoryRead(ORMModel):
    id: int
    name: str
    description: str | None
    color: str


class InventoryItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    category_id: int | None = None
    unit: str = Field(default="unit", min_length=1, max_length=32)
    reorder_level: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=3)
    target_stock_level: Decimal = Field(
        default=Decimal("0"), ge=0, max_digits=14, decimal_places=3
    )
    auto_reorder_enabled: bool = False
    selling_price: PositiveMoney = Decimal("0")
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def valid_auto_reorder_range(self):
        if self.auto_reorder_enabled and self.target_stock_level <= self.reorder_level:
            raise ValueError("Target stock must be greater than the reorder level")
        return self


class InventoryItemUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: int | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    reorder_level: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    target_stock_level: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    auto_reorder_enabled: bool | None = None
    description: str | None = Field(default=None, max_length=5000)
    is_active: bool | None = None


class InventoryItemRead(ORMModel):
    id: int
    sku: str
    name: str
    category_id: int | None
    unit: str
    current_quantity: Decimal
    reorder_level: Decimal
    target_stock_level: Decimal
    auto_reorder_enabled: bool
    average_cost: Decimal
    last_purchase_price: Decimal
    selling_price: Decimal
    image_path: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    category: CategoryRead | None = None


class PaginatedItems(BaseModel):
    items: list[InventoryItemRead]
    total: int
    page: int
    page_size: int


class MovementCreate(BaseModel):
    movement_type: Literal["receive", "adjust", "waste"]
    quantity: Decimal = Field(max_digits=14, decimal_places=3)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: Decimal, info):
        movement_type = info.data.get("movement_type")
        if movement_type == "receive" and value <= 0:
            raise ValueError("Received quantity must be positive")
        if movement_type == "waste" and value <= 0:
            raise ValueError("Waste quantity must be positive")
        if movement_type == "adjust" and value == 0:
            raise ValueError("Adjustment cannot be zero")
        return value


class MovementRead(ORMModel):
    id: int
    item_id: int
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal | None
    quantity_before: Decimal
    quantity_after: Decimal
    reason: str
    created_by_id: int
    created_at: datetime


class PurchaseLineCreate(BaseModel):
    inventory_item_id: int
    quantity: PositiveQuantity
    purchase_unit: str = Field(min_length=1, max_length=32)
    conversion_factor: PositiveQuantity = Decimal("1")
    line_total: PositiveMoney


class PurchaseReceiptCreate(BaseModel):
    supplier_name: str | None = Field(default=None, max_length=160)
    invoice_number: str | None = Field(default=None, max_length=100)
    purchased_at: datetime
    discount: PositiveMoney = Decimal("0")
    extra_cost: PositiveMoney = Decimal("0")
    notes: str | None = Field(default=None, max_length=1000)
    lines: list[PurchaseLineCreate] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [line.inventory_item_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each inventory item can appear only once per receipt")
        subtotal = sum((line.line_total for line in self.lines), Decimal("0"))
        if self.discount > subtotal + self.extra_cost:
            raise ValueError("Discount cannot exceed the receipt value")
        return self


class PurchaseLineRead(ORMModel):
    id: int
    inventory_item_id: int
    item_name: str
    quantity: Decimal
    purchase_unit: str
    conversion_factor: Decimal
    stock_quantity: Decimal
    stock_unit: str
    line_total: Decimal
    allocated_cost: Decimal
    landed_total: Decimal
    unit_cost: Decimal


class PurchaseReceiptRead(ORMModel):
    id: int
    receipt_number: str
    supplier_name: str | None
    invoice_number: str | None
    purchased_at: datetime
    subtotal: Decimal
    discount: Decimal
    extra_cost: Decimal
    total_cost: Decimal
    status: PurchaseStatus
    notes: str | None
    created_by_id: int
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    created_by: UserBrief
    lines: list[PurchaseLineRead]


class PaginatedPurchases(BaseModel):
    items: list[PurchaseReceiptRead]
    total: int
    page: int
    page_size: int


class PurchaseVoid(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PriceRequestCreate(BaseModel):
    requested_price: PositiveMoney
    reason: str = Field(min_length=3, max_length=500)


class ApprovalDecision(BaseModel):
    status: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=500)


class PriceRequestRead(ORMModel):
    id: int
    item_id: int
    old_price: Decimal
    requested_price: Decimal
    reason: str
    status: ApprovalStatus
    requested_by_id: int
    decided_by_id: int | None
    decision_note: str | None
    created_at: datetime
    decided_at: datetime | None
    item: InventoryItemRead
    requested_by: UserBrief


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=5, max_length=32, pattern=r"^[0-9+() -]+$")
    notes: str | None = Field(default=None, max_length=500)


class CustomerRead(ORMModel):
    id: int
    name: str
    phone: str
    notes: str | None
    created_at: datetime


class MenuCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    sort_order: int = Field(default=0, ge=0, le=9999)
    is_active: bool = True


class MenuCategoryRead(ORMModel):
    id: int
    name: str
    description: str | None
    color: str
    sort_order: int
    is_active: bool


class MenuItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str = Field(default="عمومی", min_length=1, max_length=100)
    category_id: int | None = None
    selling_price: PositiveMoney
    inventory_item_id: int | None = None
    stock_quantity_per_sale: PositiveQuantity = Decimal("1")
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True


class MenuItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    category_id: int | None = None
    selling_price: PositiveMoney | None = None
    inventory_item_id: int | None = None
    stock_quantity_per_sale: PositiveQuantity | None = None
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class MenuItemRead(ORMModel):
    id: int
    name: str
    category: str
    category_id: int | None
    selling_price: Decimal
    inventory_item_id: int | None
    stock_quantity_per_sale: Decimal
    description: str | None
    image_path: str | None
    is_active: bool
    calculated_cost: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    margin_percent: Decimal = Decimal("0")
    recipe_configured: bool = False
    is_available: bool = True
    max_available_quantity: int | None = None


class RecipeIngredientWrite(BaseModel):
    inventory_item_id: int
    quantity: PositiveQuantity
    unit: str = Field(min_length=1, max_length=32)


class RecipeUpsert(BaseModel):
    menu_item_id: int
    yield_quantity: PositiveQuantity = Decimal("1")
    preparation_minutes: int = Field(default=0, ge=0, le=1440)
    instructions: str = Field(default="", max_length=20000)
    notes: str | None = Field(default=None, max_length=5000)
    ingredients: list[RecipeIngredientWrite] = Field(min_length=1)


class RecipeIngredientRead(ORMModel):
    id: int
    inventory_item_id: int
    quantity: Decimal
    unit: str
    inventory_item: InventoryItemRead


class RecipeRead(ORMModel):
    id: int
    menu_item_id: int
    yield_quantity: Decimal
    preparation_minutes: int
    instructions: str
    notes: str | None
    menu_item: MenuItemRead
    ingredients: list[RecipeIngredientRead]
    calculated_cost: Decimal = Decimal("0")
    food_cost_percent: Decimal = Decimal("0")


class OrderItemCreate(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=999)
    notes: str | None = Field(default=None, max_length=300)


class OrderCreate(BaseModel):
    customer_id: int | None = None
    customer: CustomerCreate | None = None
    discount: PositiveMoney = Decimal("0")
    payment_method: PaymentMethod = PaymentMethod.CARD
    notes: str | None = Field(default=None, max_length=500)
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)


class OrderItemRead(ORMModel):
    id: int
    menu_item_id: int
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    unit_cost: Decimal
    line_cost: Decimal
    notes: str | None


class OrderRead(ORMModel):
    id: int
    order_number: str
    status: OrderStatus
    customer_id: int | None
    customer_name: str
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    payment_method: PaymentMethod
    notes: str | None
    created_by_id: int
    created_at: datetime
    items: list[OrderItemRead]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class DailyNeedCreate(BaseModel):
    required_date: date
    inventory_item_id: int | None = None
    item_name: str = Field(min_length=1, max_length=160)
    quantity: PositiveQuantity
    unit: str = Field(min_length=1, max_length=32)
    priority: NeedPriority = NeedPriority.NORMAL
    notes: str | None = Field(default=None, max_length=500)


class DailyNeedRead(ORMModel):
    id: int
    required_date: date
    inventory_item_id: int | None
    item_name: str
    quantity: Decimal
    unit: str
    priority: NeedPriority
    source: NeedSource
    status: ApprovalStatus
    notes: str | None
    requested_by_id: int
    decision_note: str | None
    created_at: datetime
    requested_by: UserBrief


class NotificationRead(ORMModel):
    id: int
    kind: str
    title: str
    message: str
    entity_type: str | None
    entity_id: str | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None


class DashboardSummary(BaseModel):
    sales_today: Decimal
    orders_today: int
    average_order_value: Decimal
    low_stock_count: int
    pending_price_approvals: int
    pending_daily_needs: int
    automatic_purchase_needs: int
    unread_notifications: int
    active_users: int
    orders_in_kitchen: int
    sales_change_percent: Decimal
    recent_orders: list[OrderRead]
    low_stock_items: list[InventoryItemRead]


class AuditRead(ORMModel):
    id: int
    actor_id: int | None
    actor_username: str
    action: str
    category: str
    entity_type: str
    entity_id: str | None
    summary: str
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: datetime


class AuditPage(BaseModel):
    items: list[AuditRead]
    total: int
    page: int
    page_size: int
