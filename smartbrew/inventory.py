"""Ingredient stock, availability rules and waste-bin monitoring.

Implements Feature 4 (stock and availability blocking) and the waste-bin half
of Feature 10. A drink is unavailable when any ingredient its recipe needs is
at or below its minimum threshold, or when there is not enough of it left for
this particular cup.
"""

from __future__ import annotations

from .models import Drink, Customisation, Ingredient
from .pricing import recipe_for

# Capacity of each waste container, in arbitrary "units" (one brewed drink
# contributes one unit of grounds and roughly one unit of waste water).
BIN_CAPACITY = 60
BIN_WARNING_RATIO = 0.9


class OutOfStock(Exception):
    """Raised when a drink is ordered that the machine cannot currently make."""


class BinsFull(Exception):
    """Raised when brewing is attempted while a waste container is full."""


class Inventory:
    """Holds ingredient levels and waste-bin levels for one machine.

    Attributes:
        ingredients: Ingredient key mapped to its Ingredient record.
        grounds_bin: Spent coffee grounds currently in the bin.
        waste_water: Waste water currently in the tank.
    """

    def __init__(self, ingredients: dict[str, Ingredient]) -> None:
        """Create an inventory over a set of ingredients.

        Input:
            ingredients (dict[str, Ingredient]): Starting stock, usually from
                catalogue.seed_ingredients().

        Returns:
            None.
        """
        self.ingredients = ingredients
        self.grounds_bin: int = 0
        self.waste_water: int = 0

    def missing_for(self, drink: Drink, customisation: Customisation) -> list[str]:
        """List the ingredients that prevent a drink from being made.

        Input:
            drink (Drink): The drink to check.
            customisation (Customisation): The configuration to check.

        Returns:
            list[str]: Labels of blocking ingredients; empty when the drink can
            be made right now.
        """
        blocking: list[str] = []
        for key, amount in recipe_for(drink, customisation).items():
            ing = self.ingredients.get(key)
            if ing is None:
                blocking.append(key)
                continue
            if ing.depleted or ing.level - amount < ing.minimum:
                blocking.append(ing.label)
        return blocking

    def is_available(self, drink: Drink, customisation: Customisation) -> bool:
        """Report whether a drink can be made as configured.

        Input:
            drink (Drink): The drink to check.
            customisation (Customisation): The configuration to check.

        Returns:
            bool: True when nothing blocks the order.
        """
        return not self.missing_for(drink, customisation)

    def consume(self, drink: Drink, customisation: Customisation) -> dict[str, float]:
        """Deduct the ingredients one configured drink uses and fill the bins.

        Input:
            drink (Drink): The drink being brewed.
            customisation (Customisation): The configuration being brewed.

        Returns:
            dict[str, float]: Ingredient key mapped to the amount deducted.

        Raises:
            BinsFull: When a waste container is already full.
            OutOfStock: When an ingredient is missing or below threshold.
        """
        if self.bins_full():
            raise BinsFull("Waste container full - empty it before brewing.")
        blocking = self.missing_for(drink, customisation)
        if blocking:
            raise OutOfStock(", ".join(blocking))

        used = recipe_for(drink, customisation)
        for key, amount in used.items():
            self.ingredients[key].level = round(
                self.ingredients[key].level - amount, 2
            )
        if "beans" in used:
            self.grounds_bin += 1
        self.waste_water += 1
        return used

    def refill(self, key: str) -> Ingredient:
        """Reset one ingredient to full capacity.

        Input:
            key (str): Ingredient key, e.g. "oat_milk".

        Returns:
            Ingredient: The refilled ingredient.

        Raises:
            KeyError: When no such ingredient exists.
        """
        ing = self.ingredients[key]
        ing.level = ing.capacity
        return ing

    def empty_bins(self) -> None:
        """Empty both waste containers.

        Input:
            None.

        Returns:
            None.
        """
        self.grounds_bin = 0
        self.waste_water = 0

    def bins_full(self) -> bool:
        """Report whether either waste container has reached capacity.

        Input:
            None.

        Returns:
            bool: True when brewing must be halted.
        """
        return self.grounds_bin >= BIN_CAPACITY or self.waste_water >= BIN_CAPACITY

    def bins_warning(self) -> bool:
        """Report whether either waste container is approaching capacity.

        Input:
            None.

        Returns:
            bool: True when the technician should be warned.
        """
        threshold = BIN_CAPACITY * BIN_WARNING_RATIO
        return self.grounds_bin >= threshold or self.waste_water >= threshold

    def low_ingredients(self) -> list[Ingredient]:
        """List ingredients currently at or below their minimum threshold.

        Input:
            None.

        Returns:
            list[Ingredient]: Depleted ingredients, in catalogue order.
        """
        return [i for i in self.ingredients.values() if i.depleted]

    def to_dict(self) -> dict:
        """Convert the inventory to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Ingredient levels plus both bin levels.
        """
        return {
            "ingredients": {k: v.to_dict() for k, v in self.ingredients.items()},
            "grounds_bin": self.grounds_bin,
            "waste_water": self.waste_water,
        }

    @staticmethod
    def from_dict(raw: dict) -> "Inventory":
        """Rebuild an Inventory from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            Inventory: The reconstructed inventory.
        """
        inv = Inventory(
            {k: Ingredient.from_dict(v) for k, v in raw["ingredients"].items()}
        )
        inv.grounds_bin = raw.get("grounds_bin", 0)
        inv.waste_water = raw.get("waste_water", 0)
        return inv
