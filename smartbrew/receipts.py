"""Receipt rendering as an on-screen code or as an e-mail.

Implements the receipt half of Feature 9 (FR-20). No payment credential
appears on a receipt beyond the masked reference already stored on the
transaction (NFR-06).

On the QR path, a real QR symbol is rendered when the optional third-party
`qrcode` package is installed. The prototype does not require it: without it,
the same payload is shown as text alongside a clearly labelled placeholder, so
the feature is demonstrable on a clean machine with no installation step. See
"Known simplifications" in README.md.
"""

from __future__ import annotations

from .models import Transaction

RECEIPT_BASE_URL = "https://receipts.smartbrew.example/r"


def receipt_payload(transaction: Transaction) -> str:
    """Build the verification URL encoded on a receipt.

    Input:
        transaction (Transaction): The completed purchase.

    Returns:
        str: A URL carrying the transaction id.
    """
    return f"{RECEIPT_BASE_URL}/{transaction.transaction_id}"


def receipt_text(transaction: Transaction, drink_name: str) -> str:
    """Render the human-readable body of a receipt.

    Input:
        transaction (Transaction): The completed purchase.
        drink_name (str): Display name of the drink bought.

    Returns:
        str: Multi-line receipt text.
    """
    lines = [
        "SmartBrew AI - receipt",
        f"Receipt no : {transaction.transaction_id}",
        f"Date       : {transaction.timestamp}",
        f"Customer   : {transaction.user_id}",
        f"Drink      : {drink_name} ({transaction.customisation.describe()})",
        f"Price      : {transaction.gross_amount:.2f} SEK",
    ]
    if transaction.discount:
        lines.append(
            f"Loyalty    : -{transaction.discount:.2f} SEK "
            f"({transaction.points_redeemed} points)"
        )
    lines.extend(
        [
            f"Charged    : {transaction.net_amount:.2f} SEK",
            f"Paid by    : {transaction.payment_reference}",
            f"Points     : +{transaction.points_earned}",
        ]
    )
    if not transaction.settled:
        lines.append("Status     : taken offline, settles when back online")
    return "\n".join(lines)


def render_qr(payload: str) -> str:
    """Render a payload as a QR symbol for display on the touchscreen.

    Input:
        payload (str): The text to encode, normally from receipt_payload().

    Returns:
        str: An ASCII QR symbol when the optional `qrcode` package is
        installed; otherwise a labelled placeholder box followed by the payload
        in clear text, so the receipt is still usable.
    """
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        rows = []
        matrix = qr.get_matrix()
        for row in matrix:
            rows.append("".join("##" if cell else "  " for cell in row))
        return "\n".join(rows)
    except ImportError:
        box_width = max(len(payload) + 2, 34)
        border = "+" + "-" * box_width + "+"
        return "\n".join(
            [
                border,
                "|" + "[ QR PLACEHOLDER ]".center(box_width) + "|",
                "|" + "install 'qrcode' for a real symbol".center(box_width) + "|",
                "|" + " " * box_width + "|",
                "|" + payload.center(box_width) + "|",
                border,
            ]
        )


def deliver_qr(transaction: Transaction, drink_name: str) -> str:
    """Produce the on-screen receipt a customer scans at the machine.

    Input:
        transaction (Transaction): The completed purchase.
        drink_name (str): Display name of the drink bought.

    Returns:
        str: Receipt text followed by the QR symbol.
    """
    return (
        receipt_text(transaction, drink_name)
        + "\n\n"
        + render_qr(receipt_payload(transaction))
    )


def deliver_email(transaction: Transaction, drink_name: str, address: str) -> str:
    """Produce the e-mail a customer receives instead of an on-screen code.

    The prototype does not send mail; it renders the message that would be
    sent, which is what the demonstration needs to show.

    Input:
        transaction (Transaction): The completed purchase.
        drink_name (str): Display name of the drink bought.
        address (str): Destination e-mail address.

    Returns:
        str: The rendered message, including headers.

    Raises:
        ValueError: When the address is empty or obviously not an address.
    """
    if not address or "@" not in address:
        raise ValueError(f"'{address}' is not a usable e-mail address.")
    return "\n".join(
        [
            f"To: {address}",
            "From: receipts@smartbrew.example",
            f"Subject: Your SmartBrew receipt {transaction.transaction_id}",
            "",
            receipt_text(transaction, drink_name),
            "",
            f"View online: {receipt_payload(transaction)}",
        ]
    )
