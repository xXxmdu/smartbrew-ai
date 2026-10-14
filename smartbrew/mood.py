"""Mood detection from a camera frame, with a hard in-memory guarantee.

Implements the mood half of Feature 6 and the privacy constraint NFR-01: the
frame is analysed in memory and discarded immediately. It is never written to
disk and never leaves the device.

The classifier itself is simulated. A real machine would run a small vision
model on the embedded compute module; what matters for this prototype is the
data-handling contract around it, which is enforced and tested here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import MOODS


@dataclass
class MoodReading:
    """The result of one mood inference.

    Deliberately contains no image data, so that nothing downstream can
    accidentally persist a frame.

    Attributes:
        mood: One of models.MOODS.
        confidence: Value between 0.0 and 1.0.
    """

    mood: str
    confidence: float


class CameraUnavailable(Exception):
    """Raised when no frame can be captured from the camera."""


class MoodSensor:
    """Captures a frame, classifies it, and discards it.

    The sensor holds no state between readings beyond a counter, which exists
    only so the demonstration can show that frames are not accumulating.

    Attributes:
        frames_processed: How many frames have been analysed this session.
        enabled: Whether the camera subsystem is operational.
    """

    def __init__(self, enabled: bool = True) -> None:
        """Create a mood sensor.

        Input:
            enabled (bool): False simulates a failed or disconnected camera.

        Returns:
            None.
        """
        self.frames_processed = 0
        self.enabled = enabled

    def analyse(self, frame: bytes | None) -> MoodReading:
        """Classify a single camera frame and discard it.

        The local variable holding the frame is cleared before returning, and
        no part of the frame is copied into the result.

        Input:
            frame (bytes | None): Raw frame bytes. None means the camera
                returned nothing.

        Returns:
            MoodReading: The detected mood and confidence.

        Raises:
            CameraUnavailable: When the camera is disabled or returned no
                frame. Callers are expected to continue without mood input
                rather than fail the order (NFR-10).
        """
        if not self.enabled:
            raise CameraUnavailable("Camera subsystem is disabled.")
        if not frame:
            raise CameraUnavailable("No frame captured.")

        # Simulated inference: a deterministic function of the frame contents so
        # that tests and demonstrations are reproducible.
        checksum = sum(frame) % len(MOODS)
        confidence = 0.55 + (sum(frame) % 40) / 100.0
        reading = MoodReading(mood=MOODS[checksum], confidence=round(confidence, 2))

        # Explicitly drop the frame. Nothing below this line can reach it.
        frame = None
        del frame
        self.frames_processed += 1
        return reading

    @staticmethod
    def simulate_frame(mood: str) -> bytes:
        """Produce a synthetic frame that will classify as a given mood.

        Used by the demonstration and the tests in place of a real camera.

        Input:
            mood (str): One of models.MOODS.

        Returns:
            bytes: A frame whose checksum maps to the requested mood.

        Raises:
            ValueError: When the mood is not recognised.
        """
        if mood not in MOODS:
            raise ValueError(f"Unknown mood '{mood}'. Expected one of {MOODS}.")
        target = MOODS.index(mood)
        # Find the smallest byte sequence whose sum maps onto the target index.
        value = target
        while value % len(MOODS) != target:
            value += 1
        return bytes([value])
