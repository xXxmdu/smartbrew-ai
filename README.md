# SmartBrew AI

A working prototype of the SmartBrew AI intelligent coffee machine, built for
**Lab 3 — Code management with Generative AI**, course **DVA332 Software
Engineering 1**, Mälardalen University, autumn 2026.

**Authors:** Ahmed Al-Baghdadi, Mohsen Alawi (group G11)
**Built with LLM assistance:** Claude Opus 5 (`claude-opus-5`). See
[`docs/prompt-log.md`](docs/prompt-log.md) for the prompt strategy and
transcript, as required by Task A.

---

## 1. System overview

SmartBrew AI is a touchscreen coffee machine for offices and lounges. It
remembers who you are, learns what you like, recommends a drink from your
history and the weather, takes contactless payment, and keeps a technician
informed about refills and faults.

This repository implements **ten features** from the requirements elicited in
Task A, as a Python command-line application. The terminal stands in for the
machine's touchscreen; everything behind the screen — pricing, stock, payment
authorisation, recommendation scoring, loyalty accounting, fault handling — is
real working code with a test for each rule.

### The ten implemented features

| # | Feature | Requirements | Backlog item |
|---|---|---|---|
| 1 | Accounts, login by password or NFC tap, preference profiles | FR-01…FR-04 | PB-06 |
| 2 | Menu browsing: categories, price, ingredients, allergens, nutrition | FR-05, FR-06 | PB-01 |
| 3 | Real-time customisation with live price recalculation | FR-07, FR-08 | PB-04 |
| 4 | Ingredient stock, consumption on brewing, availability blocking | FR-09, FR-27 | PB-02, PB-05 |
| 5 | Payment (4 methods), decline handling, offline mode, deferred settlement | FR-18, FR-19, NFR-02, NFR-03 | PB-03, PB-14 |
| 6 | Recommendation engine: history, time of day, weather, mood | FR-13…FR-16, NFR-01, NFR-10 | PB-12, PB-15 |
| 7 | **Loyalty points: earn and redeem** *(our own feature)* | FR-28, FR-29 | PB-11 |
| 8 | Saved recipes and one-touch reorder | FR-10…FR-12 | PB-10 |
| 9 | Receipts by QR or e-mail, and the transaction log | FR-20, FR-21, NFR-06 | PB-07, PB-13 |
| 10 | Technician mode: PIN access, refills, waste bins, faults, event log | FR-22…FR-26, NFR-05 | PB-08, PB-09 |

Requirement IDs refer to the Task A report submitted on Canvas.

### Architecture

```
main.py                 entry point for the interactive simulator
demo.py                 scripted walkthrough of all ten features
smartbrew/
  models.py             dataclasses: Ingredient, Drink, User, Transaction, ...
  catalogue.py          seed drinks and seed ingredient stock
  pricing.py            price and ingredient consumption for a configured drink
  inventory.py          stock levels, availability rules, waste bins
  accounts.py           registration, password/NFC login, profiles, recipes
  payments.py           authorisation, declines, offline queue, settlement
  loyalty.py            points earned and redeemed
  mood.py               in-memory mood inference from a camera frame
  recommender.py        scoring and menu reordering, weather provider
  receipts.py           QR and e-mail receipt rendering
  faults.py             fault codes and the diagnostic event log
  machine.py            the facade that orchestrates all of the above
  storage.py            atomic JSON persistence
  cli.py                the touchscreen simulator
tests/
  test_smartbrew.py     76 tests, grouped by feature
```

The user interface contains no business rules. Everything goes through
`Machine`, which is why the test suite can exercise the whole system without a
terminal.

---

## 2. Environment and prerequisites

* **Python 3.10 or newer.** Checked on 3.11 (Linux) and 3.12 (Windows).
* **No third-party packages are required.** The whole prototype runs on the
  standard library, so there is nothing to install and nothing to go wrong with
  version mismatches on the evaluation machine.
* `requirements.txt` lists one *optional* package, `qrcode`, which upgrades the
  on-screen receipt from a labelled placeholder to a real scannable QR symbol.
  Everything works without it.

Check your version:

```bash
python --version        # or python3 --version
```

If it prints 3.10 or higher, you are ready. There is no build step.

---

## 3. Execution guide

Clone and enter the repository:

```bash
git clone https://github.com/<github-username>/smartbrew-ai.git
cd smartbrew-ai
```

> On Windows use `python`; on macOS and Linux use `python3`. Everything below
> is written with `python3`.

### 3.1 Run the test suite (fastest proof that it works)

```bash
python3 -m unittest discover -s tests
```

Expected: `Ran 76 tests` and `OK`, in about 10 seconds. The tests are grouped
by feature, so `-v` shows which feature each assertion belongs to:

```bash
python3 -m unittest discover -s tests -v
```

### 3.2 Run the scripted demonstration of all ten features

```bash
python3 demo.py
```

This runs every feature in order against a real machine and prints the
observable result of each step — prices changing, stock dropping, payments
declining, points being redeemed, faults halting service. Nothing is printed
that the running system did not actually produce.

To demonstrate one feature at a time:

```bash
python3 demo.py 7          # just the loyalty points feature
python3 demo.py 5 10       # payments, then technician mode
```

Feature numbers match the table in section 1.

### 3.3 Run the interactive simulator

```bash
python3 main.py
```

You get a numbered menu standing in for the touchscreen. State is saved to
`data/machine_state.json` on exit and after every purchase, so your account,
points and stock levels are still there next time. To start clean, delete that
file, or point the program somewhere else:

```bash
python3 main.py /tmp/scratch-state.json
```

**Demonstration credentials, all fake:**

| Thing | Value |
|---|---|
| Technician PIN | `4242` |
| Card that works | `5412751234564242` (any reference not ending `0000`) |
| Card that is declined | `5412751234560000` (any reference ending `0000`) |
| Prepaid employee card | `EMP-00731`, pre-loaded with 500 SEK |

### 3.4 Walking the ten features by hand

Each row below is a complete path through the interactive simulator.

| # | Feature | What to do | What you should see |
|---|---|---|---|
| 1 | Accounts and profiles | `5` → `1`, register; `5` → `4`, set oat / 3 / large; `5` → `5` log out; `5` → `3` tap your NFC id | Logged back in by card; a new order starts pre-filled with oat, strength 3, large |
| 2 | Menu | `1` | Drinks grouped by category with price, kcal and allergens |
| 3 | Customisation | `3` → `latte` → change milk, strength, size, syrup; then `6` | Price updates after every change; option 6 itemises how it was reached |
| 4 | Stock and availability | `7` → PIN `4242` → `1` to see levels; exit; buy several lattes; `1` | Milk level falls with each drink; once at threshold the drink is listed `UNAVAILABLE` |
| 5 | Payments | `3`, buy with card ending `0000`; then `8` to go offline and buy again; `8` to come back online | Declined card brews nothing; offline purchase is served and marked pending; reconnecting settles it once |
| 6 | Recommendations | `2`, answer `y`, choose `tired` | Menu reordered with a score and a plain-English reason per drink; Flat White rises on a tired reading |
| 7 | **Loyalty points** | Buy until the balance passes 100, then buy again and accept the offer | Points accumulate; the discount is applied; the charged amount drops by 10 SEK per 100 points |
| 8 | Saved recipes | During `3` answer `y` to save, name it; log out and in; `4` | The recipe survives the logout and reorders in one step |
| 9 | Receipts and log | Buy, choose `qr`; buy again, choose `email`; then `6` | A receipt with a scannable payload, an addressed e-mail, and a log showing only masked card references |
| 10 | Technician mode | `7` → wrong PIN, then `4242` → `1` dashboard, `2` refill, `6` raise `GRINDER_JAM`, `4` event log, `5` clear it | Wrong PIN is refused and logged; a raised fault takes the machine out of service until cleared |

The scripted equivalent of this whole table is `python3 demo.py`.

---

## 4. Design notes

**Payment is authorised before ingredients are consumed.** A declined card
therefore leaves the stock untouched and no transaction in the log. There is a
test for this (`test_declined_card_leaves_drink_unbrewed`); getting the order
wrong is the obvious way to give away free coffee.

**Camera frames are never persisted.** `MoodSensor.analyse()` takes the frame,
derives a label and a confidence, drops its reference and returns a
`MoodReading` that contains no image data. A test asserts that classifying four
frames creates no file on disk. This implements the one hard privacy constraint
in the system description.

**Points cannot fund themselves.** Loyalty points are earned on the amount
actually charged, not on the price before the discount, so redeeming never
regenerates the points it consumed.

**Offline settlement is idempotent.** Queued transaction ids are removed as they
settle, so calling settlement twice cannot charge a customer twice.

**Passwords and the technician PIN are stored as PBKDF2-HMAC-SHA256 hashes**
with per-record salts. The state file never contains either in clear text, and
there are tests asserting that.

---

## 5. Known simplifications

This is a course prototype, and these are the places where it deliberately
stops short. They are listed so nothing here is mistaken for production code.

1. **The mood classifier is simulated.** A real machine would run a vision
   model on its embedded compute module. The classifier here is a deterministic
   function of the frame bytes. What is implemented for real is the data-handling
   contract around it — in-memory only, nothing written, nothing transmitted —
   which is the part the requirements constrain.
2. **The payment terminal is simulated.** No acquirer is contacted. The decline
   rule (any card reference ending `0000`) exists so the failure path can be
   demonstrated deterministically.
3. **The weather provider returns a configured value** rather than calling a
   weather API, so the offline fallback can be demonstrated without a network.
4. **E-mail receipts are rendered, not sent.** The program prints the message it
   would send.
5. **QR rendering falls back to a labelled placeholder** when the optional
   `qrcode` package is absent. Install it with `pip install qrcode` for a real
   symbol.
6. **The natural-language ordering agent (FR-17) is not implemented.** The
   system description marks it optional and modular, and Task A estimated it at
   40 story points — larger than the first three sprints combined. The reasoning
   is recorded as rejection R3 in the Task A report.

---

## 6. Licence

Coursework submission for DVA332 at Mälardalen University. Not licensed for
reuse.
