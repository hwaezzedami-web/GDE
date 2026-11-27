#!/usr/bin/env python3
"""Telegram bot for Personal_Finance_Aboubakr_Bouchra.xlsx  -  بوت تيليغرام لملف المالية

Send short commands from your phone; the bot writes the line into the Excel file.

  /rate 277 279            today's EUR square price (sell [buy]) [usd_sell] [usd_buy]
  /sell 500 277 [place]    you sold 500 EUR at 277 DZD   (/sellusd for dollars)
  /spend 2500 food bread   family expense: amount, category word, description
  /income 10000 gift       extra income
  /give 15000 brother Ali  help a relative: amount, relation word, name
  /lend 20000 Yacine 2026-12-31 [EUR]    you lent money (owed to me)
  /borrow 50000 Karim 2026-12-15 [EUR]   you borrowed money (I owe)
  /pay D001 20000          a repayment on debt D001
  /save 50000 G01 [EUR]    money put aside for goal G01
  /summary   /debts   /help

Configuration (environment variables):
  BOT_TOKEN         token from @BotFather                       (required)
  ALLOWED_USER_IDS  comma separated Telegram user ids allowed   (required)
  EXCEL_PATH        path of the workbook (default: ../Personal_Finance_Aboubakr_Bouchra.xlsx)
  USER_NAMES        optional "111=Aboubakr - أبوبكر,222=Bouchra - بشرى" so "Who" is filled per sender

Close the workbook in Excel while the bot writes: Excel locks open files.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import re
from pathlib import Path

from openpyxl import load_workbook

# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
EXCEL_PATH = Path(os.environ.get("EXCEL_PATH", HERE.parent / "Personal_Finance_Aboubakr_Bouchra.xlsx"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED = {int(x) for x in re.split(r"[,\s]+", os.environ.get("ALLOWED_USER_IDS", "")) if x.strip().isdigit()}
USER_NAMES = {}
for part in os.environ.get("USER_NAMES", "").split(","):
    if "=" in part:
        uid, name = part.split("=", 1)
        if uid.strip().isdigit():
            USER_NAMES[int(uid.strip())] = name.strip()

# sheet names (must match the workbook)
RATES = "Rates - الأسعار"
SAL = "Salary - الراتب"
EXC = "Exchange - الصرف"
DEBT = "Debts - الديون"
PAY = "Payments - التسديد"
FAM = "Family - العائلة"
REL = "Relatives - الأقارب"
PLAN = "Plans - الخطط"
SAV = "Savings - الادخار"
SET = "Settings - الإعدادات"
ROWS = {RATES: (6, 405), SAL: (6, 65), EXC: (6, 305), DEBT: (6, 155), PAY: (6, 505),
        FAM: (6, 1505), REL: (6, 405), PLAN: (6, 35), SAV: (6, 505)}

BOTH = "Both - مشترك"
EXPENSE = "Expense - مصروف"
INCOME = "Income - دخل"
OWE = "I owe - عليّ"
OWED = "Owed to me - لي"
CASH = "Cash - نقدا"
VIA_BOT = "via Telegram bot"

# extra words -> start of the category / relation / help name in Settings
CAT_WORDS = {
    "food": "Food", "bread": "Food", "groceries": "Food", "market": "Food", "اكل": "Food", "خبز": "Food", "سوق": "Food",
    "rent": "Rent", "kira": "Rent", "كراء": "Rent",
    "sonelgaz": "Electricity", "electricity": "Electricity", "gaz": "Electricity", "gas": "Electricity", "كهرباء": "Electricity",
    "water": "Water", "eau": "Water", "ماء": "Water",
    "internet": "Internet", "phone": "Internet", "djezzy": "Internet", "mobilis": "Internet", "ooredoo": "Internet", "flexy": "Internet",
    "fuel": "Transport", "essence": "Transport", "taxi": "Transport", "bus": "Transport", "وقود": "Transport", "نقل": "Transport",
    "pharmacy": "Health", "doctor": "Health", "medicine": "Health", "دواء": "Health", "طبيب": "Health",
    "clothes": "Clothes", "ملابس": "Clothes",
    "home": "Home", "furniture": "Home", "اثاث": "Home",
    "gift": "Gifts", "هدية": "Gifts", "wedding": "Gifts",
    "sadaqa": "Charity", "zakat": "Charity", "charity": "Charity", "صدقة": "Charity", "زكاة": "Charity",
    "restaurant": "Outings", "cafe": "Outings", "outing": "Outings", "خرجة": "Outings",
    "school": "Education", "course": "Education", "book": "Education",
}
REL_WORDS = {"brother": "Brother", "اخي": "Brother", "أخي": "Brother", "sister": "Sister", "اختي": "Sister",
             "mom": "Mother", "mother": "Mother", "امي": "Mother", "أمي": "Mother", "dad": "Father", "father": "Father", "ابي": "Father",
             "mil": "Wife's mother", "wifemom": "Wife's mother", "wife's": "Wife's mother", "friend": "Friend", "cousin": "Cousin"}

log = logging.getLogger("finance_bot")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def amount(text: str) -> float:
    """'15000', '15,000', '15k', '1.5m' -> float"""
    t = text.lower().replace(",", "").replace(" ", "")
    mult = 1
    if t.endswith("k"):
        mult, t = 1_000, t[:-1]
    elif t.endswith("m"):
        mult, t = 1_000_000, t[:-1]
    return float(t) * mult


def parse_date(text: str) -> dt.date | None:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def as_date(v):
    if isinstance(v, dt.datetime):
        return v.date()
    return v if isinstance(v, dt.date) else None


def fmt(n, dec=0):
    return f"{n:,.{dec}f}"


def pick(word: str, items: list[str], extra: dict, default: str) -> str:
    """Find the list item that matches a word (English or Arabic part, or a known synonym)."""
    w = word.lower().strip()
    if not w:
        return default
    target = extra.get(w)
    for it in items:
        low = it.lower()
        if target and low.startswith(target.lower()):
            return it
    for it in items:
        if w in it.lower():
            return it
    return default


# ---------------------------------------------------------------------------
# workbook access
# ---------------------------------------------------------------------------
class Book:
    def __init__(self, path: Path):
        self.path = path
        self.wb = load_workbook(path)          # formulas are kept

    def save(self):
        self.wb.calculation.fullCalcOnLoad = True  # Excel recalculates everything on open
        self.wb.save(self.path)

    def ws(self, name):
        return self.wb[name]

    def named(self, name):
        dn = self.wb.defined_names[name]
        sheet, coord = next(iter(dn.destinations))
        return self.wb[sheet][coord.replace("$", "")].value

    def setting_num(self, name, default):
        v = num(self.named(name))
        return default if v is None else v

    def list_items(self, col: str) -> list[str]:
        ws = self.ws(SET)
        return [str(ws[f"{col}{r}"].value) for r in range(6, 31) if ws[f"{col}{r}"].value not in (None, "")]

    def next_row(self, sheet: str, key_col: str = "A") -> int:
        ws = self.ws(sheet)
        first, last = ROWS[sheet]
        for r in range(first, last + 1):
            if ws[f"{key_col}{r}"].value in (None, ""):
                return r
        raise RuntimeError(f"{sheet} is full (row {last}). Add rows in Excel. - الورقة ممتلئة")

    def write(self, sheet: str, row: int, values: dict):
        ws = self.ws(sheet)
        for c, v in values.items():
            ws[f"{c}{row}"].value = v

    # ---- numbers computed in Python (openpyxl does not calculate formulas) ----
    def rates(self):
        ws = self.ws(RATES)
        first, last = ROWS[RATES]
        out = []
        for r in range(first, last + 1):
            d, e = as_date(ws[f"A{r}"].value), num(ws[f"B{r}"].value)
            if d and e:
                out.append((d, r, e, num(ws[f"C{r}"].value), num(ws[f"D{r}"].value)))
        out.sort()
        return out

    def latest(self):
        rs = self.rates()
        if not rs:
            return None, 0.0, 0.0, 0.0
        d, _, eur, _, _ = rs[-1]
        prev = [x for x in rs if x[0] < d]
        usd_rows = [x for x in rs if x[4]]
        usd = usd_rows[-1][4] if usd_rows else eur * self.setting_num("USD_EUR_MANUAL", 0.9)
        return d, eur, (prev[-1][2] if prev else 0.0), usd

    def debts(self, eur_rate, usd_rate):
        paid = {}
        ws = self.ws(PAY)
        for r in range(ROWS[PAY][0], ROWS[PAY][1] + 1):
            b, c = ws[f"B{r}"].value, num(ws[f"C{r}"].value)
            if b and c:
                paid[str(b)[:4]] = paid.get(str(b)[:4], 0) + c
        ws = self.ws(DEBT)
        out = []
        for r in range(ROWS[DEBT][0], ROWS[DEBT][1] + 1):
            person = ws[f"C{r}"].value
            if not person:
                continue
            did = ws[f"A{r}"].value
            cur = ws[f"H{r}"].value or "DZD"
            amt = num(ws[f"G{r}"].value) or 0
            rem = amt - paid.get(did, 0)
            k = eur_rate if cur == "EUR" else usd_rate if cur == "USD" else 1
            out.append(dict(id=did, type=ws[f"B{r}"].value or "", person=person, cur=cur, rem=rem,
                            rem_dzd=rem * k, due=as_date(ws[f"I{r}"].value)))
        return out


LOCK = asyncio.Lock()


async def with_book(fn):
    """Open the workbook, run fn(book) and return its message. Serialised with a lock."""
    async with LOCK:
        try:
            book = Book(EXCEL_PATH)
            msg = fn(book)
            return msg
        except PermissionError:
            return "⚠ The Excel file is open. Close it and try again.\n⚠ ملف Excel مفتوح، أغلقه وأعد المحاولة."
        except FileNotFoundError:
            return f"⚠ File not found - الملف غير موجود: {EXCEL_PATH}"
        except (ValueError, IndexError) as e:
            return f"⚠ {e}\nType /help - اكتب /help"
        except RuntimeError as e:
            return f"⚠ {e}"


# ---------------------------------------------------------------------------
# command logic (pure functions of (book, args, user) -> reply text)
# ---------------------------------------------------------------------------
def do_rate(book: Book, args, user):
    if not args:
        raise ValueError("Example: /rate 277 279   (sell price, buy price)")
    vals = [amount(a) for a in args[:4]]
    r = book.next_row(RATES)
    row = {"A": dt.date.today(), "B": vals[0], "J": VIA_BOT}
    for c, v in zip("CDE", vals[1:]):
        row[c] = v
    book.write(RATES, r, row)
    book.save()
    return f"✔ Rate saved - تم حفظ السعر: 1 EUR = {fmt(vals[0], 2)} DZD ({dt.date.today():%d/%m/%Y})"


def do_sell(book: Book, args, user, currency="EUR"):
    if len(args) < 2:
        raise ValueError("Example: /sell 500 277 square")
    amt, rate = amount(args[0]), amount(args[1])
    r = book.next_row(EXC)
    book.write(EXC, r, {"A": dt.date.today(), "B": currency, "C": amt, "D": rate, "H": " ".join(args[2:]) or None, "I": VIA_BOT})
    book.save()
    return f"✔ Sold - تم البيع: {fmt(amt, 2)} {currency} × {fmt(rate, 2)} = {fmt(amt * rate)} DZD"


def do_spend(book: Book, args, user, income=False):
    if not args:
        raise ValueError("Example: /spend 2500 food bread")
    amt = amount(args[0])
    cats = book.list_items("F")
    cat = pick(args[1] if len(args) > 1 else "", cats, CAT_WORDS, cats[-1] if cats else None)
    desc = " ".join(args[2:] if len(args) > 2 else args[1:]) or None
    r = book.next_row(FAM)
    book.write(FAM, r, {"A": dt.date.today(), "B": INCOME if income else EXPENSE, "C": USER_NAMES.get(user, BOTH),
                        "D": None if income else cat, "E": desc, "F": amt, "G": CASH, "H": VIA_BOT})
    book.save()
    what = "Income - دخل" if income else f"Expense - مصروف ({cat})"
    return f"✔ {what}: {fmt(amt)} DZD"


def do_give(book: Book, args, user):
    if len(args) < 2:
        raise ValueError("Example: /give 15000 brother Ali")
    amt = amount(args[0])
    rels = book.list_items("J")
    rel = pick(args[1], rels, REL_WORDS, rels[-1] if rels else None)
    name = " ".join(args[2:]) or args[1]
    r = book.next_row(REL)
    book.write(REL, r, {"A": dt.date.today(), "B": name, "C": rel, "D": "Other - أخرى", "E": amt,
                        "F": USER_NAMES.get(user, BOTH), "G": VIA_BOT})
    book.save()
    return f"✔ Help saved - تم حفظ المساعدة: {fmt(amt)} DZD → {name} ({rel})"


def do_loan(book: Book, args, user, kind):
    if len(args) < 2:
        raise ValueError("Example: /lend 20000 Yacine 2026-12-31 EUR")
    amt = amount(args[0])
    rest = args[1:]
    cur = "DZD"
    if rest and rest[-1].upper() in ("DZD", "EUR", "USD"):
        cur = rest.pop().upper()
    due = parse_date(rest[-1]) if rest else None
    if due:
        rest = rest[:-1]
    person = " ".join(rest)
    r = book.next_row(DEBT, key_col="C")
    did = book.ws(DEBT)[f"A{r}"].value
    book.write(DEBT, r, {"B": kind, "C": person, "F": dt.date.today(), "G": amt, "H": cur, "I": due, "O": VIA_BOT})
    book.save()
    due_txt = f", return by - الإرجاع {due:%d/%m/%Y}" if due else ""
    return f"✔ {did} saved - تم الحفظ: {kind} | {person} | {fmt(amt, 2 if cur != 'DZD' else 0)} {cur}{due_txt}"


def do_pay(book: Book, args, user):
    if len(args) < 2:
        raise ValueError("Example: /pay D001 20000")
    did, amt = args[0].upper(), amount(args[1])
    ws = book.ws(DEBT)
    person = None
    for rr in range(ROWS[DEBT][0], ROWS[DEBT][1] + 1):
        if ws[f"A{rr}"].value == did:
            person = ws[f"C{rr}"].value
            break
    if not person:
        raise ValueError(f"Debt {did} not found or empty - الدين غير موجود")
    r = book.next_row(PAY)
    book.write(PAY, r, {"A": dt.date.today(), "B": f"{did} | {person}", "C": amt, "D": CASH, "E": VIA_BOT})
    book.save()
    return f"✔ Payment saved - تم حفظ الدفعة: {did} ({person}) {fmt(amt, 2)}"


def do_save(book: Book, args, user):
    if len(args) < 2:
        raise ValueError("Example: /save 50000 G01 [EUR]")
    amt, gid = amount(args[0]), args[1].upper()
    cur = args[2].upper() if len(args) > 2 and args[2].upper() in ("DZD", "EUR", "USD") else "DZD"
    ws = book.ws(PLAN)
    goal = None
    for rr in range(ROWS[PLAN][0], ROWS[PLAN][1] + 1):
        if ws[f"A{rr}"].value == gid:
            goal = ws[f"B{rr}"].value
            break
    if not goal:
        raise ValueError(f"Goal {gid} not found or empty - الهدف غير موجود")
    r = book.next_row(SAV)
    book.write(SAV, r, {"A": dt.date.today(), "B": f"{gid} | {goal}", "C": amt, "D": cur,
                        "E": USER_NAMES.get(user, BOTH), "G": VIA_BOT})
    book.save()
    return f"✔ Saved for - تم الادخار لـ {goal}: {fmt(amt, 2 if cur != 'DZD' else 0)} {cur}"


def do_summary(book: Book, args, user):
    d, eur, prev, usd = book.latest()
    usd_eur = book.setting_num("USD_EUR_MANUAL", 0.909)
    fee = book.setting_num("BANK_FEE", 0)
    salary_usd = book.setting_num("SALARY_USD", 2700)
    salary_eur = salary_usd * usd_eur * (1 - fee)
    today = dt.date.today()
    m0 = today.replace(day=1)
    # EUR balance = salary EUR received - EUR sold
    ws = book.ws(SAL)
    received = 0.0
    for r in range(ROWS[SAL][0], ROWS[SAL][1] + 1):
        if not as_date(ws[f"A{r}"].value):
            continue
        actual = num(ws[f"F{r}"].value)
        if actual is not None:
            received += actual
        else:
            b = num(ws[f"B{r}"].value) or salary_usd
            c = num(ws[f"C{r}"].value) or usd_eur
            received += b * c * (1 - fee) - (num(ws[f"D{r}"].value) or 0)
    ws = book.ws(EXC)
    sold = sum(num(ws[f"C{r}"].value) or 0 for r in range(ROWS[EXC][0], ROWS[EXC][1] + 1)
               if ws[f"B{r}"].value != "USD" and as_date(ws[f"A{r}"].value))
    ws = book.ws(FAM)
    spent = sum(num(ws[f"F{r}"].value) or 0 for r in range(ROWS[FAM][0], ROWS[FAM][1] + 1)
                if (as_date(ws[f"A{r}"].value) or dt.date.min) >= m0 and ws[f"B{r}"].value != INCOME)
    ws = book.ws(REL)
    helped = sum(num(ws[f"E{r}"].value) or 0 for r in range(ROWS[REL][0], ROWS[REL][1] + 1)
                 if (as_date(ws[f"A{r}"].value) or dt.date.min) >= m0)
    debts = book.debts(eur, usd)
    owe = sum(x["rem_dzd"] for x in debts if x["type"] == OWE)
    owed = sum(x["rem_dzd"] for x in debts if x["type"] == OWED)
    ws = book.ws(SAV)
    saved = 0.0
    for r in range(ROWS[SAV][0], ROWS[SAV][1] + 1):
        c = num(ws[f"C{r}"].value)
        if c:
            cur = ws[f"D{r}"].value
            saved += c * (eur if cur == "EUR" else usd if cur == "USD" else 1)
    change = f"{eur - prev:+.2f}" if prev else "—"
    return "\n".join([
        f"📊 Summary - الملخص  ({today:%d/%m/%Y})",
        f"💱 EUR square - الأورو: {fmt(eur, 2)} DZD  ({change})  · {d:%d/%m}" if d else "💱 No rate yet - لا يوجد سعر بعد (/rate 277)",
        f"💵 Salary - الراتب: {fmt(salary_usd)} $ → {fmt(salary_eur, 2)} € → {fmt(salary_eur * eur)} DZD",
        f"🏦 EUR in bank - الأورو في البنك: {fmt(received - sold, 2)} € ≈ {fmt((received - sold) * eur)} DZD",
        f"👨‍👩 Spent this month - مصاريف الشهر: {fmt(spent)} DZD",
        f"🏡 Help to relatives - مساعدة الأقارب: {fmt(helped)} DZD",
        f"🤝 I owe - عليّ: {fmt(owe)} DZD   |   Owed to me - لي: {fmt(owed)} DZD",
        f"🎯 Savings - المدخرات: {fmt(saved)} DZD",
    ])


def do_debts(book: Book, args, user):
    _, eur, _, usd = book.latest()
    today = dt.date.today()
    open_ = [x for x in book.debts(eur, usd) if x["rem"] > 0]
    if not open_:
        return "✔ No open debts - لا توجد ديون مفتوحة"
    open_.sort(key=lambda x: x["due"] or dt.date.max)
    lines = ["🤝 Open debts - الديون المفتوحة"]
    for x in open_:
        flag = ""
        if x["due"]:
            days = (x["due"] - today).days
            flag = f" ⚠ {-days}d late - متأخر" if days < 0 else f" · {days}d"
        arrow = "→ I owe - عليّ" if x["type"] == OWE else "← owed to me - لي"
        due = f"{x['due']:%d/%m/%Y}" if x["due"] else "-"
        lines.append(f"{x['id']} {arrow} {x['person']}: {fmt(x['rem'], 2 if x['cur'] != 'DZD' else 0)} {x['cur']} · {due}{flag}")
    return "\n".join(lines)


HELP = """🤖 Finance bot - بوت المالية
/rate 277 279 — EUR price today (sell, buy) - سعر الأورو اليوم
/sell 500 277 square — sold 500 EUR at 277 - بعت 500 أورو
/sellusd 100 241 — sold USD - بعت دولار
/spend 2500 food bread — expense - مصروف
/income 10000 gift — extra income - دخل
/give 15000 brother Ali — help a relative - مساعدة قريب
/lend 20000 Yacine 2026-12-31 [EUR] — I lent - سلّفت
/borrow 50000 Karim 2026-12-15 — I borrowed - تسلفت
/pay D001 20000 — repayment - تسديد
/save 50000 G01 [EUR] — savings for a goal - ادخار
/summary — totals - الملخص
/debts — open debts - الديون
Amounts: 15000, 15,000 or 15k"""


# ---------------------------------------------------------------------------
# Telegram wiring
# ---------------------------------------------------------------------------
def main():
    from telegram import Update
    from telegram.ext import Application, CommandHandler, ContextTypes

    if not BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN (from @BotFather). - ضع رمز البوت")
    if not ALLOWED:
        log.warning("ALLOWED_USER_IDS is empty: the bot will refuse everyone and tell them their id.")

    def handler(fn, *extra):
        async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else 0
            if uid not in ALLOWED:
                await update.message.reply_text(f"⛔ Not allowed. Your Telegram id is {uid}. Add it to ALLOWED_USER_IDS.")
                return
            msg = await with_book(lambda book: fn(book, context.args or [], uid, *extra))
            await update.message.reply_text(msg)
        return run

    async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(HELP)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["start", "help"], help_cmd))
    app.add_handler(CommandHandler("rate", handler(do_rate)))
    app.add_handler(CommandHandler("sell", handler(do_sell)))
    app.add_handler(CommandHandler("sellusd", handler(do_sell, "USD")))
    app.add_handler(CommandHandler("spend", handler(do_spend)))
    app.add_handler(CommandHandler("income", handler(do_spend, True)))
    app.add_handler(CommandHandler("give", handler(do_give)))
    app.add_handler(CommandHandler("lend", handler(do_loan, OWED)))
    app.add_handler(CommandHandler("borrow", handler(do_loan, OWE)))
    app.add_handler(CommandHandler("pay", handler(do_pay)))
    app.add_handler(CommandHandler("save", handler(do_save)))
    app.add_handler(CommandHandler("summary", handler(do_summary)))
    app.add_handler(CommandHandler("debts", handler(do_debts)))
    log.info("Bot running. Workbook: %s", EXCEL_PATH)
    app.run_polling()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
