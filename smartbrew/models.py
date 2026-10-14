"""Domain data types for SmartBrew AI.

Every type here is a plain dataclass with no behaviour beyond conversion to and
from JSON-compatible dictionaries. Business rules live in the service modules
(inventory, pricing, payments, ...) so that the data model stays easy to
serialise and to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

# Customisation option names shared across the system. Keeping them in one place
# means pricing, the CLI and the recommender cannot drift apart.
MILK_TYPES = ("none", "whole", "oat", "soy", "lactose_free")
STRENGTHS = (1, 2, 3, 4, 5)
CUP_SIZES = ("small", "medium", "large")
TEMPERATURES = ("warm", "hot", "extra_hot")
MOODS = ("neutral", "tired", "happy", "stressed")


@dataclass
class Ingredient:
    """A consumable held in the machine's hoppers or tanks.

    Attributes:
        key: Stable machine-readable identifier, e.g. "oat_milk".
        label: Human-readable name shown on the touchscreen.
        unit: Unit the level is measured in, e.g. "ml" or "g".
        level: Current amount remaining.
        capacity: Amount present when the hopper is full.
        minimum: Level at or below which the ingredient counts as depleted.
    """

    key: str
    label: str
    unit: str
    level: float
    capacity: float
    minimum: float

    @property
    def depleted(self) -> bool:
        """Report whether this ingredient is at or below its minimum threshold.

        Input:
            None (uses this ingredient's level and minimum).

        Returns:
            bool: True when the ingredient must not be used for a new drink.
        """
        return self.level <= self.minimum

    def to_dict(self) -> dict[str, Any]:
        """Convert this ingredient to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Ingredient":
        """Rebuild an Ingredient from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            Ingredient: The reconstructed ingredient.
        """
        return Ingredient(**raw)


@dataclass
class Drink:
    """A menu item together with the recipe needed to brew it.

    Attributes:
        key: Stable identifier, e.g. "latte".
        name: Display name.
        category: Menu grouping, e.g. "Espresso based".
        base_price: Price in SEK before customisation.
        recipe: Ingredient key mapped to the amount a single cup consumes.
        kcal: Energy content of the standard cup.
        allergens: Allergen labels that must be shown before ordering.
        caffeine_mg: Caffeine in the standard cup, used by the recommender.
    """

    key: str
    name: str
    category: str
    base_price: float
    recipe: dict[str, float]
    kcal: int
    allergens: list[str] = field(default_factory=list)
    caffeine_mg: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert this drink to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Drink":
        """Rebuild a Drink from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            Drink: The reconstructed drink.
        """
        return Drink(**raw)


@dataclass
class Customisation:
    """The adjustable parameters of a single order.

    Attributes:
        milk: One of MILK_TYPES.
        strength: Number of espresso shots, one of STRENGTHS.
        size: One of CUP_SIZES.
        temperature: One of TEMPERATURES.
        syrup_shots: Number of syrup pumps, 0 or more.
    """

    milk: str = "whole"
    strength: int = 2
    size: str = "medium"
    temperature: str = "hot"
    syrup_shots: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert this customisation to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Customisation":
        """Rebuild a Customisation from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            Customisation: The reconstructed customisation.
        """
        return Customisation(**raw)

    def describe(self) -> str:
        """Render the customisation as a short one-line summary.

        Input:
            None.

        Returns:
            str: Human-readable summary, e.g. "oat milk, strength 3, large".
        """
        parts = [f"{self.milk} milk", f"strength {self.strength}", self.size]
        if self.temperature != "hot":
            parts.append(self.temperature.replace("_", " "))
        if self.syrup_shots:
            parts.append(f"{self.syrup_shots} syrup")
        return ", ".join(parts)


@dataclass
class SavedRecipe:
    """A customer's named, reusable drink configuration.

    Attributes:
        name: The name chosen by the customer, unique within their profile.
        drink_key: Key of the Drink the recipe is based on.
        customisation: The stored customisation.
    """

    name: str
    drink_key: str
    customisation: Customisation

    def to_dict(self) -> dict[str, Any]:
        """Convert this saved recipe to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        return {
            "name": self.name,
            "drink_key": self.drink_key,
            "customisation": self.customisation.to_dict(),
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "SavedRecipe":
        """Rebuild a SavedRecipe from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            SavedRecipe: The reconstructed recipe.
        """
        return SavedRecipe(
            name=raw["name"],
            drink_key=raw["drink_key"],
            customisation=Customisation.from_dict(raw["customisation"]),
        )


@dataclass
class User:
    """A registered customer of the machine.

    The password is never held in clear text; only a salted hash is stored.

    Attributes:
        user_id: Unique login name.
        display_name: Name shown on the touchscreen greeting.
        email: Address used for e-mail receipts.
        password_salt: Random hex salt for the password hash.
        password_hash: Hex PBKDF2 hash of the password.
        nfc_token: Optional identifier of a linked NFC card.
        preferences: Default customisation applied to new orders.
        saved_recipes: Named recipes keyed by recipe name.
        loyalty_points: Current redeemable point balance.
        history: Drink keys previously purchased, most recent last.
    """

    user_id: str
    display_name: str
    email: str
    password_salt: str = ""
    password_hash: str = ""
    nfc_token: str | None = None
    preferences: Customisation = field(default_factory=Customisation)
    saved_recipes: dict[str, SavedRecipe] = field(default_factory=dict)
    loyalty_points: int = 0
    history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert this user to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values, recipes nested.
        """
        return {
            "user_id": self.user_id,
            "display_name": self.display_name,
            "email": self.email,
            "password_salt": self.password_salt,
            "password_hash": self.password_hash,
            "nfc_token": self.nfc_token,
            "preferences": self.preferences.to_dict(),
            "saved_recipes": {k: v.to_dict() for k, v in self.saved_recipes.items()},
            "loyalty_points": self.loyalty_points,
            "history": list(self.history),
        }

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "User":
        """Rebuild a User from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            User: The reconstructed user.
        """
        return User(
            user_id=raw["user_id"],
            display_name=raw["display_name"],
            email=raw["email"],
            password_salt=raw.get("password_salt", ""),
            password_hash=raw.get("password_hash", ""),
            nfc_token=raw.get("nfc_token"),
            preferences=Customisation.from_dict(raw.get("preferences", {})),
            saved_recipes={
                k: SavedRecipe.from_dict(v)
                for k, v in raw.get("saved_recipes", {}).items()
            },
            loyalty_points=raw.get("loyalty_points", 0),
            history=list(raw.get("history", [])),
        )


@dataclass
class Transaction:
    """An immutable record of one completed purchase.

    No payment credential is ever stored on this record; only the method name
    and a masked reference, satisfying NFR-06.

    Attributes:
        transaction_id: Unique identifier.
        timestamp: ISO-8601 time the purchase completed.
        user_id: Purchasing user, or "guest".
        drink_key: Drink that was bought.
        customisation: Full configuration as ordered.
        gross_amount: Price before any loyalty discount.
        discount: Amount removed by redeeming loyalty points.
        net_amount: Amount actually charged.
        payment_method: Method name, e.g. "contactless".
        payment_reference: Masked reference, e.g. "card ****4242".
        points_earned: Loyalty points awarded by this purchase.
        points_redeemed: Loyalty points consumed by this purchase.
        settled: False while the transaction is queued offline.
    """

    transaction_id: str
    timestamp: str
    user_id: str
    drink_key: str
    customisation: Customisation
    gross_amount: float
    discount: float
    net_amount: float
    payment_method: str
    payment_reference: str
    points_earned: int
    points_redeemed: int
    settled: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert this transaction to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        data = asdict(self)
        data["customisation"] = self.customisation.to_dict()
        return data

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "Transaction":
        """Rebuild a Transaction from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            Transaction: The reconstructed transaction.
        """
        data = dict(raw)
        data["customisation"] = Customisation.from_dict(data["customisation"])
        return Transaction(**data)


@dataclass
class FaultEvent:
    """One entry in the machine's diagnostic event log.

    Attributes:
        timestamp: ISO-8601 time the event was raised.
        code: Short machine-readable code, e.g. "GRINDER_JAM".
        message: Human-readable description for the admin dashboard.
        severity: One of "info", "warning", "error".
        cleared: True once a technician has resolved the fault.
    """

    timestamp: str
    code: str
    message: str
    severity: str
    cleared: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert this fault event to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Field names mapped to primitive values.
        """
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> "FaultEvent":
        """Rebuild a FaultEvent from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            FaultEvent: The reconstructed event.
        """
        return FaultEvent(**raw)


def now_iso() -> str:
    """Return the current local time as an ISO-8601 string.

    Centralised here so that tests can monkeypatch a single function instead of
    patching datetime in every module.

    Input:
        None.

    Returns:
        str: Current timestamp, seconds precision, e.g. "2026-10-14T09:31:07".
    """
    return datetime.now().replace(microsecond=0).isoformat()
