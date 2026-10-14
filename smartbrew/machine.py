"""The SmartBrew AI machine: the facade that ties the services together.

Every feature the CLI and the demonstration expose is reachable through this
class. Keeping the orchestration in one place means the user interface holds no
business rules, and the whole machine can be driven from tests without a
terminal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from . import catalogue, loyalty, receipts
from .accounts import AccountService, AuthError, hash_password, verify_password
from .faults import EventLog
from .inventory import BinsFull, Inventory, OutOfStock
from .models import Customisation, Drink, Transaction, User, now_iso
from .mood import CameraUnavailable, MoodReading, MoodSensor
from .payments import PaymentDeclined, PaymentResult, PaymentTerminal
from .pricing import price_breakdown, price_of
from .recommender import Scored, Weather, WeatherProvider, rank_menu

DEFAULT_TECHNICIAN_PIN = "4242"


class MachineError(Exception):
    """Raised when an operation is not valid in the machine's current state."""


@dataclass
class OrderDraft:
    """An order being configured but not yet paid for.

    Attributes:
        drink: The drink selected.
        customisation: The current configuration, mutated as the user adjusts.
        user: The logged-in user, or None for a guest.
    """

    drink: Drink
    customisation: Customisation
    user: User | None = None

    def price(self) -> float:
        """Return the current price of this draft.

        Input:
            None.

        Returns:
            float: Price in SEK for the current configuration.
        """
        return price_of(self.drink, self.customisation)

    def breakdown(self) -> list[tuple[str, float]]:
        """Return the itemised price explanation for this draft.

        Input:
            None.

        Returns:
            list[tuple[str, float]]: (label, amount) pairs ending with Total.
        """
        return price_breakdown(self.drink, self.customisation)


@dataclass
class PurchaseOutcome:
    """Everything produced by a completed purchase.

    Attributes:
        transaction: The stored transaction record.
        receipt: Rendered receipt text (QR view or e-mail view).
        payment: The authorisation result.
        warnings: Non-fatal messages, e.g. a waste-bin warning.
    """

    transaction: Transaction
    receipt: str
    payment: PaymentResult
    warnings: list[str] = field(default_factory=list)


class Machine:
    """One SmartBrew AI coffee machine.

    Attributes:
        drinks: The catalogue, drink key mapped to Drink.
        inventory: Ingredient and waste-bin state.
        accounts: Registered users.
        terminal: The payment terminal.
        log: The diagnostic event log.
        mood_sensor: The mood camera.
        weather: The weather provider.
        transactions: Completed transactions, oldest first.
        current_user: The user currently logged in, if any.
        technician_mode: Whether administrative mode is unlocked.
    """

    def __init__(self) -> None:
        """Create a machine with a full catalogue and full hoppers.

        Input:
            None.

        Returns:
            None.
        """
        self.drinks: dict[str, Drink] = catalogue.seed_drinks()
        self.inventory = Inventory(catalogue.seed_ingredients())
        self.accounts = AccountService()
        self.terminal = PaymentTerminal(online=True)
        self.log = EventLog()
        self.mood_sensor = MoodSensor()
        self.weather = WeatherProvider(temperature_c=5.0, online=True)
        self.transactions: list[Transaction] = []
        self.current_user: User | None = None
        self.technician_mode = False
        self._pin_salt, self._pin_hash = hash_password(DEFAULT_TECHNICIAN_PIN)

    # ------------------------------------------------------------------
    # Feature 1 - accounts, login, preference profiles
    # ------------------------------------------------------------------

    def register(
        self,
        user_id: str,
        display_name: str,
        email: str,
        password: str,
        nfc_token: str | None = None,
    ) -> User:
        """Create an account and log it in.

        Input:
            user_id (str): Desired unique login name.
            display_name (str): Name shown in the greeting.
            email (str): Address for e-mail receipts.
            password (str): Clear-text password, at least 6 characters.
            nfc_token (str | None): Optional NFC card to link.

        Returns:
            User: The newly created, now logged-in user.

        Raises:
            AuthError: When the account cannot be created.
        """
        user = self.accounts.register(user_id, display_name, email, password,
                                      nfc_token)
        self.current_user = user
        return user

    def login(self, user_id: str, password: str) -> User:
        """Log in with a user id and password.

        Input:
            user_id (str): The login name.
            password (str): The clear-text password.

        Returns:
            User: The authenticated user.

        Raises:
            AuthError: When authentication fails.
        """
        self.current_user = self.accounts.login(user_id, password)
        return self.current_user

    def login_nfc(self, nfc_token: str) -> User:
        """Log in with a single NFC card tap.

        Input:
            nfc_token (str): Identifier read from the card.

        Returns:
            User: The authenticated user.

        Raises:
            AuthError: When the card is not linked to an account.
        """
        self.current_user = self.accounts.login_with_nfc(nfc_token)
        return self.current_user

    def logout(self) -> None:
        """Log the current user out and leave technician mode.

        Input:
            None.

        Returns:
            None.
        """
        self.current_user = None
        self.technician_mode = False

    def set_preferences(self, **kwargs: object) -> Customisation:
        """Update the logged-in user's default customisation.

        Input:
            **kwargs: Any Customisation field, e.g. milk="oat", strength=3.

        Returns:
            Customisation: The stored defaults after the update.

        Raises:
            MachineError: When nobody is logged in.
            TypeError: When an unknown field is given.
        """
        user = self._require_user()
        current = user.preferences.to_dict()
        for key, value in kwargs.items():
            if key not in current:
                raise TypeError(f"Unknown preference '{key}'.")
            current[key] = value
        user.preferences = Customisation.from_dict(current)
        return user.preferences

    # ------------------------------------------------------------------
    # Feature 2 - menu browsing;  Feature 4 - availability
    # ------------------------------------------------------------------

    def menu(self, customisation: Customisation | None = None) -> list[tuple[Drink, bool, list[str]]]:
        """List the catalogue with current availability.

        Input:
            customisation (Customisation | None): Configuration to test
                availability against. The logged-in user's defaults are used
                when None.

        Returns:
            list[tuple[Drink, bool, list[str]]]: (drink, available, blocking
            ingredient labels) for every drink, in catalogue order.
        """
        cust = customisation or self._default_customisation()
        rows = []
        for drink in self.drinks.values():
            blocking = self.inventory.missing_for(drink, cust)
            rows.append((drink, not blocking, blocking))
        return rows

    def available_drinks(self, customisation: Customisation | None = None) -> list[Drink]:
        """List only the drinks that can be made right now.

        Input:
            customisation (Customisation | None): Configuration to test
                against; the user's defaults are used when None.

        Returns:
            list[Drink]: Drinks with no blocking ingredients.
        """
        return [d for d, ok, _ in self.menu(customisation) if ok]

    # ------------------------------------------------------------------
    # Feature 6 - recommendations and mood
    # ------------------------------------------------------------------

    def read_mood(self, frame: bytes | None) -> MoodReading | None:
        """Classify a camera frame, tolerating a camera failure.

        A camera fault must not stop a customer ordering (NFR-10), so a failure
        is logged and reported as "no reading" rather than raised.

        Input:
            frame (bytes | None): Raw frame bytes, or None if none captured.

        Returns:
            MoodReading | None: The reading, or None when unavailable.
        """
        try:
            return self.mood_sensor.analyse(frame)
        except CameraUnavailable as exc:
            self.log.raise_fault("CAMERA_FAULT", str(exc))
            return None

    def recommendations(
        self, mood: MoodReading | None = None, hour: int | None = None
    ) -> list[Scored]:
        """Rank the available menu for the current context.

        Input:
            mood (MoodReading | None): Optional detected mood.
            hour (int | None): Hour of day 0-23; the system clock is used when
                None.

        Returns:
            list[Scored]: Available drinks sorted by descending score.
        """
        current_hour = datetime.now().hour if hour is None else hour
        return rank_menu(
            self.available_drinks(),
            self.current_user,
            current_hour,
            self.weather.current(),
            mood,
        )

    # ------------------------------------------------------------------
    # Feature 3 - ordering and customisation
    # ------------------------------------------------------------------

    def start_order(self, drink_key: str) -> OrderDraft:
        """Begin an order, pre-filled with the user's preferences.

        Input:
            drink_key (str): Key of the drink to order.

        Returns:
            OrderDraft: A draft ready to customise.

        Raises:
            MachineError: When the drink key is unknown or a blocking fault is
                active.
        """
        self._require_serviceable()
        drink = self.drinks.get(drink_key)
        if drink is None:
            raise MachineError(f"No drink called '{drink_key}'.")
        return OrderDraft(
            drink=drink,
            customisation=self._default_customisation(),
            user=self.current_user,
        )

    def customise(self, draft: OrderDraft, **kwargs: object) -> float:
        """Change one or more options on a draft and return the new price.

        Input:
            draft (OrderDraft): The draft being configured.
            **kwargs: Any Customisation field, e.g. milk="oat", size="large".

        Returns:
            float: The recalculated price in SEK.

        Raises:
            TypeError: When an unknown option is given.
            ValueError: When a value is outside the allowed set.
        """
        current = draft.customisation.to_dict()
        for key, value in kwargs.items():
            if key not in current:
                raise TypeError(f"Unknown option '{key}'.")
            current[key] = value
        self._validate_customisation(current)
        draft.customisation = Customisation.from_dict(current)
        return draft.price()

    # ------------------------------------------------------------------
    # Feature 5 - payment;  Feature 7 - loyalty;  Feature 9 - receipts and log
    # ------------------------------------------------------------------

    def place_order(
        self,
        draft: OrderDraft,
        method: str,
        card_reference: str,
        redeem_points: int = 0,
        receipt: str = "qr",
    ) -> PurchaseOutcome:
        """Pay for, brew and record a drink.

        The order of operations matters: points are applied, payment is
        authorised, and only then are ingredients consumed. A declined payment
        therefore leaves the drink unbrewed and the stock untouched (FR-19).

        Input:
            draft (OrderDraft): The configured order.
            method (str): One of payments.METHODS.
            card_reference (str): Raw card reference from the reader.
            redeem_points (int): Loyalty points to redeem, 0 for none.
            receipt (str): "qr" or "email".

        Returns:
            PurchaseOutcome: Transaction, rendered receipt, payment result and
            any warnings.

        Raises:
            MachineError: When a blocking fault is active or the receipt choice
                is invalid.
            LoyaltyError: When the redemption is not permitted.
            PaymentDeclined: When the payment is refused.
            OutOfStock: When an ingredient became unavailable.
            BinsFull: When a waste container is full.
        """
        self._require_serviceable()
        if receipt not in ("qr", "email"):
            raise MachineError("Receipt must be 'qr' or 'email'.")
        if receipt == "email" and self.current_user is None:
            raise MachineError("An e-mail receipt needs a logged-in account.")

        gross = draft.price()

        balance = self.current_user.loyalty_points if self.current_user else 0
        if redeem_points and self.current_user is None:
            raise MachineError("Loyalty points need a logged-in account.")
        redemption = loyalty.redeem(balance, gross, redeem_points)
        net = round(gross - redemption.discount, 2)

        payment = self.terminal.authorise(net, method, card_reference)

        # Payment is authorised; now commit the physical side.
        self.inventory.consume(draft.drink, draft.customisation)

        earned = loyalty.points_for(net)
        transaction = Transaction(
            transaction_id=uuid.uuid4().hex[:12],
            timestamp=now_iso(),
            user_id=self.current_user.user_id if self.current_user else "guest",
            drink_key=draft.drink.key,
            customisation=draft.customisation,
            gross_amount=gross,
            discount=redemption.discount,
            net_amount=net,
            payment_method=payment.method,
            payment_reference=payment.reference,
            points_earned=earned,
            points_redeemed=redemption.points_used,
            settled=not payment.offline,
        )
        self.transactions.append(transaction)
        if payment.offline:
            self.terminal.queue(transaction.transaction_id)

        if self.current_user:
            self.current_user.loyalty_points = redemption.remaining_balance + earned
            self.current_user.history.append(draft.drink.key)

        warnings = self._post_brew_checks()

        if receipt == "qr":
            body = receipts.deliver_qr(transaction, draft.drink.name)
        else:
            body = receipts.deliver_email(
                transaction, draft.drink.name, self.current_user.email
            )

        return PurchaseOutcome(transaction, body, payment, warnings)

    def transaction_log(self) -> list[Transaction]:
        """Return every completed transaction, oldest first.

        Input:
            None.

        Returns:
            list[Transaction]: The full log.
        """
        return list(self.transactions)

    # ------------------------------------------------------------------
    # Feature 8 - saved recipes
    # ------------------------------------------------------------------

    def save_current_as(self, draft: OrderDraft, name: str):
        """Store the draft's configuration on the user's profile.

        Input:
            draft (OrderDraft): The configured order to remember.
            name (str): Customer-chosen recipe name.

        Returns:
            SavedRecipe: The stored recipe.

        Raises:
            MachineError: When nobody is logged in.
            ValueError: When the name is blank.
        """
        user = self._require_user()
        return self.accounts.save_recipe(
            user, name, draft.drink.key, draft.customisation
        )

    def order_saved(self, name: str) -> OrderDraft:
        """Rebuild a draft from a saved recipe, for one-touch reordering.

        Input:
            name (str): The recipe name.

        Returns:
            OrderDraft: A draft configured exactly as saved.

        Raises:
            MachineError: When nobody is logged in, the recipe is unknown, or
                its drink has left the catalogue.
        """
        user = self._require_user()
        recipe = user.saved_recipes.get(name.strip())
        if recipe is None:
            raise MachineError(f"No saved recipe called '{name}'.")
        drink = self.drinks.get(recipe.drink_key)
        if drink is None:
            raise MachineError(
                f"Recipe '{name}' refers to a drink that is no longer on the menu."
            )
        self._require_serviceable()
        return OrderDraft(drink=drink, customisation=recipe.customisation, user=user)

    # ------------------------------------------------------------------
    # Feature 10 - technician mode
    # ------------------------------------------------------------------

    def technician_login(self, pin: str) -> bool:
        """Unlock administrative mode with the technician PIN.

        Failed attempts are logged (NFR-05).

        Input:
            pin (str): The PIN entered on the keypad.

        Returns:
            bool: True when the PIN was accepted.
        """
        if verify_password(pin, self._pin_salt, self._pin_hash):
            self.technician_mode = True
            return True
        self.log.raise_fault("AUTH_FAILED", "incorrect technician PIN")
        return False

    def technician_logout(self) -> None:
        """Leave administrative mode.

        Input:
            None.

        Returns:
            None.
        """
        self.technician_mode = False

    def refill(self, ingredient_key: str):
        """Refill one ingredient to capacity and clear its low-level fault.

        Input:
            ingredient_key (str): Ingredient to refill, e.g. "oat_milk".

        Returns:
            Ingredient: The refilled ingredient.

        Raises:
            MachineError: When not in technician mode or the key is unknown.
        """
        self._require_technician()
        try:
            ing = self.inventory.refill(ingredient_key)
        except KeyError:
            raise MachineError(f"No ingredient called '{ingredient_key}'.") from None
        if not self.inventory.low_ingredients():
            self.log.clear("LOW_INGREDIENT")
        return ing

    def empty_bins(self) -> None:
        """Empty both waste containers and clear their faults.

        Input:
            None.

        Returns:
            None.

        Raises:
            MachineError: When not in technician mode.
        """
        self._require_technician()
        self.inventory.empty_bins()
        self.log.clear("BIN_FULL")
        self.log.clear("BIN_NEAR_FULL")

    def report_fault(self, code: str, detail: str = ""):
        """Raise a fault, as the machine's own sensors would.

        Exposed so the demonstration can trigger a fault deterministically.

        Input:
            code (str): A key of faults.KNOWN_FAULTS, or any other string.
            detail (str): Optional extra text.

        Returns:
            FaultEvent: The event appended to the log.
        """
        return self.log.raise_fault(code, detail)

    def clear_fault(self, code: str) -> int:
        """Mark a fault as resolved.

        Input:
            code (str): The fault code to clear.

        Returns:
            int: How many events were cleared.

        Raises:
            MachineError: When not in technician mode.
        """
        self._require_technician()
        return self.log.clear(code)

    def dashboard(self) -> dict:
        """Produce the administrative dashboard view.

        Input:
            None.

        Returns:
            dict: Ingredient levels, bin levels, active faults, pending
            settlements and connectivity.

        Raises:
            MachineError: When not in technician mode.
        """
        self._require_technician()
        return {
            "ingredients": [
                {
                    "label": i.label,
                    "level": i.level,
                    "capacity": i.capacity,
                    "unit": i.unit,
                    "depleted": i.depleted,
                }
                for i in self.inventory.ingredients.values()
            ],
            "grounds_bin": self.inventory.grounds_bin,
            "waste_water": self.inventory.waste_water,
            "bins_full": self.inventory.bins_full(),
            "active_faults": [e.message for e in self.log.active()],
            "pending_settlements": list(self.terminal.pending),
            "online": self.terminal.online,
            "transactions": len(self.transactions),
        }

    # ------------------------------------------------------------------
    # Connectivity (NFR-02, NFR-03)
    # ------------------------------------------------------------------

    def set_network(self, online: bool) -> list[str]:
        """Change connectivity and settle anything queued when it returns.

        Input:
            online (bool): True when the network is available.

        Returns:
            list[str]: Transaction ids settled by this call; empty when going
            offline or when nothing was queued.
        """
        was_online = self.terminal.online
        self.terminal.set_online(online)
        self.weather.online = online
        if online and not was_online:
            self.log.raise_fault("NETWORK_BACK")
            settled = self.terminal.settle_pending()
            for tid in settled:
                for tx in self.transactions:
                    if tx.transaction_id == tid:
                        tx.settled = True
            return settled
        if not online and was_online:
            self.log.raise_fault("NETWORK_LOST")
        return []

    # ------------------------------------------------------------------
    # Persistence (NFR-09)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """Capture the whole machine state as a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: State suitable for storage.save_state().
        """
        return {
            "version": 1,
            "inventory": self.inventory.to_dict(),
            "accounts": self.accounts.to_dict(),
            "terminal": self.terminal.to_dict(),
            "log": self.log.to_dict(),
            "transactions": [t.to_dict() for t in self.transactions],
            "pin": {"salt": self._pin_salt, "hash": self._pin_hash},
            "weather": {
                "temperature_c": self.weather.temperature_c,
                "online": self.weather.online,
            },
        }

    @staticmethod
    def restore(state: dict) -> "Machine":
        """Rebuild a machine from a snapshot.

        A snapshot missing a section falls back to that section's defaults, so
        an older state file still boots.

        Input:
            state (dict): Dictionary previously produced by snapshot().

        Returns:
            Machine: The restored machine, with nobody logged in.
        """
        machine = Machine()
        if state.get("inventory"):
            machine.inventory = Inventory.from_dict(state["inventory"])
        if state.get("accounts"):
            machine.accounts = AccountService.from_dict(state["accounts"])
        if state.get("terminal"):
            machine.terminal = PaymentTerminal.from_dict(state["terminal"])
        if state.get("log"):
            machine.log = EventLog.from_dict(state["log"])
        machine.transactions = [
            Transaction.from_dict(t) for t in state.get("transactions", [])
        ]
        pin = state.get("pin") or {}
        if pin.get("salt") and pin.get("hash"):
            machine._pin_salt = pin["salt"]
            machine._pin_hash = pin["hash"]
        weather = state.get("weather") or {}
        machine.weather = WeatherProvider(
            temperature_c=weather.get("temperature_c", 15.0),
            online=weather.get("online", True),
        )
        return machine

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_customisation(self) -> Customisation:
        """Return the customisation a new order should start from.

        Input:
            None.

        Returns:
            Customisation: The logged-in user's preferences, or machine
            defaults for a guest.
        """
        if self.current_user:
            return Customisation.from_dict(self.current_user.preferences.to_dict())
        return Customisation()

    def _require_user(self) -> User:
        """Return the logged-in user or fail.

        Input:
            None.

        Returns:
            User: The logged-in user.

        Raises:
            MachineError: When nobody is logged in.
        """
        if self.current_user is None:
            raise MachineError("You need to be logged in for that.")
        return self.current_user

    def _require_technician(self) -> None:
        """Fail unless administrative mode is unlocked.

        Input:
            None.

        Returns:
            None.

        Raises:
            MachineError: When not in technician mode.
        """
        if not self.technician_mode:
            raise MachineError("Administrative mode is locked.")

    def _require_serviceable(self) -> None:
        """Fail when an unresolved error-severity fault blocks service.

        Input:
            None.

        Returns:
            None.

        Raises:
            MachineError: When a blocking fault is active.
        """
        blocking = self.log.blocking()
        if blocking:
            raise MachineError(
                "Machine out of service: " + "; ".join(e.message for e in blocking)
            )

    def _validate_customisation(self, raw: dict) -> None:
        """Check a customisation dictionary against the allowed option values.

        Input:
            raw (dict): Candidate Customisation fields.

        Returns:
            None.

        Raises:
            ValueError: When any value is outside its allowed set.
        """
        from .models import CUP_SIZES, MILK_TYPES, STRENGTHS, TEMPERATURES

        if raw["milk"] not in MILK_TYPES:
            raise ValueError(f"milk must be one of {MILK_TYPES}")
        if raw["strength"] not in STRENGTHS:
            raise ValueError(f"strength must be one of {STRENGTHS}")
        if raw["size"] not in CUP_SIZES:
            raise ValueError(f"size must be one of {CUP_SIZES}")
        if raw["temperature"] not in TEMPERATURES:
            raise ValueError(f"temperature must be one of {TEMPERATURES}")
        if not isinstance(raw["syrup_shots"], int) or raw["syrup_shots"] < 0:
            raise ValueError("syrup_shots must be a non-negative integer")

    def _post_brew_checks(self) -> list[str]:
        """Raise ingredient and waste-bin faults after a drink is made.

        Input:
            None.

        Returns:
            list[str]: Warning messages for the customer-facing screen.
        """
        warnings: list[str] = []
        low = self.inventory.low_ingredients()
        if low:
            labels = ", ".join(i.label for i in low)
            self.log.raise_fault("LOW_INGREDIENT", labels)
            warnings.append(f"Low on: {labels}")
        if self.inventory.bins_full():
            self.log.raise_fault("BIN_FULL")
            warnings.append("Waste container full - service halted.")
        elif self.inventory.bins_warning():
            self.log.raise_fault("BIN_NEAR_FULL")
            warnings.append("Waste container nearly full.")
        return warnings


__all__ = [
    "Machine",
    "MachineError",
    "OrderDraft",
    "PurchaseOutcome",
    "AuthError",
    "PaymentDeclined",
    "OutOfStock",
    "BinsFull",
    "Weather",
]
