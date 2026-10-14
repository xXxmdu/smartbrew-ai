"""Loyalty points: earning and redemption.

Implements Feature 7, the feature of our own design introduced in Lab 1 and
carried through Lab 2 (REQ-08, REQ-09) and Lab 3 (FR-28, FR-29).

Rules:
  * One point is earned per whole SEK of the amount actually charged. Points
    are not earned on the part of a purchase paid for with points, so points
    cannot regenerate themselves.
  * Points may be redeemed once the balance reaches REDEEM_THRESHOLD, in whole
    blocks only, and never for more than the amount due.
"""

from __future__ import annotations

from dataclasses import dataclass

POINTS_PER_SEK = 1
REDEEM_THRESHOLD = 100
POINTS_PER_BLOCK = 100
BLOCK_VALUE_SEK = 10.0


class LoyaltyError(Exception):
    """Raised when a redemption is not permitted."""


@dataclass
class Redemption:
    """The result of applying loyalty points to an order.

    Attributes:
        points_used: Points consumed.
        discount: Amount in SEK removed from the price.
        remaining_balance: The user's balance after redemption.
    """

    points_used: int
    discount: float
    remaining_balance: int


def points_for(amount_charged: float) -> int:
    """Calculate the points earned by a purchase.

    Input:
        amount_charged (float): The amount actually paid in SEK, after any
            loyalty discount.

    Returns:
        int: Points earned, never negative.
    """
    return max(0, int(amount_charged) * POINTS_PER_SEK)


def max_redeemable(balance: int, amount_due: float) -> int:
    """Calculate the largest number of points usable on this order.

    Input:
        balance (int): The user's current point balance.
        amount_due (float): The price before discount, in SEK.

    Returns:
        int: Points that may be redeemed, always a multiple of
        POINTS_PER_BLOCK, and 0 when the balance is below the threshold.
    """
    if balance < REDEEM_THRESHOLD or amount_due <= 0:
        return 0
    blocks_affordable = int(balance // POINTS_PER_BLOCK)
    blocks_useful = int(amount_due // BLOCK_VALUE_SEK)
    if amount_due % BLOCK_VALUE_SEK:
        # A partial block may still be used; it is simply worth less than its
        # face value on this order, which we allow but do not force.
        blocks_useful += 1
    return min(blocks_affordable, blocks_useful) * POINTS_PER_BLOCK


def redeem(balance: int, amount_due: float, points: int) -> Redemption:
    """Apply loyalty points to an order.

    Input:
        balance (int): The user's current point balance.
        amount_due (float): The price before discount, in SEK.
        points (int): Points the customer wishes to redeem.

    Returns:
        Redemption: Points used, discount granted and the new balance.

    Raises:
        LoyaltyError: When the balance is below the threshold, the request is
            not a whole number of blocks, or it exceeds the balance.
    """
    if points == 0:
        return Redemption(0, 0.0, balance)
    if balance < REDEEM_THRESHOLD:
        raise LoyaltyError(
            f"At least {REDEEM_THRESHOLD} points are needed to redeem; "
            f"balance is {balance}."
        )
    if points % POINTS_PER_BLOCK:
        raise LoyaltyError(
            f"Points must be redeemed in blocks of {POINTS_PER_BLOCK}."
        )
    if points > balance:
        raise LoyaltyError(f"Cannot redeem {points} points; balance is {balance}.")

    blocks = points // POINTS_PER_BLOCK
    discount = min(blocks * BLOCK_VALUE_SEK, amount_due)
    return Redemption(
        points_used=points,
        discount=round(discount, 2),
        remaining_balance=balance - points,
    )
