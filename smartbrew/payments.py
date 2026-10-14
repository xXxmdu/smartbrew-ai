"""Payment authorisation, offline queueing and deferred settlement.

Implements Feature 5. Covers FR-18 (four payment methods), FR-19 (a declined
payment leaves the drink unbrewed), NFR-02 (keep taking orders with no
network) and NFR-03 (queued transactions settle exactly once when the network
returns).

No card number is ever retained: the authoriser is given a card reference and
returns only a masked form of it, which is what reaches the transaction log
(NFR-06).
"""

from __future__ import annotations

from dataclasses import dataclass

METHODS = ("chip", "contactless", "wallet", "employee_card")


class PaymentDeclined(Exception):
    """Raised when a payment is not authorised."""


@dataclass
class PaymentResult:
    """Outcome of a single authorisation attempt.

    Attributes:
        approved: Whether the payment was authorised.
        method: The payment method used.
        reference: Masked reference safe to store, e.g. "contactless ****4242".
        offline: True when the payment was taken offline and still needs
            settling.
        detail: Human-readable explanation, used for declines.
    """

    approved: bool
    method: str
    reference: str
    offline: bool
    detail: str = ""


def mask(card_reference: str) -> str:
    """Reduce a card reference to its last four characters.

    Input:
        card_reference (str): Raw reference supplied by the reader.

    Returns:
        str: Masked form such as "****4242"; "****" when the reference is too
        short to mask meaningfully.
    """
    digits = "".join(ch for ch in card_reference if ch.isalnum())
    if len(digits) < 4:
        return "****"
    return "****" + digits[-4:]


class PaymentTerminal:
    """Simulated card terminal with an offline store-and-forward queue.

    The terminal declines any card reference ending in "0000", which gives the
    demonstration a deterministic way to exercise the decline path.

    Attributes:
        online: Whether the terminal can currently reach the acquirer.
        pending: Transaction ids taken offline and not yet settled.
        employee_balances: Prepaid employee card balances by card reference.
    """

    DECLINE_SUFFIX = "0000"
    OFFLINE_CEILING = 50.0

    def __init__(self, online: bool = True) -> None:
        """Create a payment terminal.

        Input:
            online (bool): Starting connectivity state.

        Returns:
            None.
        """
        self.online = online
        self.pending: list[str] = []
        self.employee_balances: dict[str, float] = {}

    def set_online(self, online: bool) -> None:
        """Change the terminal's connectivity state.

        Input:
            online (bool): True to simulate the network returning.

        Returns:
            None.
        """
        self.online = online

    def top_up_employee_card(self, card_reference: str, amount: float) -> float:
        """Add credit to a prepaid employee card.

        Input:
            card_reference (str): The card's reference.
            amount (float): Amount in SEK to add; must be positive.

        Returns:
            float: The new balance.

        Raises:
            ValueError: When the amount is not positive.
        """
        if amount <= 0:
            raise ValueError("Top-up amount must be positive.")
        self.employee_balances[card_reference] = round(
            self.employee_balances.get(card_reference, 0.0) + amount, 2
        )
        return self.employee_balances[card_reference]

    def authorise(
        self, amount: float, method: str, card_reference: str
    ) -> PaymentResult:
        """Attempt to authorise a payment.

        Input:
            amount (float): Amount in SEK. Zero is allowed, which happens when
                loyalty points cover the whole price.
            method (str): One of METHODS.
            card_reference (str): Raw card reference from the reader.

        Returns:
            PaymentResult: Always returned on success, including offline
            approvals.

        Raises:
            PaymentDeclined: When the method is unknown, the card is refused,
                the employee card has insufficient credit, or the amount is
                above the ceiling the terminal may approve offline.
        """
        if method not in METHODS:
            raise PaymentDeclined(f"Unsupported payment method '{method}'.")
        if amount < 0:
            raise PaymentDeclined("Amount cannot be negative.")

        masked = f"{method} {mask(card_reference)}"

        if amount == 0:
            return PaymentResult(True, method, masked, offline=False,
                                 detail="Covered by loyalty points.")

        if method == "employee_card":
            balance = self.employee_balances.get(card_reference, 0.0)
            if balance < amount:
                raise PaymentDeclined(
                    f"Employee card has {balance:.2f} SEK, needs {amount:.2f} SEK."
                )
            self.employee_balances[card_reference] = round(balance - amount, 2)
            # Prepaid cards are settled on the machine, so they never queue.
            return PaymentResult(True, method, masked, offline=False)

        if card_reference.endswith(self.DECLINE_SUFFIX):
            raise PaymentDeclined("Card declined by issuer.")

        if not self.online:
            if amount > self.OFFLINE_CEILING:
                raise PaymentDeclined(
                    f"Offline limit is {self.OFFLINE_CEILING:.2f} SEK; "
                    f"cannot approve {amount:.2f} SEK without a network."
                )
            return PaymentResult(True, method, masked, offline=True,
                                 detail="Stored for settlement when back online.")

        return PaymentResult(True, method, masked, offline=False)

    def queue(self, transaction_id: str) -> None:
        """Record a transaction as awaiting settlement.

        Input:
            transaction_id (str): Id of the offline transaction.

        Returns:
            None.
        """
        if transaction_id not in self.pending:
            self.pending.append(transaction_id)

    def settle_pending(self) -> list[str]:
        """Settle every queued transaction, once connectivity allows.

        Each id is removed from the queue as it settles, so calling this twice
        cannot charge a transaction twice (NFR-03).

        Input:
            None.

        Returns:
            list[str]: Ids settled by this call; empty while still offline.
        """
        if not self.online:
            return []
        settled = list(self.pending)
        self.pending.clear()
        return settled

    def to_dict(self) -> dict:
        """Convert the terminal state to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: Connectivity, pending queue and employee balances.
        """
        return {
            "online": self.online,
            "pending": list(self.pending),
            "employee_balances": dict(self.employee_balances),
        }

    @staticmethod
    def from_dict(raw: dict) -> "PaymentTerminal":
        """Rebuild a PaymentTerminal from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            PaymentTerminal: The reconstructed terminal.
        """
        term = PaymentTerminal(online=raw.get("online", True))
        term.pending = list(raw.get("pending", []))
        term.employee_balances = dict(raw.get("employee_balances", {}))
        return term
