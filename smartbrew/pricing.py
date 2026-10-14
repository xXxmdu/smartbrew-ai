"""Price and recipe calculation for a customised order.

Implements Feature 3 (real-time customisation with live pricing). Both the
price and the ingredient consumption of an order depend on the same
customisation, so they are derived together here to keep them consistent.
"""

from __future__ import annotations

from .models import Customisation, Drink

# Multiplier applied to the liquid part of a recipe for each cup size.
SIZE_FACTOR = {"small": 0.75, "medium": 1.0, "large": 1.35}

# Surcharge in SEK added for each cup size.
SIZE_SURCHARGE = {"small": -3.0, "medium": 0.0, "large": 5.0}

# Surcharge in SEK for each non-default milk type.
MILK_SURCHARGE = {
    "none": 0.0,
    "whole": 0.0,
    "oat": 4.0,
    "soy": 4.0,
    "lactose_free": 5.0,
}

# Ingredient key supplying each milk type. "none" consumes no milk.
MILK_INGREDIENT = {
    "none": None,
    "whole": "whole_milk",
    "oat": "oat_milk",
    "soy": "soy_milk",
    "lactose_free": "lactose_free_milk",
}

# Surcharge per espresso shot beyond the drink's standard two.
EXTRA_SHOT_PRICE = 5.0

# Surcharge per syrup pump.
SYRUP_PRICE = 3.0

# Grams of beans in one espresso shot.
BEANS_PER_SHOT = 9.0

# Millilitres of syrup in one pump.
SYRUP_PER_SHOT = 10.0


def price_of(drink: Drink, customisation: Customisation) -> float:
    """Calculate the price of one drink as configured.

    Input:
        drink (Drink): The catalogue item being ordered.
        customisation (Customisation): The chosen options.

    Returns:
        float: Price in SEK, rounded to two decimals, never below zero.
    """
    price = drink.base_price
    price += SIZE_SURCHARGE.get(customisation.size, 0.0)
    if drink.recipe.get("whole_milk") or customisation.milk != "none":
        price += MILK_SURCHARGE.get(customisation.milk, 0.0)
    extra_shots = max(0, customisation.strength - 2)
    price += extra_shots * EXTRA_SHOT_PRICE
    price += customisation.syrup_shots * SYRUP_PRICE
    return round(max(price, 0.0), 2)


def recipe_for(drink: Drink, customisation: Customisation) -> dict[str, float]:
    """Calculate the actual ingredient consumption of one configured drink.

    The stored recipe describes a medium cup at strength 2 with whole milk.
    This function rescales it for the chosen size, swaps in the chosen milk and
    adds beans and syrup for the chosen strength and syrup shots.

    Input:
        drink (Drink): The catalogue item being ordered.
        customisation (Customisation): The chosen options.

    Returns:
        dict[str, float]: Ingredient key mapped to the amount consumed.
    """
    factor = SIZE_FACTOR.get(customisation.size, 1.0)
    consumption: dict[str, float] = {}

    for key, amount in drink.recipe.items():
        if key == "cups":
            consumption["cups"] = amount
            continue
        if key == "whole_milk":
            # Milk is redirected to whichever milk the customer picked.
            target = MILK_INGREDIENT.get(customisation.milk)
            if target is None:
                continue
            consumption[target] = consumption.get(target, 0.0) + amount * factor
            continue
        consumption[key] = consumption.get(key, 0.0) + amount * factor

    if "beans" in drink.recipe:
        # Replace the standard two-shot bean amount with the chosen strength.
        shots_beyond_standard = customisation.strength - 2
        if shots_beyond_standard:
            consumption["beans"] = round(
                consumption.get("beans", 0.0)
                + shots_beyond_standard * BEANS_PER_SHOT,
                2,
            )

    if customisation.syrup_shots:
        consumption["syrup"] = round(
            consumption.get("syrup", 0.0)
            + customisation.syrup_shots * SYRUP_PER_SHOT,
            2,
        )

    return {k: round(v, 2) for k, v in consumption.items() if v > 0}


def price_breakdown(drink: Drink, customisation: Customisation) -> list[tuple[str, float]]:
    """Produce an itemised explanation of how the price was reached.

    Used by the CLI so the customer sees the price change as they customise,
    rather than only a final number.

    Input:
        drink (Drink): The catalogue item being ordered.
        customisation (Customisation): The chosen options.

    Returns:
        list[tuple[str, float]]: (label, amount) pairs, ending with ("Total", x).
    """
    lines: list[tuple[str, float]] = [(f"{drink.name} base", drink.base_price)]

    size_delta = SIZE_SURCHARGE.get(customisation.size, 0.0)
    if size_delta:
        lines.append((f"Cup size: {customisation.size}", size_delta))

    milk_delta = MILK_SURCHARGE.get(customisation.milk, 0.0)
    if milk_delta and (drink.recipe.get("whole_milk") or customisation.milk != "none"):
        lines.append((f"{customisation.milk.replace('_', ' ')} milk", milk_delta))

    extra_shots = max(0, customisation.strength - 2)
    if extra_shots:
        lines.append(
            (f"{extra_shots} extra shot(s)", extra_shots * EXTRA_SHOT_PRICE)
        )

    if customisation.syrup_shots:
        lines.append(
            (f"{customisation.syrup_shots} syrup pump(s)",
             customisation.syrup_shots * SYRUP_PRICE)
        )

    lines.append(("Total", price_of(drink, customisation)))
    return lines
