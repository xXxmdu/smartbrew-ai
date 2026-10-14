"""Recommendation scoring and menu reordering.

Implements Feature 6. A score is computed for every available drink from four
signals named in the system description - order history, stored preferences,
time of day and outdoor weather - plus the optional mood signal.

The weather provider is local and falls back to a neutral reading when offline,
so the recommender keeps working during a network outage (NFR-02, NFR-10).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Drink, User
from .mood import MoodReading

# Weight of each signal in the final score. Kept explicit so the ranking can be
# explained to the customer and tuned without touching the algorithm.
WEIGHTS = {
    "history": 3.0,
    "preference": 1.5,
    "time_of_day": 2.0,
    "weather": 1.5,
    "mood": 2.0,
}


@dataclass
class Weather:
    """A weather reading used as a recommendation signal.

    Attributes:
        temperature_c: Outdoor temperature in degrees Celsius.
        stale: True when this is a fallback reading taken while offline.
    """

    temperature_c: float
    stale: bool = False


class WeatherProvider:
    """Supplies the current outdoor temperature.

    A real machine would call a weather API. This provider returns a configured
    value and degrades to a neutral fallback when offline, which is what the
    offline requirement actually needs to be demonstrated.

    Attributes:
        temperature_c: The value returned while online.
        online: Whether the external service is reachable.
    """

    FALLBACK_TEMPERATURE = 15.0

    def __init__(self, temperature_c: float = 15.0, online: bool = True) -> None:
        """Create a weather provider.

        Input:
            temperature_c (float): Temperature to report while online.
            online (bool): Whether the external service is reachable.

        Returns:
            None.
        """
        self.temperature_c = temperature_c
        self.online = online

    def current(self) -> Weather:
        """Return the current weather reading.

        Input:
            None.

        Returns:
            Weather: The live reading, or a neutral fallback marked stale when
            the service is unreachable.
        """
        if not self.online:
            return Weather(self.FALLBACK_TEMPERATURE, stale=True)
        return Weather(self.temperature_c, stale=False)


@dataclass
class Scored:
    """One drink together with its recommendation score and reasons.

    Attributes:
        drink: The scored drink.
        score: Total score; higher ranks earlier on the menu.
        reasons: Short human-readable explanations of the score.
    """

    drink: Drink
    score: float
    reasons: list[str]


def score_drink(
    drink: Drink,
    user: User | None,
    hour: int,
    weather: Weather,
    mood: MoodReading | None = None,
) -> Scored:
    """Score a single drink against the current context.

    Input:
        drink (Drink): The drink to score.
        user (User | None): The logged-in user, or None for a guest.
        hour (int): Hour of day, 0-23.
        weather (Weather): Current weather reading.
        mood (MoodReading | None): Optional detected mood.

    Returns:
        Scored: The drink with its total score and the reasons behind it.
    """
    score = 0.0
    reasons: list[str] = []

    if user and user.history:
        occurrences = user.history.count(drink.key)
        if occurrences:
            share = occurrences / len(user.history)
            score += WEIGHTS["history"] * share
            reasons.append(f"you order this {share:.0%} of the time")

    if user and drink.recipe.get("whole_milk") and user.preferences.milk != "none":
        score += WEIGHTS["preference"] * 0.5
        reasons.append(f"matches your {user.preferences.milk} milk preference")

    # Before 10:00 a milky breakfast drink; after 15:00 something lighter on
    # caffeine so the customer still sleeps.
    if hour < 10 and drink.recipe.get("whole_milk"):
        score += WEIGHTS["time_of_day"]
        reasons.append("a morning drink")
    elif 10 <= hour < 15 and drink.caffeine_mg >= 80:
        score += WEIGHTS["time_of_day"] * 0.6
        reasons.append("an afternoon pick-me-up")
    elif hour >= 15 and drink.caffeine_mg < 80:
        score += WEIGHTS["time_of_day"] * 0.8
        reasons.append("low caffeine for the evening")

    if weather.temperature_c < 8 and drink.kcal >= 150:
        score += WEIGHTS["weather"]
        reasons.append(f"warming, it is {weather.temperature_c:.0f} degrees out")
    elif weather.temperature_c > 22 and drink.kcal < 100:
        score += WEIGHTS["weather"] * 0.8
        reasons.append("light for a warm day")
    if weather.stale:
        reasons.append("(weather unavailable, using a neutral estimate)")

    if mood:
        if mood.mood == "tired" and drink.caffeine_mg >= 120:
            score += WEIGHTS["mood"] * mood.confidence
            reasons.append("extra caffeine, you look tired")
        elif mood.mood == "stressed" and drink.caffeine_mg < 80:
            score += WEIGHTS["mood"] * mood.confidence
            reasons.append("something calming")
        elif mood.mood == "happy" and drink.kcal >= 200:
            score += WEIGHTS["mood"] * mood.confidence * 0.6
            reasons.append("a treat to match your mood")

    return Scored(drink=drink, score=round(score, 3), reasons=reasons)


def rank_menu(
    drinks: list[Drink],
    user: User | None,
    hour: int,
    weather: Weather,
    mood: MoodReading | None = None,
) -> list[Scored]:
    """Score and reorder a whole menu, highest first.

    Ties are broken by drink name so the ordering is stable and the demo is
    reproducible.

    Input:
        drinks (list[Drink]): Drinks to rank, usually the available ones.
        user (User | None): The logged-in user, or None for a guest.
        hour (int): Hour of day, 0-23.
        weather (Weather): Current weather reading.
        mood (MoodReading | None): Optional detected mood.

    Returns:
        list[Scored]: The menu sorted by descending score.
    """
    scored = [score_drink(d, user, hour, weather, mood) for d in drinks]
    scored.sort(key=lambda s: (-s.score, s.drink.name))
    return scored
