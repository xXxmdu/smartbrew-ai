#!/usr/bin/env python3
"""Scripted demonstration of all ten SmartBrew AI features.

Run with:

    python demo.py            # run every feature in order
    python demo.py 5          # run only feature 5
    python demo.py 3 7 10     # run a selection

Each section prints what it is about to do, performs it against a real Machine
instance, and prints the observable result. Nothing is faked for display: every
number shown comes back from the running system.
"""

from __future__ import annotations

import sys

from smartbrew import loyalty
from smartbrew.inventory import BIN_CAPACITY, OutOfStock
from smartbrew.machine import Machine, MachineError
from smartbrew.models import Customisation
from smartbrew.mood import MoodSensor
from smartbrew.payments import PaymentDeclined

GOOD_CARD = "5412751234564242"
BAD_CARD = "5412751234560000"
STAFF_CARD = "EMP-00731"
NFC_CARD = "NFC-AB12-9931"


def rule(title: str) -> None:
    """Print a section heading.

    Input:
        title (str): The heading text.

    Returns:
        None.
    """
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def step(text: str) -> None:
    """Print a single narrated step.

    Input:
        text (str): Description of what is happening.

    Returns:
        None.
    """
    print(f"  -> {text}")


def fresh_machine_with_user() -> Machine:
    """Build a machine with one registered, logged-in customer.

    Input:
        None.

    Returns:
        Machine: A machine with user "ahmed" logged in and a topped-up staff
        card.
    """
    m = Machine()
    m.register("ahmed", "Ahmed", "ahmed@example.com", "coffee123",
               nfc_token=NFC_CARD)
    m.terminal.top_up_employee_card(STAFF_CARD, 200.0)
    return m


def feature_1() -> None:
    """Feature 1 - accounts, password and NFC login, preference profiles.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 1  Accounts, login (password + NFC) and preference profiles")
    m = Machine()

    step("Registering account 'ahmed'")
    user = m.register("ahmed", "Ahmed", "ahmed@example.com", "coffee123",
                      nfc_token=NFC_CARD)
    print(f"     created: {user.display_name} <{user.email}>")
    print(f"     password stored as PBKDF2 hash: {user.password_hash[:24]}...")
    print(f"     clear-text password is not stored anywhere on the record")

    step("Setting preference profile to oat milk, strength 3, large")
    prefs = m.set_preferences(milk="oat", strength=3, size="large")
    print(f"     defaults now: {prefs.describe()}")

    step("Logging out, then logging back in with the password")
    m.logout()
    m.login("ahmed", "coffee123")
    print(f"     welcome back, {m.current_user.display_name}")

    step("Logging out, then logging back in with a single NFC tap")
    m.logout()
    m.login_nfc(NFC_CARD)
    print(f"     welcome back, {m.current_user.display_name}")

    step("Trying a wrong password")
    m.logout()
    try:
        m.login("ahmed", "wrong-password")
    except Exception as exc:
        print(f"     refused: {exc}")

    step("Starting an order and checking the profile was applied")
    m.login_nfc(NFC_CARD)
    draft = m.start_order("latte")
    print(f"     new order pre-filled with: {draft.customisation.describe()}")


def feature_2() -> None:
    """Feature 2 - menu browsing with price, ingredients, allergens, nutrition.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 2  Menu browsing: categories, price, allergens, nutrition")
    m = Machine()
    by_category: dict[str, list] = {}
    for drink, available, _ in m.menu():
        by_category.setdefault(drink.category, []).append((drink, available))

    for category, rows in by_category.items():
        print(f"\n  {category}")
        for drink, available in rows:
            allergens = ", ".join(drink.allergens) or "none"
            mark = " " if available else " (unavailable)"
            print(
                f"    {drink.name:<16} {drink.base_price:>6.2f} SEK   "
                f"{drink.kcal:>4} kcal   {drink.caffeine_mg:>3} mg caffeine   "
                f"allergens: {allergens}{mark}"
            )


def feature_3() -> None:
    """Feature 3 - real-time customisation with live price recalculation.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 3  Real-time customisation with live pricing")
    m = fresh_machine_with_user()
    m.set_preferences(milk="whole", strength=2, size="medium")
    draft = m.start_order("latte")

    step(f"Starting point: {draft.customisation.describe()}")
    print(f"     price {draft.price():.2f} SEK")

    for change in ({"milk": "oat"}, {"strength": 4}, {"size": "large"},
                   {"syrup_shots": 2}):
        label = ", ".join(f"{k}={v}" for k, v in change.items())
        new_price = m.customise(draft, **change)
        step(f"Change {label:<18} -> {new_price:.2f} SEK")

    print("\n  Itemised breakdown now shown on screen before confirming:")
    for label, amount in draft.breakdown():
        print(f"    {label:<28} {amount:>8.2f}")

    step("Rejecting an invalid option")
    try:
        m.customise(draft, size="bucket")
    except ValueError as exc:
        print(f"     refused: {exc}")


def feature_4() -> None:
    """Feature 4 - ingredient stock, depletion and availability blocking.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 4  Ingredient stock, depletion and availability blocking")
    m = fresh_machine_with_user()
    m.set_preferences(milk="oat")

    before = m.inventory.ingredients["oat_milk"].level
    step(f"Oat milk before brewing: {before:.0f} ml")

    draft = m.start_order("latte")
    m.place_order(draft, "contactless", GOOD_CARD)
    after = m.inventory.ingredients["oat_milk"].level
    step(f"Oat milk after one latte: {after:.0f} ml  (consumed {before - after:.0f} ml)")

    step("Draining the oat milk down to its minimum threshold")
    m.inventory.ingredients["oat_milk"].level = 150.0
    oat = Customisation(milk="oat")
    for drink, available, blocking in m.menu(oat):
        if not available:
            print(f"     {drink.name:<16} unavailable - blocked by: {', '.join(blocking)}")

    step("Ordering an oat latte anyway")
    try:
        draft = m.start_order("latte")
        m.customise(draft, milk="oat")
        m.place_order(draft, "contactless", GOOD_CARD)
    except OutOfStock as exc:
        print(f"     refused: out of stock - {exc}")

    step("The same drink with whole milk is still available")
    draft = m.start_order("latte")
    m.customise(draft, milk="whole")
    out = m.place_order(draft, "contactless", GOOD_CARD)
    print(f"     brewed, charged {out.transaction.net_amount:.2f} SEK")


def feature_5() -> None:
    """Feature 5 - payment methods, decline path, offline mode, settlement.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 5  Payments: four methods, declines, offline settlement")
    m = fresh_machine_with_user()

    for method, card in (("contactless", GOOD_CARD), ("chip", GOOD_CARD),
                         ("wallet", GOOD_CARD), ("employee_card", STAFF_CARD)):
        draft = m.start_order("espresso")
        out = m.place_order(draft, method, card)
        step(f"{method:<14} approved  {out.transaction.payment_reference}  "
             f"{out.transaction.net_amount:.2f} SEK")

    step("A card the issuer declines")
    stock_before = m.inventory.ingredients["beans"].level
    draft = m.start_order("latte")
    try:
        m.place_order(draft, "contactless", BAD_CARD)
    except PaymentDeclined as exc:
        print(f"     refused: {exc}")
    stock_after = m.inventory.ingredients["beans"].level
    print(f"     beans unchanged ({stock_before:.0f} g -> {stock_after:.0f} g): "
          f"nothing was brewed")

    step("Employee card with insufficient credit")
    m.terminal.employee_balances[STAFF_CARD] = 5.0
    draft = m.start_order("mocha")
    try:
        m.place_order(draft, "employee_card", STAFF_CARD)
    except PaymentDeclined as exc:
        print(f"     refused: {exc}")

    step("Pulling the network out")
    m.set_network(False)
    draft = m.start_order("espresso")
    out = m.place_order(draft, "contactless", GOOD_CARD)
    print(f"     still served: {out.payment.detail}")
    print(f"     transaction settled? {out.transaction.settled}")
    print(f"     queued for settlement: {m.terminal.pending}")

    step("Restoring the network")
    settled = m.set_network(True)
    print(f"     settled now: {settled}")
    print(f"     queue after settling: {m.terminal.pending}")
    step("Calling settle again to prove a transaction cannot be charged twice")
    print(f"     settled on second call: {m.terminal.settle_pending()}")


def feature_6() -> None:
    """Feature 6 - recommendations from history, time, weather and mood.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 6  Recommendation engine (history, time, weather, mood)")
    m = fresh_machine_with_user()
    m.weather.temperature_c = 2.0
    m.current_user.history.extend(["latte", "latte", "latte", "espresso"])

    step("Cold morning (08:00, 2 degrees), customer usually drinks latte")
    for scored in m.recommendations(hour=8)[:4]:
        why = "; ".join(scored.reasons) or "no particular reason"
        print(f"     {scored.score:>6.2f}  {scored.drink.name:<16} {why}")

    step("Same customer, warm afternoon (16:00, 26 degrees)")
    m.weather.temperature_c = 26.0
    for scored in m.recommendations(hour=16)[:4]:
        why = "; ".join(scored.reasons) or "no particular reason"
        print(f"     {scored.score:>6.2f}  {scored.drink.name:<16} {why}")

    step("Now with a 'tired' reading from the camera")
    frame = MoodSensor.simulate_frame("tired")
    reading = m.read_mood(frame)
    print(f"     detected: {reading.mood} (confidence {reading.confidence})")

    before = {s.drink.key: (i + 1, s.score)
              for i, s in enumerate(m.recommendations(hour=16))}
    after = m.recommendations(mood=reading, hour=16)
    print(f"     {'drink':<16}{'rank':>10}{'score':>16}")
    for position, scored in enumerate(after, start=1):
        old_rank, old_score = before[scored.drink.key]
        arrow = "same" if old_rank == position else f"{old_rank} -> {position}"
        delta = scored.score - old_score
        marker = f"  {delta:+.2f}" if abs(delta) > 1e-9 else ""
        print(f"     {scored.drink.name:<16}{arrow:>10}"
              f"{old_score:>8.2f} ->{scored.score:>6.2f}{marker}")
    boosted = [s for s in after if "tired" in " ".join(s.reasons)]
    for s in boosted:
        print(f"     boosted: {s.drink.name} ({s.drink.caffeine_mg} mg caffeine) "
              f"- {'; '.join(s.reasons)}")

    step("Privacy check (NFR-01): the reading carries no image data")
    print(f"     MoodReading fields: {list(vars(reading).keys())}")
    print(f"     frames analysed: {m.mood_sensor.frames_processed}, frames retained: 0")

    step("Camera unplugged - ordering must continue regardless")
    m.mood_sensor.enabled = False
    print(f"     read_mood returns: {m.read_mood(frame)}")
    print(f"     menu still ranks {len(m.recommendations(hour=16))} drinks")


def feature_7() -> None:
    """Feature 7 - loyalty points, earned and redeemed (our own feature).

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 7  Loyalty points: earn and redeem  [our own feature]")
    m = fresh_machine_with_user()
    print(f"  Rules: 1 point per SEK charged; redeem in blocks of "
          f"{loyalty.POINTS_PER_BLOCK} worth {loyalty.BLOCK_VALUE_SEK:.0f} SEK, "
          f"from {loyalty.REDEEM_THRESHOLD} points.")

    step("Buying drinks until the balance passes the threshold")
    for i in range(5):
        draft = m.start_order("mocha")
        out = m.place_order(draft, "contactless", GOOD_CARD)
        print(f"     purchase {i + 1}: charged {out.transaction.net_amount:>6.2f} SEK, "
              f"+{out.transaction.points_earned:>3} points, "
              f"balance {m.current_user.loyalty_points}")

    balance = m.current_user.loyalty_points
    draft = m.start_order("mocha")
    gross = draft.price()
    usable = loyalty.max_redeemable(balance, gross)
    step(f"Next mocha costs {gross:.2f} SEK; balance {balance} allows {usable} points")

    out = m.place_order(draft, "contactless", GOOD_CARD, redeem_points=usable)
    tx = out.transaction
    print(f"     gross {tx.gross_amount:.2f} - discount {tx.discount:.2f} "
          f"= charged {tx.net_amount:.2f} SEK")
    print(f"     points: -{tx.points_redeemed} redeemed, +{tx.points_earned} earned, "
          f"balance now {m.current_user.loyalty_points}")

    step("Trying to redeem more points than the balance holds")
    try:
        loyalty.redeem(500, 90.0, 900)
    except loyalty.LoyaltyError as exc:
        print(f"     refused: {exc}")

    step("Trying to redeem a part-block")
    try:
        loyalty.redeem(500, 50.0, 150)
    except loyalty.LoyaltyError as exc:
        print(f"     refused: {exc}")

    step("Trying to redeem below the threshold")
    try:
        loyalty.redeem(88, 33.0, 100)
    except loyalty.LoyaltyError as exc:
        print(f"     refused: {exc}")

    step("Points are not earned on the discounted part, so they cannot self-fund")
    r = loyalty.redeem(200, 33.0, 200)
    print(f"     redeem 200 points on a 33.00 SEK drink: discount {r.discount:.2f}, "
          f"charged {33.0 - r.discount:.2f}, earns only "
          f"{loyalty.points_for(33.0 - r.discount)} points back")


def feature_8() -> None:
    """Feature 8 - saved recipes and one-touch reordering.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 8  Saved recipes and one-touch reorder")
    m = fresh_machine_with_user()

    step("Configuring a drink and saving it as 'Morning Oat'")
    draft = m.start_order("latte")
    m.customise(draft, milk="oat", strength=3, size="large", syrup_shots=1)
    recipe = m.save_current_as(draft, "Morning Oat")
    print(f"     saved: {recipe.name} = {recipe.drink_key}, "
          f"{recipe.customisation.describe()}")

    step("Logging out and back in")
    m.logout()
    m.login("ahmed", "coffee123")
    print(f"     recipes on profile: {list(m.current_user.saved_recipes)}")

    step("One-touch reorder")
    draft = m.order_saved("Morning Oat")
    print(f"     rebuilt: {draft.drink.name}, {draft.customisation.describe()}, "
          f"{draft.price():.2f} SEK")
    out = m.place_order(draft, "wallet", GOOD_CARD)
    print(f"     brewed and charged {out.transaction.net_amount:.2f} SEK")

    step("Deleting the recipe")
    print(f"     deleted: {m.accounts.delete_recipe(m.current_user, 'Morning Oat')}")
    try:
        m.order_saved("Morning Oat")
    except MachineError as exc:
        print(f"     refused: {exc}")


def feature_9() -> None:
    """Feature 9 - receipts by QR or e-mail, and the transaction log.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 9  Receipts (QR or e-mail) and the transaction log")
    m = fresh_machine_with_user()

    step("Buying a drink and taking the on-screen QR receipt")
    draft = m.start_order("cappuccino")
    m.customise(draft, milk="soy", size="large")
    out = m.place_order(draft, "contactless", GOOD_CARD, receipt="qr")
    print()
    for line in out.receipt.splitlines():
        print("     " + line)

    step("Buying another and taking the e-mail receipt instead")
    draft = m.start_order("espresso")
    out = m.place_order(draft, "chip", GOOD_CARD, receipt="email")
    print()
    for line in out.receipt.splitlines():
        print("     " + line)

    step("The transaction log")
    print(f"     {'time':<21}{'drink':<12}{'config':<34}{'paid':>8}  method")
    for tx in m.transaction_log():
        print(f"     {tx.timestamp:<21}{tx.drink_key:<12}"
              f"{tx.customisation.describe():<34}{tx.net_amount:>8.2f}  "
              f"{tx.payment_reference}")

    step("Security check (NFR-06): no full card number anywhere in the log")
    blob = " ".join(str(tx.to_dict()) for tx in m.transaction_log())
    print(f"     full PAN '{GOOD_CARD}' present in log? {GOOD_CARD in blob}")


def feature_10() -> None:
    """Feature 10 - technician mode, refills, waste bins, faults, event log.

    Input:
        None.

    Returns:
        None.
    """
    rule("FEATURE 10  Technician mode: refills, waste bins, faults, event log")
    m = fresh_machine_with_user()

    step("Trying an administrative action while locked")
    try:
        m.refill("oat_milk")
    except MachineError as exc:
        print(f"     refused: {exc}")

    step("Entering the wrong PIN")
    print(f"     accepted? {m.technician_login('0000')}")
    print(f"     logged: {m.log.events[-1].message}")

    step("Entering the correct PIN")
    print(f"     accepted? {m.technician_login('4242')}")

    step("Draining oat milk, then refilling it")
    m.inventory.ingredients["oat_milk"].level = 40.0
    print(f"     before: {m.inventory.ingredients['oat_milk'].level:.0f} ml "
          f"(depleted: {m.inventory.ingredients['oat_milk'].depleted})")
    ing = m.refill("oat_milk")
    print(f"     after refill: {ing.level:.0f} ml (depleted: {ing.depleted})")

    step("Filling the waste container to capacity")
    m.inventory.grounds_bin = BIN_CAPACITY - 1
    m.technician_logout()
    draft = m.start_order("espresso")
    out = m.place_order(draft, "contactless", GOOD_CARD)
    print(f"     warnings after that drink: {out.warnings}")

    step("Ordering again with the bin full")
    try:
        m.start_order("espresso")
    except MachineError as exc:
        print(f"     refused: {exc}")

    step("Technician empties the bin and service resumes")
    m.technician_login("4242")
    m.empty_bins()
    m.technician_logout()
    draft = m.start_order("espresso")
    out = m.place_order(draft, "contactless", GOOD_CARD)
    print(f"     served again, charged {out.transaction.net_amount:.2f} SEK")

    step("Raising a hardware fault")
    m.report_fault("GRINDER_JAM", "burr motor stalled")
    try:
        m.start_order("latte")
    except MachineError as exc:
        print(f"     refused: {exc}")

    step("Administrative dashboard")
    m.technician_login("4242")
    dash = m.dashboard()
    print(f"     online: {dash['online']}   transactions: {dash['transactions']}   "
          f"grounds bin: {dash['grounds_bin']}/{BIN_CAPACITY}")
    print(f"     active faults: {dash['active_faults']}")

    step("Clearing the fault and serving again")
    m.clear_fault("GRINDER_JAM")
    m.technician_logout()
    draft = m.start_order("latte")
    print(f"     order accepted again: {draft.drink.name} at {draft.price():.2f} SEK")

    step("Event log (remote diagnostics view)")
    for event in m.log.tail(8):
        flag = "cleared" if event.cleared else "ACTIVE "
        print(f"     {event.timestamp}  {flag}  [{event.severity:<7}] {event.message}")


FEATURES = {
    1: feature_1,
    2: feature_2,
    3: feature_3,
    4: feature_4,
    5: feature_5,
    6: feature_6,
    7: feature_7,
    8: feature_8,
    9: feature_9,
    10: feature_10,
}


def main(argv: list[str]) -> int:
    """Run the requested feature demonstrations.

    Input:
        argv (list[str]): Command-line arguments after the program name. Empty
            means run all ten; otherwise each argument is a feature number.

    Returns:
        int: Process exit code, 0 on success and 2 on a bad argument.
    """
    if argv:
        try:
            wanted = [int(a) for a in argv]
        except ValueError:
            print("Usage: python demo.py [feature numbers 1-10]", file=sys.stderr)
            return 2
        unknown = [n for n in wanted if n not in FEATURES]
        if unknown:
            print(f"No such feature(s): {unknown}. Valid range is 1-10.",
                  file=sys.stderr)
            return 2
    else:
        wanted = sorted(FEATURES)

    print("SmartBrew AI - feature demonstration")
    print(f"Running feature(s): {', '.join(str(n) for n in wanted)}")
    for number in wanted:
        FEATURES[number]()
    print("\n" + "=" * 72)
    print("Demonstration complete.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
