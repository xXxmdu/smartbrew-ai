"""Seed catalogue: the drinks the machine can make and what it holds in stock.

Implements the data half of Feature 2 (menu browsing). The availability rules
themselves live in inventory.py.
"""

from __future__ import annotations

from .models import Drink, Ingredient


def seed_ingredients() -> dict[str, Ingredient]:
    """Build the machine's starting ingredient stock.

    Input:
        None.

    Returns:
        dict[str, Ingredient]: Ingredient key mapped to a full hopper.
    """
    raw = [
        ("beans", "Coffee beans", "g", 1200.0, 1200.0, 60.0),
        ("water", "Water", "ml", 8000.0, 8000.0, 500.0),
        ("whole_milk", "Whole milk", "ml", 2000.0, 2000.0, 150.0),
        ("oat_milk", "Oat milk", "ml", 1500.0, 1500.0, 150.0),
        ("soy_milk", "Soy milk", "ml", 1000.0, 1000.0, 150.0),
        ("lactose_free_milk", "Lactose-free milk", "ml", 1000.0, 1000.0, 150.0),
        ("cocoa", "Cocoa powder", "g", 500.0, 500.0, 40.0),
        ("syrup", "Vanilla syrup", "ml", 600.0, 600.0, 50.0),
        ("cups", "Paper cups", "pcs", 200.0, 200.0, 10.0),
    ]
    return {
        key: Ingredient(key=key, label=label, unit=unit, level=lvl,
                        capacity=cap, minimum=minimum)
        for key, label, unit, lvl, cap, minimum in raw
    }


def seed_drinks() -> dict[str, Drink]:
    """Build the machine's drink catalogue.

    Recipe amounts are per standard (medium) cup; pricing.py scales them by cup
    size and strength.

    Input:
        None.

    Returns:
        dict[str, Drink]: Drink key mapped to its Drink definition.
    """
    raw = [
        # key, name, category, price, recipe, kcal, allergens, caffeine
        ("espresso", "Espresso", "Espresso based", 15.0,
         {"beans": 9.0, "water": 40.0, "cups": 1.0}, 5, [], 80),
        ("americano", "Americano", "Espresso based", 18.0,
         {"beans": 9.0, "water": 180.0, "cups": 1.0}, 8, [], 80),
        ("latte", "Caffe Latte", "Milk based", 28.0,
         {"beans": 9.0, "water": 40.0, "whole_milk": 180.0, "cups": 1.0},
         150, ["milk"], 80),
        ("cappuccino", "Cappuccino", "Milk based", 27.0,
         {"beans": 9.0, "water": 40.0, "whole_milk": 130.0, "cups": 1.0},
         110, ["milk"], 80),
        ("flat_white", "Flat White", "Milk based", 30.0,
         {"beans": 18.0, "water": 60.0, "whole_milk": 130.0, "cups": 1.0},
         130, ["milk"], 160),
        ("mocha", "Caffe Mocha", "Milk based", 33.0,
         {"beans": 9.0, "water": 40.0, "whole_milk": 160.0,
          "cocoa": 20.0, "cups": 1.0},
         230, ["milk"], 90),
        ("hot_chocolate", "Hot Chocolate", "Without coffee", 25.0,
         {"water": 60.0, "whole_milk": 200.0, "cocoa": 30.0, "cups": 1.0},
         280, ["milk"], 5),
    ]
    return {
        key: Drink(key=key, name=name, category=cat, base_price=price,
                   recipe=recipe, kcal=kcal, allergens=list(allergens),
                   caffeine_mg=caffeine)
        for key, name, cat, price, recipe, kcal, allergens, caffeine in raw
    }
