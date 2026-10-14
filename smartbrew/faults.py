"""Fault detection and the diagnostic event log.

Implements the fault half of Feature 10 (FR-26). Faults are both shown on the
administrative dashboard and appended to a persistent log so a technician can
diagnose the machine before travelling to it.
"""

from __future__ import annotations

from .models import FaultEvent, now_iso

# Fault codes the machine knows how to raise, mapped to dashboard text.
KNOWN_FAULTS = {
    "GRINDER_JAM": ("Grinder Jammed", "error"),
    "HEATER_FAULT": ("Water Heater Fault", "error"),
    "LOW_INGREDIENT": ("Low Ingredient Threshold", "warning"),
    "BIN_NEAR_FULL": ("Waste container approaching capacity", "warning"),
    "BIN_FULL": ("Waste container full - service halted", "error"),
    "NETWORK_LOST": ("Network unreachable - offline mode", "warning"),
    "NETWORK_BACK": ("Network restored", "info"),
    "AUTH_FAILED": ("Failed administrative authentication", "warning"),
    "CAMERA_FAULT": ("Mood camera unavailable", "info"),
}


class EventLog:
    """An append-only log of machine events.

    Attributes:
        events: All events, oldest first.
    """

    def __init__(self, events: list[FaultEvent] | None = None) -> None:
        """Create an event log.

        Input:
            events (list[FaultEvent] | None): Existing events to load.

        Returns:
            None.
        """
        self.events: list[FaultEvent] = events or []

    def raise_fault(self, code: str, detail: str = "") -> FaultEvent:
        """Record a fault and return the event created.

        Input:
            code (str): A key of KNOWN_FAULTS, or any other string for an
                unclassified fault, which is logged at "error" severity.
            detail (str): Optional extra text appended to the message.

        Returns:
            FaultEvent: The event appended to the log.
        """
        message, severity = KNOWN_FAULTS.get(code, (code, "error"))
        if detail:
            message = f"{message}: {detail}"
        event = FaultEvent(
            timestamp=now_iso(), code=code, message=message, severity=severity
        )
        self.events.append(event)
        return event

    def active(self) -> list[FaultEvent]:
        """List faults that have not yet been cleared by a technician.

        Informational events are not treated as active faults.

        Input:
            None.

        Returns:
            list[FaultEvent]: Uncleared warnings and errors, oldest first.
        """
        return [
            e for e in self.events if not e.cleared and e.severity in ("warning", "error")
        ]

    def blocking(self) -> list[FaultEvent]:
        """List uncleared faults severe enough to stop the machine serving.

        Input:
            None.

        Returns:
            list[FaultEvent]: Uncleared events of severity "error".
        """
        return [e for e in self.events if not e.cleared and e.severity == "error"]

    def clear(self, code: str) -> int:
        """Mark every uncleared event with a given code as resolved.

        Input:
            code (str): The fault code to clear, e.g. "GRINDER_JAM".

        Returns:
            int: How many events were cleared.
        """
        count = 0
        for event in self.events:
            if event.code == code and not event.cleared:
                event.cleared = True
                count += 1
        return count

    def clear_all(self) -> int:
        """Mark every uncleared event as resolved.

        Input:
            None.

        Returns:
            int: How many events were cleared.
        """
        count = 0
        for event in self.events:
            if not event.cleared:
                event.cleared = True
                count += 1
        return count

    def tail(self, limit: int = 20) -> list[FaultEvent]:
        """Return the most recent events for the dashboard.

        Input:
            limit (int): Maximum number of events to return.

        Returns:
            list[FaultEvent]: Up to `limit` events, oldest first.
        """
        return self.events[-limit:]

    def to_dict(self) -> dict:
        """Convert the log to a JSON-serialisable dictionary.

        Input:
            None.

        Returns:
            dict: A single "events" key holding the serialised events.
        """
        return {"events": [e.to_dict() for e in self.events]}

    @staticmethod
    def from_dict(raw: dict) -> "EventLog":
        """Rebuild an EventLog from its dictionary form.

        Input:
            raw (dict): Dictionary previously produced by to_dict().

        Returns:
            EventLog: The reconstructed log.
        """
        return EventLog([FaultEvent.from_dict(e) for e in raw.get("events", [])])
