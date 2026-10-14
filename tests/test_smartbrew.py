"""Test suite for SmartBrew AI.

Run with:  python -m unittest discover -s tests -v

The tests are grouped by the ten features so a failure points directly at the
feature it belongs to. They are written against the Machine facade wherever
possible, because that is the surface the CLI and the demonstration use.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smartbrew import loyalty, storage
from smartbrew.accounts import AuthError
from smartbrew.inventory import BIN_CAPACITY, BinsFull, OutOfStock
from smartbrew.machine import Machine, MachineError
from smartbrew.models import Customisation
from smartbrew.mood import CameraUnavailable, MoodSensor
from smartbrew.payments import PaymentDeclined
from smartbrew.pricing import price_of, recipe_for

GOOD_CARD = "5412751234564242"
BAD_CARD = "5412751234560000"
STAFF_CARD = "EMP-00731"
NFC_CARD = "NFC-AB12-9931"


def machine_with_user() -> Machine:
    """Build a machine with one registered, logged-in customer.

    Input:
        None.

    Returns:
        Machine: Machine with user "ahmed" logged in and a funded staff card.
    """
    m = Machine()
    m.register("ahmed", "Ahmed", "ahmed@example.com", "coffee123",
               nfc_token=NFC_CARD)
    m.terminal.top_up_employee_card(STAFF_CARD, 500.0)
    return m


class TestFeature1Accounts(unittest.TestCase):
    """Feature 1 - accounts, login and preference profiles."""

    def test_password_is_not_stored_in_clear(self) -> None:
        """The clear-text password must not appear on the user record.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        blob = json.dumps(m.accounts.to_dict())
        self.assertNotIn("coffee123", blob)

    def test_login_with_password(self) -> None:
        """A correct password authenticates the user.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.logout()
        self.assertEqual(m.login("ahmed", "coffee123").user_id, "ahmed")

    def test_login_with_wrong_password_fails(self) -> None:
        """An incorrect password is rejected.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.logout()
        with self.assertRaises(AuthError):
            m.login("ahmed", "nope")

    def test_unknown_user_and_wrong_password_look_identical(self) -> None:
        """The failure message must not reveal whether the user id exists.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.logout()
        with self.assertRaises(AuthError) as a:
            m.login("ahmed", "nope")
        with self.assertRaises(AuthError) as b:
            m.login("nobody", "nope")
        self.assertEqual(str(a.exception), str(b.exception))

    def test_login_with_nfc(self) -> None:
        """A linked NFC card authenticates the user.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.logout()
        self.assertEqual(m.login_nfc(NFC_CARD).user_id, "ahmed")

    def test_unknown_nfc_card_fails(self) -> None:
        """An unlinked card is rejected.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.logout()
        with self.assertRaises(AuthError):
            m.login_nfc("NFC-UNKNOWN")

    def test_duplicate_user_id_rejected(self) -> None:
        """Two accounts cannot share a user id.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        with self.assertRaises(AuthError):
            m.register("ahmed", "Other", "o@example.com", "password1")

    def test_short_password_rejected(self) -> None:
        """Passwords shorter than six characters are rejected.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        with self.assertRaises(AuthError):
            m.register("x", "X", "x@example.com", "abc")

    def test_preferences_applied_to_new_order(self) -> None:
        """A new order starts from the user's stored defaults.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_preferences(milk="oat", strength=3, size="large")
        draft = m.start_order("latte")
        self.assertEqual(draft.customisation.milk, "oat")
        self.assertEqual(draft.customisation.strength, 3)
        self.assertEqual(draft.customisation.size, "large")

    def test_guest_gets_machine_defaults(self) -> None:
        """With nobody logged in, an order starts from machine defaults.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        draft = m.start_order("latte")
        self.assertEqual(draft.customisation.milk, "whole")


class TestFeature2Menu(unittest.TestCase):
    """Feature 2 - menu browsing."""

    def test_menu_lists_every_drink(self) -> None:
        """Every catalogue drink appears on the menu.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        self.assertEqual(len(m.menu()), len(m.drinks))

    def test_menu_carries_nutrition_and_allergens(self) -> None:
        """Milk drinks declare the milk allergen and a calorie figure.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        latte = m.drinks["latte"]
        self.assertIn("milk", latte.allergens)
        self.assertGreater(latte.kcal, 0)

    def test_all_drinks_available_on_a_full_machine(self) -> None:
        """A machine with full hoppers can make everything.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        self.assertEqual(len(m.available_drinks()), len(m.drinks))


class TestFeature3Customisation(unittest.TestCase):
    """Feature 3 - customisation and live pricing."""

    def test_price_rises_with_each_upgrade(self) -> None:
        """Each upgrade increases the price.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        base = draft.price()
        oat = m.customise(draft, milk="oat")
        strong = m.customise(draft, strength=4)
        large = m.customise(draft, size="large")
        self.assertLess(base, oat)
        self.assertLess(oat, strong)
        self.assertLess(strong, large)

    def test_small_cup_is_cheaper(self) -> None:
        """A small cup costs less than a medium one.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        latte = m.drinks["latte"]
        self.assertLess(
            price_of(latte, Customisation(size="small")),
            price_of(latte, Customisation(size="medium")),
        )

    def test_breakdown_total_matches_price(self) -> None:
        """The itemised breakdown ends with the same number as the price.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("mocha")
        m.customise(draft, milk="soy", strength=3, syrup_shots=2)
        label, total = draft.breakdown()[-1]
        self.assertEqual(label, "Total")
        self.assertAlmostEqual(total, draft.price(), places=2)

    def test_invalid_option_value_rejected(self) -> None:
        """An out-of-range option value is refused.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        with self.assertRaises(ValueError):
            m.customise(draft, strength=99)

    def test_unknown_option_rejected(self) -> None:
        """An option that does not exist is refused.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        with self.assertRaises(TypeError):
            m.customise(draft, sprinkles=True)

    def test_milk_choice_redirects_ingredient(self) -> None:
        """Choosing oat milk consumes oat milk and no whole milk.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        used = recipe_for(m.drinks["latte"], Customisation(milk="oat"))
        self.assertIn("oat_milk", used)
        self.assertNotIn("whole_milk", used)

    def test_no_milk_consumes_no_milk(self) -> None:
        """Choosing no milk removes milk from the recipe entirely.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        used = recipe_for(m.drinks["latte"], Customisation(milk="none"))
        self.assertFalse([k for k in used if k.endswith("milk")])


class TestFeature4Inventory(unittest.TestCase):
    """Feature 4 - stock, depletion and availability."""

    def test_brewing_decrements_stock(self) -> None:
        """Brewing a drink reduces the ingredients it uses.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        before = m.inventory.ingredients["beans"].level
        draft = m.start_order("espresso")
        m.place_order(draft, "contactless", GOOD_CARD)
        self.assertLess(m.inventory.ingredients["beans"].level, before)

    def test_depleted_ingredient_makes_drink_unavailable(self) -> None:
        """A drink whose ingredient is at threshold is not available.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        m.inventory.ingredients["whole_milk"].level = 150.0
        self.assertNotIn("latte", [d.key for d in m.available_drinks()])

    def test_ordering_a_depleted_drink_raises(self) -> None:
        """Ordering past the threshold is refused.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.ingredients["whole_milk"].level = 150.0
        draft = m.start_order("latte")
        with self.assertRaises(OutOfStock):
            m.place_order(draft, "contactless", GOOD_CARD)

    def test_other_drinks_remain_available(self) -> None:
        """Depleting one ingredient does not block unrelated drinks.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        m.inventory.ingredients["whole_milk"].level = 150.0
        self.assertIn("espresso", [d.key for d in m.available_drinks()])

    def test_refill_restores_capacity(self) -> None:
        """A refill resets the ingredient to its full capacity.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.ingredients["oat_milk"].level = 10.0
        m.technician_login("4242")
        ing = m.refill("oat_milk")
        self.assertEqual(ing.level, ing.capacity)
        self.assertFalse(ing.depleted)


class TestFeature5Payments(unittest.TestCase):
    """Feature 5 - payment, declines and offline settlement."""

    def test_all_four_methods_are_accepted(self) -> None:
        """Each payment method named in the requirements works.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        for method, card in (("chip", GOOD_CARD), ("contactless", GOOD_CARD),
                             ("wallet", GOOD_CARD), ("employee_card", STAFF_CARD)):
            with self.subTest(method=method):
                m = machine_with_user()
                draft = m.start_order("espresso")
                out = m.place_order(draft, method, card)
                self.assertTrue(out.payment.approved)

    def test_declined_card_leaves_drink_unbrewed(self) -> None:
        """FR-19: a declined payment must not consume ingredients.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        before = m.inventory.ingredients["beans"].level
        draft = m.start_order("latte")
        with self.assertRaises(PaymentDeclined):
            m.place_order(draft, "contactless", BAD_CARD)
        self.assertEqual(m.inventory.ingredients["beans"].level, before)
        self.assertEqual(m.transaction_log(), [])

    def test_employee_card_balance_is_checked(self) -> None:
        """A prepaid card without enough credit is declined.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.terminal.employee_balances[STAFF_CARD] = 1.0
        draft = m.start_order("latte")
        with self.assertRaises(PaymentDeclined):
            m.place_order(draft, "employee_card", STAFF_CARD)

    def test_employee_card_balance_is_debited(self) -> None:
        """A prepaid card payment reduces the stored balance.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        before = m.terminal.employee_balances[STAFF_CARD]
        draft = m.start_order("espresso")
        out = m.place_order(draft, "employee_card", STAFF_CARD)
        self.assertAlmostEqual(
            m.terminal.employee_balances[STAFF_CARD],
            before - out.transaction.net_amount,
            places=2,
        )

    def test_offline_order_is_served_and_queued(self) -> None:
        """NFR-02: an outage must not stop service.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_network(False)
        draft = m.start_order("espresso")
        out = m.place_order(draft, "contactless", GOOD_CARD)
        self.assertTrue(out.payment.approved)
        self.assertTrue(out.payment.offline)
        self.assertFalse(out.transaction.settled)
        self.assertIn(out.transaction.transaction_id, m.terminal.pending)

    def test_reconnecting_settles_exactly_once(self) -> None:
        """NFR-03: queued transactions settle, and only once.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_network(False)
        draft = m.start_order("espresso")
        out = m.place_order(draft, "contactless", GOOD_CARD)
        settled = m.set_network(True)
        self.assertEqual(settled, [out.transaction.transaction_id])
        self.assertTrue(m.transaction_log()[-1].settled)
        self.assertEqual(m.terminal.settle_pending(), [])

    def test_offline_ceiling_is_enforced(self) -> None:
        """A large offline amount is declined rather than risked.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_network(False)
        draft = m.start_order("mocha")
        m.customise(draft, size="large", strength=5, syrup_shots=5)
        self.assertGreater(draft.price(), m.terminal.OFFLINE_CEILING)
        with self.assertRaises(PaymentDeclined):
            m.place_order(draft, "contactless", GOOD_CARD)

    def test_card_number_never_reaches_the_log(self) -> None:
        """NFR-06: no full card reference is stored.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("espresso")
        m.place_order(draft, "contactless", GOOD_CARD)
        blob = json.dumps([t.to_dict() for t in m.transaction_log()])
        self.assertNotIn(GOOD_CARD, blob)
        self.assertIn("****4242", blob)


class TestFeature6Recommendations(unittest.TestCase):
    """Feature 6 - recommendations and mood."""

    def test_history_lifts_a_drink(self) -> None:
        """A frequently ordered drink scores higher than an unknown one.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.current_user.history.extend(["latte"] * 5)
        ranked = {s.drink.key: s.score for s in m.recommendations(hour=8)}
        self.assertGreater(ranked["latte"], ranked["americano"])

    def test_cold_weather_lifts_a_warming_drink(self) -> None:
        """Below 8 degrees, a high-calorie drink gains weather points.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.weather.temperature_c = 1.0
        cold = {s.drink.key: s.score for s in m.recommendations(hour=8)}
        m.weather.temperature_c = 25.0
        warm = {s.drink.key: s.score for s in m.recommendations(hour=8)}
        self.assertGreater(cold["hot_chocolate"], warm["hot_chocolate"])

    def test_tired_mood_lifts_a_high_caffeine_drink(self) -> None:
        """A tired reading raises the score of the strongest drink.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        reading = m.read_mood(MoodSensor.simulate_frame("tired"))
        without = {s.drink.key: s.score for s in m.recommendations(hour=16)}
        with_mood = {s.drink.key: s.score
                     for s in m.recommendations(mood=reading, hour=16)}
        self.assertGreater(with_mood["flat_white"], without["flat_white"])

    def test_ranking_is_sorted_and_complete(self) -> None:
        """Every available drink is ranked, in descending score order.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        ranked = m.recommendations(hour=9)
        self.assertEqual(len(ranked), len(m.available_drinks()))
        self.assertEqual([s.score for s in ranked],
                         sorted([s.score for s in ranked], reverse=True))

    def test_mood_reading_carries_no_image_data(self) -> None:
        """NFR-01: the reading exposes only a label and a confidence.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        sensor = MoodSensor()
        reading = sensor.analyse(MoodSensor.simulate_frame("happy"))
        self.assertEqual(set(vars(reading)), {"mood", "confidence"})

    def test_mood_inference_writes_nothing_to_disk(self) -> None:
        """NFR-01: analysing a frame must not create any file.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with tempfile.TemporaryDirectory() as tmp:
            before = set(Path(tmp).rglob("*"))
            sensor = MoodSensor()
            for mood in ("tired", "happy", "stressed", "neutral"):
                sensor.analyse(MoodSensor.simulate_frame(mood))
            self.assertEqual(set(Path(tmp).rglob("*")), before)

    def test_camera_failure_does_not_break_ordering(self) -> None:
        """NFR-10: a dead camera degrades gracefully.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.mood_sensor.enabled = False
        self.assertIsNone(m.read_mood(b"x"))
        self.assertTrue(m.recommendations(hour=9))

    def test_sensor_raises_when_disabled(self) -> None:
        """The sensor itself signals the failure to its caller.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with self.assertRaises(CameraUnavailable):
            MoodSensor(enabled=False).analyse(b"x")

    def test_weather_falls_back_when_offline(self) -> None:
        """An unreachable weather service yields a stale neutral reading.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_network(False)
        reading = m.weather.current()
        self.assertTrue(reading.stale)
        self.assertTrue(m.recommendations(hour=9))


class TestFeature7Loyalty(unittest.TestCase):
    """Feature 7 - loyalty points (our own feature)."""

    def test_points_are_earned_on_the_charged_amount(self) -> None:
        """One point per whole SEK actually charged.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("mocha")
        out = m.place_order(draft, "contactless", GOOD_CARD)
        self.assertEqual(out.transaction.points_earned,
                         int(out.transaction.net_amount))
        self.assertEqual(m.current_user.loyalty_points,
                         out.transaction.points_earned)

    def test_redeeming_below_threshold_is_refused(self) -> None:
        """Fewer than 100 points cannot be redeemed.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with self.assertRaises(loyalty.LoyaltyError):
            loyalty.redeem(50, 30.0, 100)

    def test_part_blocks_are_refused(self) -> None:
        """Points redeem in whole blocks only.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with self.assertRaises(loyalty.LoyaltyError):
            loyalty.redeem(500, 50.0, 150)

    def test_redeeming_more_than_balance_is_refused(self) -> None:
        """A redemption cannot exceed the balance.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with self.assertRaises(loyalty.LoyaltyError):
            loyalty.redeem(200, 90.0, 300)

    def test_discount_never_exceeds_the_price(self) -> None:
        """Redeeming more value than the drink costs does not pay the customer.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        r = loyalty.redeem(1000, 12.0, 1000)
        self.assertLessEqual(r.discount, 12.0)

    def test_points_do_not_self_fund(self) -> None:
        """Points are not earned on the part paid for with points.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.current_user.loyalty_points = 300
        draft = m.start_order("mocha")
        gross = draft.price()
        out = m.place_order(draft, "contactless", GOOD_CARD, redeem_points=200)
        self.assertLess(out.transaction.points_earned, int(gross))

    def test_full_cycle_balance_is_consistent(self) -> None:
        """Balance after redemption equals balance - used + earned.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.current_user.loyalty_points = 250
        draft = m.start_order("mocha")
        out = m.place_order(draft, "contactless", GOOD_CARD, redeem_points=200)
        self.assertEqual(
            m.current_user.loyalty_points,
            250 - out.transaction.points_redeemed + out.transaction.points_earned,
        )

    def test_guest_cannot_redeem(self) -> None:
        """Loyalty points require an account.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        draft = m.start_order("espresso")
        with self.assertRaises(MachineError):
            m.place_order(draft, "contactless", GOOD_CARD, redeem_points=100)


class TestFeature8SavedRecipes(unittest.TestCase):
    """Feature 8 - saved recipes and one-touch reorder."""

    def test_save_and_reorder(self) -> None:
        """A saved recipe rebuilds the exact configuration.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        m.customise(draft, milk="oat", strength=4, size="large", syrup_shots=1)
        m.save_current_as(draft, "Morning Oat")
        m.logout()
        m.login("ahmed", "coffee123")
        rebuilt = m.order_saved("Morning Oat")
        self.assertEqual(rebuilt.drink.key, "latte")
        self.assertEqual(rebuilt.customisation.milk, "oat")
        self.assertEqual(rebuilt.customisation.strength, 4)
        self.assertEqual(rebuilt.customisation.syrup_shots, 1)

    def test_saving_again_overwrites(self) -> None:
        """Saving under an existing name modifies that recipe.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        m.customise(draft, milk="oat")
        m.save_current_as(draft, "Usual")
        m.customise(draft, milk="soy")
        m.save_current_as(draft, "Usual")
        self.assertEqual(len(m.current_user.saved_recipes), 1)
        self.assertEqual(m.order_saved("Usual").customisation.milk, "soy")

    def test_blank_name_rejected(self) -> None:
        """A recipe needs a name.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        with self.assertRaises(ValueError):
            m.save_current_as(draft, "   ")

    def test_delete_recipe(self) -> None:
        """A deleted recipe can no longer be ordered.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        m.save_current_as(draft, "Usual")
        self.assertTrue(m.accounts.delete_recipe(m.current_user, "Usual"))
        with self.assertRaises(MachineError):
            m.order_saved("Usual")

    def test_guest_cannot_save(self) -> None:
        """Saving a recipe requires an account.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        draft = m.start_order("latte")
        with self.assertRaises(MachineError):
            m.save_current_as(draft, "Usual")


class TestFeature9Receipts(unittest.TestCase):
    """Feature 9 - receipts and the transaction log."""

    def test_qr_receipt_contains_the_transaction_id(self) -> None:
        """The on-screen receipt carries the transaction reference.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("espresso")
        out = m.place_order(draft, "contactless", GOOD_CARD, receipt="qr")
        self.assertIn(out.transaction.transaction_id, out.receipt)

    def test_email_receipt_is_addressed_to_the_user(self) -> None:
        """The e-mail receipt goes to the account's address.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("espresso")
        out = m.place_order(draft, "contactless", GOOD_CARD, receipt="email")
        self.assertIn("To: ahmed@example.com", out.receipt)

    def test_email_receipt_requires_an_account(self) -> None:
        """A guest cannot be sent an e-mail receipt.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = Machine()
        draft = m.start_order("espresso")
        with self.assertRaises(MachineError):
            m.place_order(draft, "contactless", GOOD_CARD, receipt="email")

    def test_invalid_receipt_choice_rejected(self) -> None:
        """Only the two documented receipt types are accepted.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("espresso")
        with self.assertRaises(MachineError):
            m.place_order(draft, "contactless", GOOD_CARD, receipt="fax")

    def test_transaction_records_every_parameter(self) -> None:
        """FR-21: the log holds the full configuration and payment method.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        draft = m.start_order("latte")
        m.customise(draft, milk="soy", strength=3, size="large", syrup_shots=2)
        out = m.place_order(draft, "wallet", GOOD_CARD)
        tx = out.transaction
        self.assertEqual(tx.customisation.milk, "soy")
        self.assertEqual(tx.customisation.strength, 3)
        self.assertEqual(tx.customisation.size, "large")
        self.assertEqual(tx.customisation.syrup_shots, 2)
        self.assertEqual(tx.payment_method, "wallet")
        self.assertEqual(tx.drink_key, "latte")

    def test_log_grows_with_each_purchase(self) -> None:
        """Every completed purchase is recorded.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        for _ in range(3):
            m.place_order(m.start_order("espresso"), "contactless", GOOD_CARD)
        self.assertEqual(len(m.transaction_log()), 3)


class TestFeature10Technician(unittest.TestCase):
    """Feature 10 - technician mode, waste bins, faults and the event log."""

    def test_admin_locked_by_default(self) -> None:
        """Administrative actions need technician mode.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        with self.assertRaises(MachineError):
            m.refill("oat_milk")
        with self.assertRaises(MachineError):
            m.dashboard()

    def test_wrong_pin_is_refused_and_logged(self) -> None:
        """NFR-05: a failed attempt is recorded.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        self.assertFalse(m.technician_login("0000"))
        self.assertFalse(m.technician_mode)
        self.assertIn("AUTH_FAILED", [e.code for e in m.log.events])

    def test_correct_pin_unlocks(self) -> None:
        """The correct PIN grants administrative mode.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        self.assertTrue(m.technician_login("4242"))
        self.assertTrue(m.technician_mode)

    def test_pin_is_not_stored_in_clear(self) -> None:
        """The technician PIN is stored only as a hash.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        self.assertNotIn("4242", json.dumps(m.snapshot()["pin"]))

    def test_bins_fill_and_halt_service(self) -> None:
        """FR-25: a full waste container stops brewing.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.grounds_bin = BIN_CAPACITY
        with self.assertRaises(BinsFull):
            m.inventory.consume(m.drinks["espresso"], Customisation())

    def test_full_bin_blocks_new_orders(self) -> None:
        """Once the full-bin fault is raised, ordering is refused.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.grounds_bin = BIN_CAPACITY - 1
        m.place_order(m.start_order("espresso"), "contactless", GOOD_CARD)
        with self.assertRaises(MachineError):
            m.start_order("espresso")

    def test_emptying_bins_restores_service(self) -> None:
        """A technician emptying the bin clears the fault.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.grounds_bin = BIN_CAPACITY - 1
        m.place_order(m.start_order("espresso"), "contactless", GOOD_CARD)
        m.technician_login("4242")
        m.empty_bins()
        m.technician_logout()
        self.assertTrue(m.start_order("espresso"))

    def test_bin_warning_before_full(self) -> None:
        """FR-24: the technician is warned as the bin approaches capacity.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.grounds_bin = int(BIN_CAPACITY * 0.9) - 1
        out = m.place_order(m.start_order("espresso"), "contactless", GOOD_CARD)
        self.assertTrue(any("nearly full" in w for w in out.warnings))

    def test_fault_blocks_service_until_cleared(self) -> None:
        """An error-severity fault takes the machine out of service.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.report_fault("GRINDER_JAM")
        with self.assertRaises(MachineError):
            m.start_order("latte")
        m.technician_login("4242")
        m.clear_fault("GRINDER_JAM")
        m.technician_logout()
        self.assertTrue(m.start_order("latte"))

    def test_low_ingredient_fault_is_logged(self) -> None:
        """Dropping onto the threshold raises a logged warning.

        A mocha uses 20 g of cocoa and the minimum is 40 g, so starting at
        60 g is the last order the machine will accept: it completes and
        leaves the ingredient exactly at its threshold.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.inventory.ingredients["cocoa"].level = 60.0
        out = m.place_order(m.start_order("mocha"), "contactless", GOOD_CARD)
        self.assertTrue(m.inventory.ingredients["cocoa"].depleted)
        self.assertIn("LOW_INGREDIENT", [e.code for e in m.log.events])
        self.assertTrue(any("Cocoa" in w for w in out.warnings))

    def test_dashboard_reports_state(self) -> None:
        """The dashboard exposes what a remote technician needs.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.place_order(m.start_order("espresso"), "contactless", GOOD_CARD)
        m.technician_login("4242")
        dash = m.dashboard()
        self.assertEqual(dash["transactions"], 1)
        self.assertTrue(dash["online"])
        self.assertTrue(dash["ingredients"])


class TestPersistence(unittest.TestCase):
    """NFR-09 - state survives a restart."""

    def test_round_trip_through_a_file(self) -> None:
        """A saved machine reloads with its accounts, stock and log intact.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        m.set_preferences(milk="oat", strength=3)
        draft = m.start_order("latte")
        m.save_current_as(draft, "Usual")
        out = m.place_order(draft, "contactless", GOOD_CARD)
        beans = m.inventory.ingredients["beans"].level
        points = m.current_user.loyalty_points

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            storage.save_state(m.snapshot(), path)
            restored = Machine.restore(storage.load_state(path))

        self.assertEqual(restored.inventory.ingredients["beans"].level, beans)
        self.assertEqual(len(restored.transaction_log()), 1)
        self.assertEqual(restored.transaction_log()[0].transaction_id,
                         out.transaction.transaction_id)
        user = restored.accounts.users["ahmed"]
        self.assertEqual(user.loyalty_points, points)
        self.assertEqual(user.preferences.milk, "oat")
        self.assertIn("Usual", user.saved_recipes)
        self.assertIsNone(restored.current_user)

    def test_restored_machine_still_authenticates(self) -> None:
        """Password and PIN hashes survive the round trip.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        m = machine_with_user()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            storage.save_state(m.snapshot(), path)
            restored = Machine.restore(storage.load_state(path))
        self.assertEqual(restored.login("ahmed", "coffee123").user_id, "ahmed")
        self.assertTrue(restored.technician_login("4242"))

    def test_missing_file_is_a_cold_start(self) -> None:
        """A machine with no state file starts fresh rather than failing.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(storage.load_state(Path(tmp) / "nope.json"), {})

    def test_corrupt_file_is_a_cold_start(self) -> None:
        """A damaged state file does not crash the machine.

        Input:
            None (unittest supplies no arguments).

        Returns:
            None. The test fails by raising AssertionError.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(storage.load_state(path), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
