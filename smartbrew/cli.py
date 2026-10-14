"""Interactive touchscreen simulator for SmartBrew AI.

This is the user-facing shell for the machine. It holds no business rules: it
reads input, calls Machine, and prints what comes back. State is loaded from
and saved to the JSON state file, so a session survives restarting the program
(NFR-09).

Run with:  python main.py
"""

from __future__ import annotations

import sys

from . import loyalty, storage
from .accounts import AuthError
from .inventory import BIN_CAPACITY, BinsFull, OutOfStock
from .loyalty import LoyaltyError
from .machine import Machine, MachineError, OrderDraft
from .models import CUP_SIZES, MILK_TYPES, STRENGTHS, TEMPERATURES
from .mood import MoodSensor
from .payments import METHODS, PaymentDeclined

DEMO_CARD = "5412751234564242"


def ask(prompt: str, default: str = "") -> str:
    """Read one line from the user, returning a default on empty input.

    Input:
        prompt (str): Text shown before the cursor.
        default (str): Value returned when the user just presses Enter.

    Returns:
        str: The user's answer, stripped, or the default.

    Raises:
        SystemExit: When the input stream closes (Ctrl-D), so the program can
            shut down cleanly instead of looping on EOF.
    """
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        print()
        raise SystemExit(0) from None
    return answer or default


def choose(prompt: str, options: tuple, default: str) -> str:
    """Ask the user to pick one of a fixed set of options.

    Input:
        prompt (str): Text shown before the cursor.
        options (tuple): Permitted values.
        default (str): Value used on empty input.

    Returns:
        str: One of `options`.
    """
    shown = "/".join(str(o) for o in options)
    while True:
        answer = ask(f"{prompt} ({shown})", str(default))
        for option in options:
            if answer == str(option):
                return answer
        print(f"  Please choose one of: {shown}")


def banner(machine: Machine) -> None:
    """Print the machine's status header.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    user = machine.current_user
    who = f"{user.display_name} ({user.loyalty_points} points)" if user else "not logged in"
    net = "online" if machine.terminal.online else "OFFLINE"
    admin = "  [TECHNICIAN MODE]" if machine.technician_mode else ""
    faults = machine.log.blocking()
    status = f"  !! {len(faults)} blocking fault(s)" if faults else ""
    print()
    print("-" * 68)
    print(f" SmartBrew AI   |  {who}  |  {net}{admin}{status}")
    print("-" * 68)


def show_menu(machine: Machine) -> None:
    """Print the catalogue with prices, nutrition and availability.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    current_category = None
    for drink, available, blocking in machine.menu():
        if drink.category != current_category:
            current_category = drink.category
            print(f"\n  {current_category}")
        allergens = ", ".join(drink.allergens) or "none"
        state = "" if available else f"   UNAVAILABLE ({', '.join(blocking)})"
        print(f"    {drink.key:<14} {drink.name:<16} {drink.base_price:>6.2f} SEK"
              f"  {drink.kcal:>4} kcal  allergens: {allergens}{state}")
    print()


def show_recommendations(machine: Machine) -> None:
    """Print the menu ranked by recommendation score.

    Offers to use the mood camera first, since that is one of the signals.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    reading = None
    if ask("Use the mood camera? (y/n)", "n").lower().startswith("y"):
        simulated = choose("  Simulated mood", ("neutral", "tired", "happy", "stressed"),
                           "tired")
        reading = machine.read_mood(MoodSensor.simulate_frame(simulated))
        if reading:
            print(f"  Detected {reading.mood} (confidence {reading.confidence}). "
                  f"The frame was analysed in memory and discarded.")
        else:
            print("  Camera unavailable; continuing without a mood reading.")

    weather = machine.weather.current()
    note = " (estimate, weather service unreachable)" if weather.stale else ""
    print(f"\n  Outdoor temperature: {weather.temperature_c:.0f} C{note}\n")
    for position, scored in enumerate(machine.recommendations(mood=reading), start=1):
        why = "; ".join(scored.reasons) or "no particular signal"
        print(f"  {position}. {scored.drink.name:<16} score {scored.score:>6.2f}   {why}")
    print()


def customise_draft(machine: Machine, draft: OrderDraft) -> None:
    """Let the user adjust the order, showing the price after each change.

    Input:
        machine (Machine): The running machine.
        draft (OrderDraft): The order being configured.

    Returns:
        None.
    """
    while True:
        print(f"\n  Current: {draft.customisation.describe()}  ->  "
              f"{draft.price():.2f} SEK")
        print("  1) milk   2) strength   3) size   4) temperature   5) syrup"
              "   6) show breakdown   0) done")
        pick = ask("  Change", "0")
        try:
            if pick == "1":
                machine.customise(draft, milk=choose("  Milk", MILK_TYPES,
                                                     draft.customisation.milk))
            elif pick == "2":
                machine.customise(draft, strength=int(
                    choose("  Strength", STRENGTHS, str(draft.customisation.strength))))
            elif pick == "3":
                machine.customise(draft, size=choose("  Size", CUP_SIZES,
                                                     draft.customisation.size))
            elif pick == "4":
                machine.customise(draft, temperature=choose(
                    "  Temperature", TEMPERATURES, draft.customisation.temperature))
            elif pick == "5":
                machine.customise(draft, syrup_shots=int(
                    ask("  Syrup pumps", str(draft.customisation.syrup_shots))))
            elif pick == "6":
                for label, amount in draft.breakdown():
                    print(f"    {label:<28} {amount:>8.2f}")
            elif pick == "0":
                return
            else:
                print("  Not an option.")
        except (ValueError, TypeError) as exc:
            print(f"  {exc}")


def checkout(machine: Machine, draft: OrderDraft) -> None:
    """Take payment for a draft, brew it and show the receipt.

    Input:
        machine (Machine): The running machine.
        draft (OrderDraft): The configured order.

    Returns:
        None.
    """
    price = draft.price()
    print(f"\n  Total: {price:.2f} SEK")

    redeem = 0
    user = machine.current_user
    if user:
        usable = loyalty.max_redeemable(user.loyalty_points, price)
        if usable:
            print(f"  You have {user.loyalty_points} points; "
                  f"you may redeem {usable} for {usable // 100 * 10} SEK off.")
            if ask("  Redeem them? (y/n)", "n").lower().startswith("y"):
                redeem = usable
        elif user.loyalty_points < loyalty.REDEEM_THRESHOLD:
            print(f"  Loyalty balance {user.loyalty_points} "
                  f"(need {loyalty.REDEEM_THRESHOLD} to redeem).")

    method = choose("  Payment method", METHODS, "contactless")
    card = ask("  Card reference", DEMO_CARD)
    receipt = choose("  Receipt", ("qr", "email"), "qr")

    try:
        outcome = machine.place_order(draft, method, card, redeem_points=redeem,
                                      receipt=receipt)
    except PaymentDeclined as exc:
        print(f"\n  PAYMENT DECLINED: {exc}")
        print("  Nothing was brewed and you have not been charged.")
        return
    except (OutOfStock, BinsFull) as exc:
        print(f"\n  CANNOT BREW: {exc}")
        return
    except (LoyaltyError, MachineError) as exc:
        print(f"\n  {exc}")
        return

    print("\n  Brewing... enjoy your drink.\n")
    for line in outcome.receipt.splitlines():
        print("  " + line)
    for warning in outcome.warnings:
        print(f"\n  NOTE: {warning}")
    if machine.current_user:
        print(f"\n  Loyalty balance: {machine.current_user.loyalty_points} points")


def order_flow(machine: Machine) -> None:
    """Run the full ordering journey: pick, customise, optionally save, pay.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    show_menu(machine)
    key = ask("  Drink key (blank to cancel)")
    if not key:
        return
    try:
        draft = machine.start_order(key)
    except MachineError as exc:
        print(f"  {exc}")
        return

    customise_draft(machine, draft)

    if machine.current_user and ask("  Save this as a recipe? (y/n)", "n").lower().startswith("y"):
        name = ask("  Recipe name")
        try:
            machine.save_current_as(draft, name)
            print(f"  Saved as '{name}'.")
        except (ValueError, MachineError) as exc:
            print(f"  {exc}")

    checkout(machine, draft)


def account_flow(machine: Machine) -> None:
    """Register, log in by password or NFC, or edit preferences.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    print("\n  1) register   2) log in   3) log in with NFC   4) preferences"
          "   5) log out   0) back")
    pick = ask("  Choose", "0")
    try:
        if pick == "1":
            uid = ask("  User id")
            name = ask("  Display name", uid)
            email = ask("  E-mail", f"{uid}@example.com")
            password = ask("  Password (min 6 chars)")
            nfc = ask("  NFC card id (blank for none)")
            machine.register(uid, name, email, password, nfc or None)
            print(f"  Account created. Welcome, {name}.")
        elif pick == "2":
            machine.login(ask("  User id"), ask("  Password"))
            print(f"  Welcome back, {machine.current_user.display_name}.")
        elif pick == "3":
            machine.login_nfc(ask("  Tap card (enter card id)"))
            print(f"  Welcome back, {machine.current_user.display_name}.")
        elif pick == "4":
            if machine.current_user is None:
                print("  Log in first.")
                return
            prefs = machine.current_user.preferences
            machine.set_preferences(
                milk=choose("  Default milk", MILK_TYPES, prefs.milk),
                strength=int(choose("  Default strength", STRENGTHS, str(prefs.strength))),
                size=choose("  Default size", CUP_SIZES, prefs.size),
            )
            print(f"  Defaults: {machine.current_user.preferences.describe()}")
        elif pick == "5":
            machine.logout()
            print("  Logged out.")
    except (AuthError, MachineError, TypeError, ValueError) as exc:
        print(f"  {exc}")


def saved_recipe_flow(machine: Machine) -> None:
    """List saved recipes and reorder or delete one.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    user = machine.current_user
    if user is None:
        print("  Log in to use saved recipes.")
        return
    if not user.saved_recipes:
        print("  No saved recipes yet. Save one while ordering.")
        return

    print()
    for name, recipe in user.saved_recipes.items():
        drink = machine.drinks.get(recipe.drink_key)
        label = drink.name if drink else recipe.drink_key
        print(f"    {name:<20} {label}, {recipe.customisation.describe()}")

    name = ask("\n  Recipe to order (or 'del <name>', blank to cancel)")
    if not name:
        return
    if name.startswith("del "):
        removed = machine.accounts.delete_recipe(user, name[4:])
        print("  Deleted." if removed else "  No such recipe.")
        return
    try:
        draft = machine.order_saved(name)
    except MachineError as exc:
        print(f"  {exc}")
        return
    print(f"  {draft.drink.name}, {draft.customisation.describe()} - "
          f"{draft.price():.2f} SEK")
    checkout(machine, draft)


def technician_flow(machine: Machine) -> None:
    """Administrative mode: dashboard, refills, bins, faults, event log.

    Input:
        machine (Machine): The running machine.

    Returns:
        None.
    """
    if not machine.technician_mode:
        if not machine.technician_login(ask("  Technician PIN")):
            print("  Access denied. The attempt has been logged.")
            return
        print("  Administrative mode unlocked.")

    while True:
        print("\n  1) dashboard   2) refill   3) empty bins   4) event log"
              "   5) clear fault   6) raise test fault   0) exit admin")
        pick = ask("  Choose", "0")
        try:
            if pick == "1":
                dash = machine.dashboard()
                print(f"\n  Network: {'online' if dash['online'] else 'OFFLINE'}"
                      f"   Transactions: {dash['transactions']}"
                      f"   Pending settlement: {len(dash['pending_settlements'])}")
                print(f"  Grounds bin {dash['grounds_bin']}/{BIN_CAPACITY}"
                      f"   Waste water {dash['waste_water']}/{BIN_CAPACITY}"
                      f"   {'FULL' if dash['bins_full'] else 'ok'}")
                print("\n  Ingredients:")
                for ing in dash["ingredients"]:
                    flag = "  LOW" if ing["depleted"] else ""
                    print(f"    {ing['label']:<22} {ing['level']:>8.1f} / "
                          f"{ing['capacity']:.0f} {ing['unit']}{flag}")
                print("\n  Active faults:")
                for message in dash["active_faults"] or ["    (none)"]:
                    print(f"    {message}")
            elif pick == "2":
                for key, ing in machine.inventory.ingredients.items():
                    print(f"    {key:<22} {ing.level:>8.1f} / {ing.capacity:.0f} {ing.unit}")
                machine.refill(ask("  Ingredient key"))
                print("  Refilled to capacity.")
            elif pick == "3":
                machine.empty_bins()
                print("  Both containers emptied.")
            elif pick == "4":
                for event in machine.log.tail(25):
                    flag = "cleared" if event.cleared else "ACTIVE "
                    print(f"    {event.timestamp}  {flag}  "
                          f"[{event.severity:<7}] {event.message}")
            elif pick == "5":
                print(f"  Cleared {machine.clear_fault(ask('  Fault code'))} event(s).")
            elif pick == "6":
                machine.report_fault(ask("  Fault code", "GRINDER_JAM"))
                print("  Fault raised.")
            elif pick == "0":
                machine.technician_logout()
                return
        except MachineError as exc:
            print(f"  {exc}")


def run(state_path: str = str(storage.DEFAULT_STATE_PATH)) -> int:
    """Run the interactive machine until the user exits.

    State is loaded at start and saved on exit and after every purchase, so a
    crash loses at most the order in progress.

    Input:
        state_path (str): Path to the JSON state file.

    Returns:
        int: Process exit code, always 0.
    """
    state = storage.load_state(state_path)
    machine = Machine.restore(state) if state else Machine()
    if not state:
        # First run: give the demo staff card some credit so the prepaid
        # payment path can be tried without extra setup.
        machine.terminal.top_up_employee_card("EMP-00731", 500.0)

    print("SmartBrew AI - touchscreen simulator")
    print("Technician PIN is 4242. Demo card ends 4242; a card ending 0000 is declined.")

    while True:
        banner(machine)
        print("  1) menu            2) recommendations   3) order a drink")
        print("  4) saved recipes   5) account           6) transaction log")
        print("  7) technician      8) toggle network    0) exit")
        pick = ask("Choose", "0")

        if pick == "1":
            show_menu(machine)
        elif pick == "2":
            show_recommendations(machine)
        elif pick == "3":
            order_flow(machine)
            storage.save_state(machine.snapshot(), state_path)
        elif pick == "4":
            saved_recipe_flow(machine)
            storage.save_state(machine.snapshot(), state_path)
        elif pick == "5":
            account_flow(machine)
            storage.save_state(machine.snapshot(), state_path)
        elif pick == "6":
            log = machine.transaction_log()
            if not log:
                print("  No transactions yet.")
            for tx in log:
                mark = "" if tx.settled else "  [pending settlement]"
                print(f"    {tx.timestamp}  {tx.drink_key:<12}"
                      f"{tx.net_amount:>7.2f} SEK  {tx.payment_reference}{mark}")
        elif pick == "7":
            technician_flow(machine)
            storage.save_state(machine.snapshot(), state_path)
        elif pick == "8":
            settled = machine.set_network(not machine.terminal.online)
            print(f"  Network is now "
                  f"{'online' if machine.terminal.online else 'offline'}.")
            if settled:
                print(f"  Settled {len(settled)} queued transaction(s).")
        elif pick == "0":
            storage.save_state(machine.snapshot(), state_path)
            print(f"\n  State saved to {state_path}. Goodbye.")
            return 0
        else:
            print("  Not an option.")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the interactive simulator.

    Input:
        argv (list[str] | None): Command-line arguments after the program
            name. An optional first argument overrides the state file path.

    Returns:
        int: Process exit code.
    """
    args = sys.argv[1:] if argv is None else argv
    path = args[0] if args else str(storage.DEFAULT_STATE_PATH)
    try:
        return run(path)
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        return 130
