from decimal import Decimal


UNIT_FACTORS: dict[tuple[str, str], Decimal] = {
    ("گرم", "کیلوگرم"): Decimal("1000"),
    ("میلی‌لیتر", "لیتر"): Decimal("1000"),
    ("gram", "kilogram"): Decimal("1000"),
    ("g", "kg"): Decimal("1000"),
    ("milliliter", "liter"): Decimal("1000"),
    ("ml", "l"): Decimal("1000"),
}


def unit_factor(stock_unit: str, entered_unit: str) -> Decimal:
    stock = stock_unit.strip().casefold()
    entered = entered_unit.strip().casefold()
    if stock == entered:
        return Decimal("1")
    factor = UNIT_FACTORS.get((stock, entered))
    if factor is None:
        raise ValueError(f"Unit {entered_unit} cannot be converted to {stock_unit}")
    return factor


def stock_quantity(quantity: Decimal, entered_unit: str, stock_unit: str) -> Decimal:
    return Decimal(quantity) * unit_factor(stock_unit, entered_unit)


def unit_price(
    total_price: Decimal,
    quantity: Decimal,
    entered_unit: str,
    stock_unit: str,
) -> Decimal:
    normalized_quantity = stock_quantity(quantity, entered_unit, stock_unit)
    if normalized_quantity <= 0:
        raise ValueError("Package quantity must be greater than zero")
    return Decimal(total_price) / normalized_quantity
