#!/usr/bin/env python3
"""Build the bilingual (English / Arabic) personal finance workbook.

Usage:  python build_workbook.py [output.xlsx]

Every number shown in the workbook is a live Excel formula; this script only
lays out the sheets, formulas, dropdowns, formatting, charts and a few
example rows (marked "Example - مثال") that the user deletes.
"""
import datetime as dt
import sys

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.axis import DateAxis
from openpyxl.chart.series import SeriesLabel
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter, column_index_from_string
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink

OUT = sys.argv[1] if len(sys.argv) > 1 else "Personal_Finance_Aboubakr_Bouchra.xlsx"

# --------------------------------------------------------------------------
# Look & feel
# --------------------------------------------------------------------------
FONT = "Arial"
NAVY = "1F3A5F"      # input column headers / titles
TEAL = "2F6F5E"      # automatic column headers
GOLD = "B7791F"
RED = "C62828"
GREEN = "2E7D32"
ORANGE = "E65100"
BLUE_IN = "0000FF"   # typed inputs
GRAY_TXT = "666666"
AUTO_FILL = "F2F4F7"
CARD_FILL = "F7F9FC"
YELLOW = "FFF59D"
LIGHT_NAVY = "DCE6F1"

thin = Side(style="thin", color="D0D5DD")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

FMT_DATE = "dd/mm/yyyy"
FMT_MONTH = "mmm yyyy"
FMT_DZD = '#,##0;[Red]-#,##0;"-"'
FMT_DZD_U = '#,##0 "DZD";[Red]-#,##0 "DZD";"-"'
FMT_EUR = '#,##0.00;[Red]-#,##0.00;"-"'
FMT_EUR_U = '#,##0.00 "€";[Red]-#,##0.00 "€";"-"'
FMT_USD_U = '#,##0 "$";[Red]-#,##0 "$";"-"'
FMT_RATE = '#,##0.00'
FMT_RATE4 = '0.0000'
FMT_PCT = '0.0%;[Red]-0.0%;"-"'
FMT_CHG = '▲ #,##0.00;▼ #,##0.00;"="'
FMT_CHGP = '▲ 0.00%;▼ 0.00%;"="'


def color_change(ws, rng):
    """Green when up, red when down (conditional formatting works in Excel and Google Sheets)."""
    tl = rng.split(":")[0].replace("$", "")
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}>0)"], font=Font(color=GREEN, bold=True)))
    ws.conditional_formatting.add(rng, FormulaRule(formula=[f"AND(ISNUMBER({tl}),{tl}<0)"], font=Font(color=RED, bold=True)))
FMT_INT = '#,##0;[Red]-#,##0;"0"'


def fnt(size=10, bold=False, color="000000", italic=False, underline=None):
    return Font(name=FONT, size=size, bold=bold, color=color, italic=italic, underline=underline)


def fill(color):
    return PatternFill("solid", start_color=color, end_color=color)


def col(c):
    return c if isinstance(c, int) else column_index_from_string(c)


def L(c):
    return get_column_letter(c) if isinstance(c, int) else c


# --------------------------------------------------------------------------
# Sheet names
# --------------------------------------------------------------------------
DASH = "Dashboard - الرئيسية"
RATES = "Rates - الأسعار"
SAL = "Salary - الراتب"
EXC = "Exchange - الصرف"
DEBT = "Debts - الديون"
PAY = "Payments - التسديد"
FAM = "Family - العائلة"
BUD = "Budget - الميزانية"
REL = "Relatives - الأقارب"
PLAN = "Plans - الخطط"
SAV = "Savings - الادخار"
SUMM = "Summary - الملخص"
ZAK = "Zakat - الزكاة"
SET = "Settings - الإعدادات"
GUIDE = "Guide - الدليل"

ORDER = [DASH, RATES, SAL, EXC, DEBT, PAY, FAM, BUD, REL, PLAN, SAV, SUMM, ZAK, SET, GUIDE]
TAB = {DASH: NAVY, RATES: GREEN, SAL: GREEN, EXC: GREEN, DEBT: RED, PAY: RED,
       FAM: "6A1B9A", BUD: "6A1B9A", REL: "6A1B9A", PLAN: "1565C0", SAV: "1565C0",
       SUMM: NAVY, ZAK: GOLD, SET: "616161", GUIDE: "616161"}


def q(sheet):
    return f"'{sheet}'!"


# data row ranges (first row, last row) for every log sheet
ROWS = {RATES: (6, 405), SAL: (6, 65), EXC: (6, 305), DEBT: (6, 155), PAY: (6, 505),
        FAM: (6, 1505), REL: (6, 405), PLAN: (6, 35), SAV: (6, 505)}

wb = Workbook()
wb.remove(wb.active)
WS = {}
for name in ORDER:
    ws = wb.create_sheet(name)
    ws.sheet_properties.tabColor = TAB[name]
    ws.sheet_view.zoomScale = 90
    WS[name] = ws


def define(name, sheet, rng):
    """Workbook-level defined name pointing at an absolute range."""
    parts = rng.split(":")
    absr = ":".join("$" + "".join(ch for ch in p if ch.isalpha()) + "$" + "".join(ch for ch in p if ch.isdigit()) for p in parts)
    wb.defined_names[name] = DefinedName(name, attr_text=q(sheet) + absr)


def define_formula(name, text):
    wb.defined_names[name] = DefinedName(name, attr_text=text)


# --------------------------------------------------------------------------
# Generic helpers
# --------------------------------------------------------------------------
def put(ws, coord, value=None, font=None, fill_=None, fmt=None, align=None, border=None):
    c = ws[coord]
    if value is not None:
        c.value = value
    c.font = font or fnt()
    if fill_:
        c.fill = fill(fill_)
    if fmt:
        c.number_format = fmt
    if align:
        c.alignment = align
    if border:
        c.border = border
    return c


def link(ws, coord, target_sheet, text, size=10, bold=True):
    c = ws[coord]
    c.value = text
    c.hyperlink = Hyperlink(ref=coord, location=f"'{target_sheet}'!A1", display=text)
    c.font = fnt(size, bold, "1565C0", underline="single")
    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return c


def title(ws, text, subtitle, last_col, back=True):
    lc = L(last_col)
    ws.merge_cells(f"A1:{lc}1")
    put(ws, "A1", text, fnt(16, True, "FFFFFF"), NAVY, align=Alignment(horizontal="left", vertical="center", indent=1))
    ws.row_dimensions[1].height = 34
    ws.merge_cells(f"A2:{lc}2")
    put(ws, "A2", subtitle, fnt(9, False, GRAY_TXT, italic=True),
        align=Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1))
    ws.row_dimensions[2].height = 30
    if back:
        link(ws, "A3", DASH, "← Dashboard\nالرئيسية", 9)
    ws.row_dimensions[3].height = 32


def chips(ws, row, start_col, items, step=3):
    """Small label/value pairs on the row above the table (label, formula, fmt)."""
    c = col(start_col)
    for label, formula, fmt in items:
        put(ws, f"{L(c)}{row}", label, fnt(8, True, GRAY_TXT),
            align=Alignment(horizontal="right", vertical="center", wrap_text=True))
        put(ws, f"{L(c + 1)}{row}", formula, fnt(11, True, NAVY), LIGHT_NAVY, fmt,
            Alignment(horizontal="center", vertical="center"), BORDER)
        c += step


def comment(ws, coord, text, w=320, h=110):
    cm = Comment(text, "Finance")
    cm.width, cm.height = w, h
    ws[coord].comment = cm


LIST_SRC = {}   # list name -> direct range (works in Excel and Google Sheets)


def dv_list(ws, rng, listname, strict=False, prompt=None):
    dv = DataValidation(type="list", formula1=LIST_SRC[listname], allow_blank=True)
    dv.showErrorMessage = True
    dv.errorStyle = "stop" if strict else "warning"
    dv.errorTitle = "Choose from the list - اختر من القائمة"
    dv.error = "Please choose a value from the dropdown list.\nاختر قيمة من القائمة المنسدلة."
    if prompt:
        dv.promptTitle, dv.prompt, dv.showInputMessage = "Tip - نصيحة", prompt, True
    ws.add_data_validation(dv)
    dv.add(rng)


def dv_date(ws, rng):
    dv = DataValidation(type="date", operator="between", formula1="36526", formula2="73415", allow_blank=True)
    dv.showErrorMessage = True
    dv.errorStyle = "stop"
    dv.errorTitle = "Date - تاريخ"
    dv.error = "Type a date like 27/11/2026.\nاكتب تاريخا مثل 27/11/2026."
    ws.add_data_validation(dv)
    dv.add(rng)


def dv_number(ws, rng, minimum=0, negative_ok=False):
    if negative_ok:
        dv = DataValidation(type="decimal", operator="between", formula1="-1000000000000", formula2="1000000000000", allow_blank=True)
    else:
        dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1=str(minimum), allow_blank=True)
    dv.showErrorMessage = True
    dv.errorStyle = "stop"
    dv.errorTitle = "Number - رقم"
    dv.error = "Type a number only (no letters).\nاكتب رقما فقط."
    ws.add_data_validation(dv)
    dv.add(rng)


def build_log(ws, sheet, cols, title_text, subtitle, totals=None, examples=None):
    """A log table: header row 5, data rows from ROWS[sheet].

    cols: list of dicts with keys
      c (letter), en, ar, w (width), kind ('in' | 'auto' | 'id' | 'hidden'),
      fmt, f (formula template with {r}), dv (callable(ws, rng)), tip (header comment)
    """
    first, last = ROWS[sheet]
    visible_last = max(col(x["c"]) for x in cols if x["kind"] != "hidden")
    title(ws, title_text, subtitle, visible_last)
    ws.row_dimensions[5].height = 44
    for x in cols:
        c = x["c"]
        ws.column_dimensions[c].width = x.get("w", 12)
        hdr_color = NAVY if x["kind"] == "in" else TEAL
        mark = "" if x["kind"] == "in" else "⚙ "
        put(ws, f"{c}5", f"{mark}{x['en']}\n{x['ar']}", fnt(9, True, "FFFFFF"), hdr_color,
            align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
        if x.get("tip"):
            comment(ws, f"{c}5", x["tip"])
        if x["kind"] == "hidden":
            ws.column_dimensions[c].hidden = True
        for r in range(first, last + 1):
            cell = ws[f"{c}{r}"]
            if x.get("f"):
                cell.value = x["f"].replace("{r}", str(r))
            if x["kind"] == "id":
                cell.value = x["id"](r - first + 1)
                cell.font = fnt(9, True, GRAY_TXT)
                cell.fill = fill(AUTO_FILL)
                cell.alignment = Alignment(horizontal="center")
            elif x["kind"] == "in":
                cell.font = fnt(10, False, BLUE_IN)
            else:
                cell.font = fnt(10)
                cell.fill = fill(AUTO_FILL)
            cell.border = BORDER
            if x.get("fmt"):
                cell.number_format = x["fmt"]
            if x.get("align"):
                cell.alignment = x["align"]
        if x.get("dv"):
            x["dv"](ws, f"{c}{first}:{c}{last}")
    # totals row 4
    if totals:
        put(ws, "A4", "Total - المجموع", fnt(9, True, NAVY), LIGHT_NAVY,
            align=Alignment(horizontal="center", vertical="center"), border=BORDER)
        for c, (f, fmt) in totals.items():
            put(ws, f"{c}4", f.replace("{first}", str(first)).replace("{last}", str(last)),
                fnt(10, True, NAVY), LIGHT_NAVY, fmt, Alignment(horizontal="center"), BORDER)
        comment(ws, "A4", "Totals follow the filter: filter a column (arrow in the header) and the totals show only the visible rows.\n"
                          "المجموع يتبع الفلتر: إذا فلترت عمودا يظهر مجموع الصفوف الظاهرة فقط.")
    ws.freeze_panes = f"B{first}"
    ws.auto_filter.ref = f"A5:{L(visible_last)}{last}"
    if examples:
        for i, row in enumerate(examples):
            for c, v in row.items():
                ws[f"{c}{first + i}"].value = v
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = "5:5"


EX = "Example - مثال (delete / احذف)"

# ==========================================================================
# SETTINGS
# ==========================================================================
ws = WS[SET]
title(ws, "⚙ Settings - الإعدادات",
      "Change only the blue / yellow cells. Gray cells are automatic.  |  غيّر الخلايا الزرقاء والصفراء فقط، الخلايا الرمادية تلقائية.", 16)
ws.column_dimensions["A"].width = 46
ws.column_dimensions["B"].width = 20
ws.column_dimensions["C"].width = 58
ws.column_dimensions["D"].width = 3

ECB = ('=IFERROR(1/_xlfn.FILTERXML(_xlfn.WEBSERVICE("https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"),'
       '"//*[@currency=\'USD\']/@rate"),"n/a")')
RB = q(RATES)
settings_rows = [
    ("§", "Profile & salary - الملف والراتب"),
    ("NAME_ME", "Your name - اسمك", "Aboubakr - أبوبكر", "in", None, "Used in the 'Who' dropdowns. - يظهر في قوائم 'من'"),
    ("NAME_WIFE", "Wife's name - اسم الزوجة", "Bouchra - بشرى", "in", None, ""),
    ("SALARY_USD", "Monthly salary (USD) - الراتب الشهري (دولار)", 2700, "in", FMT_USD_U,
     "From you: 2,700 USD, paid in EUR to your euro bank account. - من عندك"),
    ("USD_EUR_MANUAL", "USD → EUR rate, manual - سعر تحويل الدولار ← أورو (يدوي)", 0.909, "in", FMT_RATE4,
     "≈1.10 USD per EUR in mid-Nov 2026 (Trading Economics), so 1 USD ≈ 0.909 EUR. Used when no automatic rate is available."),
    ("OFFICIAL_EUR_MANUAL", "Official EUR → DZD, manual - السعر الرسمي للأورو (يدوي)", 151, "in", FMT_RATE,
     "≈151 DZD per EUR on 16 Nov 2026 (Bank of Algeria, via Observalgerie). Used when no automatic rate is available."),
    ("USE_LIVE", "Use automatic rates when available? - استعمال الأسعار التلقائية؟", "Yes - نعم", "key", None,
     "Yes = automatic official rates (Google Sheets / Excel Windows). No = always the manual numbers above."),
    ("USD_EUR_GOOGLE", "USD → EUR, automatic in Google Sheets - تلقائي في Google Sheets",
     '=IFERROR(GOOGLEFINANCE("CURRENCY:USDEUR"),"n/a")', "auto", FMT_RATE4,
     "Updates by itself on Google's servers (phone or browser, laptop off). Shows n/a in Excel - يظهر n/a في Excel"),
    ("USD_EUR_LIVE", "USD → EUR, automatic in Excel for Windows - تلقائي في Excel ويندوز", ECB, "auto", FMT_RATE4,
     "European Central Bank rate, Excel 2013+ on Windows (WEBSERVICE). Shows n/a on phone, Mac and Google Sheets."),
    ("OFFICIAL_EUR_GOOGLE", "Official EUR → DZD, automatic in Google Sheets - الرسمي تلقائي",
     '=IFERROR(GOOGLEFINANCE("CURRENCY:EURDZD"),"n/a")', "auto", FMT_RATE, "Google Sheets only - في Google Sheets فقط"),
    ("USD_EUR", "USD → EUR rate USED - سعر التحويل المستعمل",
     '=IF(LEFT(USE_LIVE,3)="Yes",IF(ISNUMBER(USD_EUR_GOOGLE),USD_EUR_GOOGLE,IF(ISNUMBER(USD_EUR_LIVE),USD_EUR_LIVE,USD_EUR_MANUAL)),USD_EUR_MANUAL)',
     "auto", FMT_RATE4, "Automatic rate if available, otherwise the manual one."),
    ("OFFICIAL_EUR", "Official EUR → DZD USED - السعر الرسمي المستعمل",
     '=IF(AND(LEFT(USE_LIVE,3)="Yes",ISNUMBER(OFFICIAL_EUR_GOOGLE)),OFFICIAL_EUR_GOOGLE,OFFICIAL_EUR_MANUAL)', "auto", FMT_RATE, ""),
    ("BANK_FEE", "Bank conversion fee (%) - عمولة البنك على التحويل", 0, "in", "0.00%",
     "If your bank keeps e.g. 1% when converting USD→EUR, type 1%. - إذا كان البنك يأخذ عمولة"),
    ("DUE_SOON_DAYS", "'Due soon' alert for debts (days) - تنبيه الديون قبل (أيام)", 7, "in", "0", ""),
    ("§", "Market numbers (automatic) - أرقام السوق (تلقائي)"),
    ("RATE_DATE", "Last rate date - تاريخ آخر سعر", '=SUMPRODUCT(MAX((R_EUR<>"")*R_DATE))', "auto", FMT_DATE, "Newest date in Rates that has a EUR price."),
    ("RATE_ROW", "(helper) row of last rate", '=SUMPRODUCT(MAX((R_DATE=RATE_DATE)*(R_EUR<>"")*ROW(R_DATE)))', "auto", "0", ""),
    ("RATE_EUR", "EUR → DZD now (you sell) - سعر بيع الأورو الآن", f"=IF(RATE_ROW=0,0,INDEX({RB}$B:$B,RATE_ROW))", "auto", FMT_RATE,
     "This one number updates the whole workbook (salary, EUR in bank, debts, savings, zakat)."),
    ("RATE_EUR_BUY", "EUR price now (you buy) - سعر شراء الأورو الآن",
     f"=IF(RATE_ROW=0,0,IF(N(INDEX({RB}$C:$C,RATE_ROW))=0,RATE_EUR,INDEX({RB}$C:$C,RATE_ROW)))", "auto", FMT_RATE, ""),
    ("PREV_DATE", "Previous day with a rate - اليوم السابق", '=SUMPRODUCT(MAX((R_DATE<RATE_DATE)*(R_EUR<>"")*R_DATE))', "auto", FMT_DATE, ""),
    ("PREV_ROW", "(helper) row of previous rate", '=SUMPRODUCT(MAX((R_DATE=PREV_DATE)*(PREV_DATE>0)*(R_EUR<>"")*ROW(R_DATE)))', "auto", "0", ""),
    ("RATE_EUR_PREV", "Previous day EUR rate - سعر اليوم السابق", f"=IF(PREV_ROW=0,0,INDEX({RB}$B:$B,PREV_ROW))", "auto", FMT_RATE, ""),
    ("USD_DATE", "(helper) last USD date", '=SUMPRODUCT(MAX((R_USD<>"")*R_DATE))', "auto", FMT_DATE, ""),
    ("USD_ROW", "(helper) row of last USD rate", '=SUMPRODUCT(MAX((R_DATE=USD_DATE)*(R_USD<>"")*ROW(R_DATE)))', "auto", "0", ""),
    ("RATE_USD", "USD → DZD now (you sell) - سعر بيع الدولار الآن",
     f"=IF(USD_ROW=0,RATE_EUR*USD_EUR,INDEX({RB}$D:$D,USD_ROW))", "auto", FMT_RATE,
     "From Rates column D. If you never typed a USD price, it is estimated from the EUR price."),
    ("RATE_FIRST_DATE", "(helper) first rate date", '=SUMPRODUCT(MIN(R_DATE+((R_EUR="")+(R_DATE=""))*1000000))', "auto", FMT_DATE, ""),
    ("SALARY_EUR", "Salary in EUR (estimate) - الراتب بالأورو (تقديري)", "=SALARY_USD*USD_EUR*(1-BANK_FEE)", "auto", FMT_EUR_U, ""),
    ("SALARY_DZD", "Salary in DZD at today's square rate - الراتب بالدينار", "=SALARY_EUR*RATE_EUR", "auto", FMT_DZD_U, ""),
    ("PREMIUM", "Square premium vs official - فرق السكوار عن الرسمي", "=IF(OFFICIAL_EUR>0,RATE_EUR/OFFICIAL_EUR-1,0)", "auto", FMT_PCT, ""),
    ("EUR_BALANCE", "EUR still in bank (received − sold) - الأورو المتبقي في البنك", '=SUM(S_EUR)-SUMIFS(E_AMT,E_CUR,"<>USD")', "auto", FMT_EUR_U,
     "Salary EUR received (Salary sheet) minus EUR sold (Exchange sheet)."),
    ("I_OWE_DZD", "Total I owe (DZD) - مجموع ما عليّ", "=SUMIFS(D_REMDZD,D_TYPE,DT_OWE)", "auto", FMT_DZD_U, ""),
    ("OWED_ME_DZD", "Total owed to me (DZD) - مجموع ما لي عند الناس", "=SUMIFS(D_REMDZD,D_TYPE,DT_OWED)", "auto", FMT_DZD_U, ""),
    ("SAVINGS_DZD", "Total savings for goals (DZD) - مجموع المدخرات", "=SUM(SV_DZD)", "auto", FMT_DZD_U, ""),
    ("GOALS_TARGET", "Total of all goals (DZD) - مجموع الأهداف", "=SUM(G_TARGET)", "auto", FMT_DZD_U, ""),
    ("SEL_MONTH_END", "(helper) first day after selected month", "=DATE(YEAR(SEL_MONTH),MONTH(SEL_MONTH)+1,1)", "auto", FMT_DATE, ""),
]
r = 5
for item in settings_rows:
    if item[0] == "§":
        if r > 5:
            r += 1
        ws.merge_cells(f"A{r}:C{r}")
        put(ws, f"A{r}", item[1], fnt(11, True, "FFFFFF"), TEAL, align=Alignment(vertical="center", indent=1))
        ws.row_dimensions[r].height = 22
        r += 1
        continue
    nm, label, val, kind, fmt, note = item
    put(ws, f"A{r}", label, fnt(10, kind != "auto"), border=BORDER, align=Alignment(vertical="center", wrap_text=True))
    if kind == "in":
        put(ws, f"B{r}", val, fnt(10, True, BLUE_IN), "FFFFFF", fmt, Alignment(horizontal="center"), BORDER)
    elif kind == "key":
        put(ws, f"B{r}", val, fnt(10, True, BLUE_IN), YELLOW, fmt, Alignment(horizontal="center"), BORDER)
    else:
        put(ws, f"B{r}", val, fnt(10), AUTO_FILL, fmt, Alignment(horizontal="center"), BORDER)
    put(ws, f"C{r}", note, fnt(8, False, GRAY_TXT, italic=True), align=Alignment(vertical="center", wrap_text=True))
    define(nm, SET, f"B{r}")
    r += 1
ws["B8"].fill = fill(YELLOW)   # salary = key input
ws.freeze_panes = "A5"

# ---- Lists (columns E..P) ----
LISTS = [
    ("E", "LIST_WHO", "Who - من", ["=NAME_ME", "=NAME_WIFE", "Both - مشترك"]),
    ("F", "LIST_CAT", "Expense categories - فئات المصاريف", [
        "Food & groceries - المواد الغذائية", "Rent - الكراء", "Electricity & gas - الكهرباء والغاز", "Water - الماء",
        "Internet & phone - الأنترنت والهاتف", "Transport & fuel - النقل والوقود", "Health & pharmacy - الصحة والدواء",
        "Clothes - الملابس", "Home & furniture - المنزل والأثاث", "Personal Aboubakr - مصاريف أبوبكر",
        "Personal Bouchra - مصاريف بشرى", "Gifts & occasions - الهدايا والمناسبات", "Charity & zakat - الصدقة والزكاة",
        "Outings & fun - الخرجات والترفيه", "Education & courses - التعليم والدورات", "Other - أخرى"]),
    ("G", "LIST_PAY", "Payment method - طريقة الدفع", [
        "Cash - نقدا", "BaridiMob / CCP - بريدي موب", "Edahabia card - البطاقة الذهبية", "Bank card - بطاقة بنكية",
        "Bank transfer - تحويل بنكي", "Other - أخرى"]),
    ("H", "LIST_CUR", "Currency - العملة", ["DZD", "EUR", "USD"]),
    ("I", "LIST_DEBTTYPE", "Debt type - نوع الدين", ["I owe - عليّ", "Owed to me - لي"]),
    ("J", "LIST_REL", "Relation - القرابة", [
        "Brother - أخ", "Sister - أخت", "Mother - الأم", "Father - الأب", "Wife's mother - أم الزوجة",
        "Wife's father - أب الزوجة", "Wife's brother - أخ الزوجة", "Wife's sister - أخت الزوجة",
        "Uncle / aunt - عم / خال", "Cousin - ابن العم / الخال", "Friend - صديق", "Neighbor - جار",
        "Colleague - زميل", "Other - أخرى"]),
    ("K", "LIST_HELP", "Help type - نوع المساعدة", [
        "Monthly support - مصروف شهري", "Gift - هدية", "Medical - علاج", "Eid / occasion - عيد / مناسبة",
        "Wedding - عرس", "Emergency - طارئ", "Bills - فواتير", "Other - أخرى"]),
    ("L", "LIST_GOALCAT", "Goal category - نوع الهدف", [
        "Emergency fund - صندوق الطوارئ", "House - السكن", "Car - السيارة", "Hajj / Umrah - الحج / العمرة",
        "Children - الأطفال", "Education - التعليم", "Travel - السفر", "Business / project - مشروع",
        "Furniture - الأثاث", "Gold - الذهب", "Wedding - العرس", "Other - أخرى"]),
    ("M", "LIST_PRIO", "Priority - الأولوية", ["High - عالية", "Medium - متوسطة", "Low - منخفضة"]),
    ("N", "LIST_TYPE", "Entry type - نوع العملية", ["Expense - مصروف", "Income - دخل"]),
    ("O", "LIST_YESNO", "Yes / No - نعم / لا", ["Yes - نعم", "No - لا"]),
    ("P", "LIST_KEPT", "Where kept - أين المال", [
        "Cash DZD - نقدا", "EUR bank - حساب الأورو", "CCP / bank DZD - الحساب البريدي", "Gold - ذهب", "Other - أخرى"]),
]
put(ws, "E4", "Dropdown lists — add new items at the bottom of a list (max 25).  |  القوائم المنسدلة — أضف عناصر جديدة في الأسفل",
    fnt(9, True, TEAL))
for c, nm, hdr, items in LISTS:
    ws.column_dimensions[c].width = 26 if c not in ("H", "M", "O") else 14
    put(ws, f"{c}5", hdr, fnt(9, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
    for i in range(25):
        cell = put(ws, f"{c}{6 + i}", items[i] if i < len(items) else None, fnt(9, False, BLUE_IN), border=BORDER)
    LIST_SRC[nm] = f"{q(SET)}${c}$6:${c}$30"
    define(nm, SET, f"{c}6:{c}30")
ws.row_dimensions[5].height = 30
define("WHO_ME", SET, "E6")
define("WHO_WIFE", SET, "E7")
define("DT_OWE", SET, "I6")
define("DT_OWED", SET, "I7")
define("TYPE_INCOME", SET, "N7")
dv_list(ws, "B11", "LIST_YESNO", strict=True)

# ==========================================================================
# RATES
# ==========================================================================
ws = WS[RATES]
f6, l6 = ROWS[RATES]
for nm, c in (("R_DATE", "A"), ("R_EUR", "B"), ("R_EURBUY", "C"), ("R_USD", "D")):
    define(nm, RATES, f"{c}{f6}:{c}{l6}")
rng = lambda c: f"${c}${f6}:${c}${l6}"
rate_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date,
         tip="One line per day (or more). Order does not matter.\nسطر لكل يوم، الترتيب غير مهم."),
    dict(c="B", en="EUR → DZD\n(you sell)", ar="بيع الأورو", w=13, kind="in", fmt=FMT_RATE, dv=dv_number,
         tip="Price the trader PAYS you for 1 EUR at the square (achat). This is the main number.\nالسعر الذي يدفعه لك الصراف مقابل 1 أورو. هذا هو الرقم الأساسي."),
    dict(c="C", en="EUR price\n(you buy)", ar="شراء الأورو", w=12, kind="in", fmt=FMT_RATE, dv=dv_number,
         tip="Optional. Price to BUY 1 EUR (vente).\nاختياري: سعر شراء 1 أورو."),
    dict(c="D", en="USD → DZD\n(you sell)", ar="بيع الدولار", w=12, kind="in", fmt=FMT_RATE, dv=dv_number, tip="Optional - اختياري"),
    dict(c="E", en="USD price\n(you buy)", ar="شراء الدولار", w=12, kind="in", fmt=FMT_RATE, dv=dv_number, tip="Optional - اختياري"),
    dict(c="F", en="Official EUR\n(bank)", ar="الرسمي (البنك)", w=12, kind="in", fmt=FMT_RATE, dv=dv_number,
         tip="Optional. If empty, Settings → official rate is used.\nاختياري."),
    dict(c="G", en="Change vs\nprevious day", ar="التغير عن الأمس", w=13, kind="auto", fmt=FMT_CHG,
         f='=IF(OR($A{r}="",$B{r}="",N($L{r})=0),"",$B{r}-INDEX(' + rng("B") + ',MATCH($L{r},' + rng("A") + ',0)))'),
    dict(c="H", en="Change %", ar="نسبة التغير", w=11, kind="auto", fmt=FMT_CHGP,
         f='=IF($G{r}="","",$G{r}/($B{r}-$G{r}))'),
    dict(c="I", en="Square vs\nofficial", ar="الفرق مع الرسمي", w=11, kind="auto", fmt=FMT_PCT,
         f='=IF($B{r}="","",IF(N($F{r})>0,$B{r}/$F{r}-1,IF(OFFICIAL_EUR>0,$B{r}/OFFICIAL_EUR-1,"")))'),
    dict(c="J", en="Place / source", ar="المكان / المصدر", w=22, kind="in"),
    dict(c="K", en="Notes", ar="ملاحظات", w=30, kind="in"),
    dict(c="L", en="prev date", ar="", w=10, kind="hidden", fmt=FMT_DATE,
         f='=IF(OR($A{r}="",$B{r}=""),0,SUMPRODUCT(MAX((' + rng("A") + '<$A{r})*(' + rng("B") + '<>"")*' + rng("A") + ')))'),
]
# Example rates: based on press reports for November 2026 (EUR ≈ 276.5–277 DZD, USD ≈ 241 DZD at the square)
ex_rates = [276.0, 276.5, 276.5, 277.0, 276.0, 275.5, 275.5, 276.0, 276.5, 277.0, 277.0, 277.5, 276.5, 277.0]
ex_usd = [240.5, 241.0, 241.0, 241.5, 240.5, 240.0, 240.0, 240.5, 241.0, 241.5, 241.0, 241.5, 241.0, 241.0]
rate_examples = []
for i, (e, u) in enumerate(zip(ex_rates, ex_usd)):
    rate_examples.append({"A": dt.date(2026, 11, 14) + dt.timedelta(days=i), "B": e, "C": e + 2, "D": u, "E": u + 2,
                          "F": 151.0 if i in (2, 9) else None, "J": "Square (example)", "K": EX})
rate_examples[0]["K"] = EX + " — values based on Nov 2026 press reports"
build_log(ws, RATES, rate_cols, "💱 Daily exchange rates - أسعار الصرف اليومية",
          "Add one line every day with the square (black-market) price. The newest line updates every sheet automatically.  |  "
          "أضف سطرا كل يوم بسعر السكوار. آخر سطر يحدّث كل الأوراق تلقائيا.",
          examples=rate_examples)
for i in range(len(rate_examples)):
    if rate_examples[i]["F"] is None:
        ws[f"F{f6 + i}"].value = None
color_change(ws, f"G{f6}:H{l6}")
chips(ws, 3, "C", [
    ("Now (you sell)\nالآن (بيع)", "=RATE_EUR", FMT_RATE),
    ("Change\nالتغير", "=IF(RATE_EUR_PREV=0,0,RATE_EUR-RATE_EUR_PREV)", FMT_CHG),
    ("Last update\nآخر تحديث", "=IF(RATE_DATE=0,\"-\",RATE_DATE)", FMT_DATE),
])
color_change(ws, "G3")
# chart helper: last 30 days (carry the last known price forward)
ws.column_dimensions["M"].width = 3
ws.column_dimensions["N"].width = 12
ws.column_dimensions["O"].width = 14
ws.column_dimensions["P"].hidden = True
ws.merge_cells("N4:O4")
put(ws, "N4", "Last 30 days (chart)\nآخر 30 يوما", fnt(9, True, TEAL), align=Alignment(horizontal="center", wrap_text=True))
put(ws, "N5", "⚙ Day\nاليوم", fnt(9, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
put(ws, "O5", "EUR → DZD", fnt(9, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
for k in range(1, 31):
    rr = 5 + k
    put(ws, f"N{rr}", f"=IF(RATE_DATE=0,TODAY(),RATE_DATE)-30+{k}", fnt(9), AUTO_FILL, "dd/mm", border=BORDER)
    ws[f"P{rr}"] = f'=SUMPRODUCT(MAX(({rng("A")}<=N{rr})*({rng("B")}<>"")*{rng("A")}))'
    put(ws, f"O{rr}", f'=IF(RATE_DATE=0,"",IFERROR(INDEX({rng("B")},MATCH(IF(P{rr}=0,RATE_FIRST_DATE,P{rr}),{rng("A")},0)),""))',
        fnt(9), AUTO_FILL, FMT_RATE, border=BORDER)

# ==========================================================================
# SALARY
# ==========================================================================
ws = WS[SAL]
f6, l6 = ROWS[SAL]
define("S_MONTH", SAL, f"A{f6}:A{l6}")
define("S_EUR", SAL, f"G{f6}:G{l6}")
MONTH_RANGE = '">="&DATE(YEAR($A{r}),MONTH($A{r}),1),E_DATE,"<"&DATE(YEAR($A{r}),MONTH($A{r})+1,1)'
sal_cols = [
    dict(c="A", en="Month", ar="الشهر", w=12, kind="in", fmt=FMT_MONTH, dv=dv_date,
         tip="Type the 1st day of the month, e.g. 01/12/2026.\nاكتب أول يوم من الشهر."),
    dict(c="B", en="Salary (USD)", ar="الراتب (دولار)", w=12, kind="in", fmt=FMT_USD_U,
         f='=IF($A{r}="","",SALARY_USD)', dv=dv_number,
         tip="Filled automatically from Settings. Type over it if this month was different.\nيمتلئ تلقائيا، اكتب فوقه إذا تغير."),
    dict(c="C", en="USD → EUR\nrate", ar="سعر التحويل", w=11, kind="in", fmt=FMT_RATE4,
         f='=IF($A{r}="","",USD_EUR)', dv=dv_number,
         tip="Filled from Settings. Type the bank's real rate if you know it.\nاكتب سعر البنك الحقيقي إن عرفته."),
    dict(c="D", en="Bank fee\n(EUR)", ar="عمولة البنك", w=11, kind="in", fmt=FMT_EUR, dv=dv_number),
    dict(c="E", en="EUR expected", ar="الأورو المتوقع", w=13, kind="auto", fmt=FMT_EUR,
         f='=IF($A{r}="","",$B{r}*$C{r}*(1-BANK_FEE)-N($D{r}))'),
    dict(c="F", en="EUR actually\nreceived", ar="الأورو المستلم فعلا", w=13, kind="in", fmt=FMT_EUR, dv=dv_number,
         tip="Optional: the exact EUR amount on your bank statement. If empty, 'EUR expected' is used.\nاختياري: المبلغ الحقيقي في كشف البنك."),
    dict(c="G", en="EUR final", ar="الأورو النهائي", w=13, kind="auto", fmt=FMT_EUR,
         f='=IF($A{r}="","",IF($F{r}<>"",$F{r},$E{r}))'),
    dict(c="H", en="EUR sold\nthis month", ar="الأورو المباع هذا الشهر", w=13, kind="auto", fmt=FMT_EUR,
         f='=IF($A{r}="","",SUMIFS(E_AMT,E_DATE,' + MONTH_RANGE + ',E_CUR,"<>USD"))'),
    dict(c="I", en="DZD from\nselling", ar="الدينار من البيع", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF($A{r}="","",SUMIFS(E_DZD,E_DATE,' + MONTH_RANGE + ',E_CUR,"<>USD"))'),
    dict(c="J", en="Average rate\nsold", ar="متوسط سعر البيع", w=12, kind="auto", fmt=FMT_RATE,
         f='=IF(N($H{r})>0,$I{r}/$H{r},"")'),
    dict(c="K", en="Value at today's\nsquare rate", ar="القيمة بسعر اليوم", w=15, kind="auto", fmt=FMT_DZD,
         f='=IF($A{r}="","",$G{r}*RATE_EUR)'),
    dict(c="L", en="Value at\nofficial rate", ar="القيمة بالسعر الرسمي", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF($A{r}="","",$G{r}*OFFICIAL_EUR)'),
    dict(c="M", en="Square gain", ar="ربح السكوار", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF($A{r}="","",$K{r}-$L{r})'),
    dict(c="N", en="Notes", ar="ملاحظات", w=28, kind="in"),
]
S = "=SUBTOTAL(109,{c}{first}:{c}{last})"
build_log(ws, SAL, sal_cols, "💵 Salary - الراتب  (USD → EUR → DZD)",
          "Add a line when the salary arrives: type only the month. USD, rate and EUR fill themselves.  |  "
          "أضف سطرا عند وصول الراتب: اكتب الشهر فقط، الباقي يمتلئ تلقائيا.",
          totals={c: (S.replace("{c}", c), fmt) for c, fmt in
                  (("B", FMT_USD_U), ("E", FMT_EUR), ("F", FMT_EUR), ("G", FMT_EUR), ("H", FMT_EUR),
                   ("I", FMT_DZD), ("K", FMT_DZD), ("L", FMT_DZD), ("M", FMT_DZD))},
          examples=[{"A": dt.date(2026, 10, 1), "F": 2446.30, "N": EX},
                    {"A": dt.date(2026, 11, 1), "N": EX}])
ws["J4"] = '=IF(N(H4)>0,I4/H4,"")'
ws["J4"].number_format = FMT_RATE
ws["J4"].font = fnt(10, True, NAVY)
ws["J4"].fill = fill(LIGHT_NAVY)
chips(ws, 3, "C", [
    ("Salary now\nالراتب الآن", "=SALARY_EUR", FMT_EUR_U),
    ("In DZD today\nبالدينار اليوم", "=SALARY_DZD", FMT_DZD_U),
    ("EUR in bank\nالأورو في البنك", "=EUR_BALANCE", FMT_EUR_U),
])

# ==========================================================================
# EXCHANGE (selling EUR / USD at the square)
# ==========================================================================
ws = WS[EXC]
f6, l6 = ROWS[EXC]
for nm, c in (("E_DATE", "A"), ("E_CUR", "B"), ("E_AMT", "C"), ("E_RATE", "D"), ("E_DZD", "E")):
    define(nm, EXC, f"{c}{f6}:{c}{l6}")
exc_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="B", en="Currency", ar="العملة", w=10, kind="in",
         dv=lambda w, rg: dv_list(w, rg, "LIST_CUR", True), tip="EUR or USD. Empty = EUR.\nفارغ = أورو"),
    dict(c="C", en="Amount sold", ar="المبلغ المباع", w=13, kind="in", fmt=FMT_EUR, dv=dv_number),
    dict(c="D", en="Rate you got\n(DZD)", ar="السعر الذي أخذته", w=13, kind="in", fmt=FMT_RATE, dv=dv_number),
    dict(c="E", en="DZD received", ar="الدينار المستلم", w=15, kind="auto", fmt=FMT_DZD,
         f='=IF(OR($C{r}="",$D{r}=""),"",$C{r}*$D{r})'),
    dict(c="F", en="Market rate\nthat day", ar="سعر السوق ذلك اليوم", w=13, kind="auto", fmt=FMT_RATE,
         f='=IF($A{r}="","",IFERROR(1/(1/INDEX(IF($B{r}="USD",R_USD,R_EUR),MATCH($A{r},R_DATE,0))),""))'),
    dict(c="G", en="Better / worse\nthan market", ar="أفضل / أسوأ من السوق", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF(OR($E{r}="",$F{r}=""),"",($D{r}-$F{r})*$C{r})',
         tip="Positive = you sold above the market price that day.\nموجب = بعت بسعر أفضل من السوق."),
    dict(c="H", en="Buyer / place", ar="المشتري / المكان", w=22, kind="in"),
    dict(c="I", en="Notes", ar="ملاحظات", w=28, kind="in"),
]
build_log(ws, EXC, exc_cols, "🔄 Exchange - بيع العملة في السكوار",
          "Every time you sell EUR (or USD) for dinars, add one line.  |  كل مرة تبيع الأورو أو الدولار بالدينار، أضف سطرا.",
          totals={"E": (S.replace("{c}", "E"), FMT_DZD), "G": (S.replace("{c}", "G"), FMT_DZD)},
          examples=[{"A": dt.date(2026, 10, 5), "B": "EUR", "C": 1500, "D": 274.5, "H": "Square (example)", "I": EX},
                    {"A": dt.date(2026, 11, 16), "B": "EUR", "C": 2000, "D": 276.5, "H": "Square (example)", "I": EX},
                    {"A": dt.date(2026, 11, 24), "B": "EUR", "C": 400, "D": 277.0, "H": "Square (example)", "I": EX}])
chips(ws, 3, "C", [
    ("EUR sold (all)\nكل الأورو المباع", '=SUMIFS(E_AMT,E_CUR,"<>USD")', FMT_EUR_U),
    ("DZD received\nالدينار المستلم", "=SUM(E_DZD)", FMT_DZD_U),
    ("Avg EUR rate\nمتوسط السعر", '=IFERROR(SUMIFS(E_DZD,E_CUR,"<>USD")/SUMIFS(E_AMT,E_CUR,"<>USD"),0)', FMT_RATE),
])

# ==========================================================================
# DEBTS
# ==========================================================================
ws = WS[DEBT]
f6, l6 = ROWS[DEBT]
for nm, c in (("D_ID", "A"), ("D_TYPE", "B"), ("D_PERSON", "C"), ("D_CUR", "H"), ("D_DUE", "I"), ("D_REM", "K"),
              ("D_REMDZD", "L"), ("D_DAYS", "M"), ("D_STATUS", "N"), ("D_LABEL", "P"), ("D_KEY", "Q")):
    define(nm, DEBT, f"{c}{f6}:{c}{l6}")
debt_cols = [
    dict(c="A", en="ID", ar="الرقم", w=7, kind="id", id=lambda n: f"D{n:03d}"),
    dict(c="B", en="Type", ar="النوع", w=15, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_DEBTTYPE", True),
         tip="I owe = you borrowed (سلف عليك).\nOwed to me = you lent (سلّفت لشخص)."),
    dict(c="C", en="Person", ar="الشخص", w=20, kind="in"),
    dict(c="D", en="Phone", ar="الهاتف", w=13, kind="in"),
    dict(c="E", en="Relation", ar="القرابة", w=15, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_REL")),
    dict(c="F", en="Date taken", ar="تاريخ السلف", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="G", en="Amount", ar="المبلغ", w=12, kind="in", fmt=FMT_EUR, dv=dv_number),
    dict(c="H", en="Currency", ar="العملة", w=8, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_CUR", True),
         tip="Empty = DZD - فارغ = دينار"),
    dict(c="I", en="Planned return\ndate", ar="تاريخ الإرجاع المخطط", w=13, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="J", en="Paid so far", ar="المسدد", w=12, kind="auto", fmt=FMT_EUR,
         f='=IF($C{r}="","",SUMIFS(P_AMT,P_ID,$A{r}))', tip="From the Payments sheet - من ورقة التسديد"),
    dict(c="K", en="Remaining", ar="المتبقي", w=12, kind="auto", fmt=FMT_EUR,
         f='=IF($C{r}="","",N($G{r})-$J{r})'),
    dict(c="L", en="Remaining\nin DZD", ar="المتبقي بالدينار", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF($C{r}="","",$K{r}*IF($H{r}="EUR",RATE_EUR,IF($H{r}="USD",RATE_USD,1)))',
         tip="EUR / USD debts are converted at today's square rate.\nالديون بالأورو تحسب بسعر اليوم."),
    dict(c="M", en="Days left", ar="الأيام المتبقية", w=10, kind="auto", fmt=FMT_INT,
         f='=IF(OR($C{r}="",$I{r}="",N($K{r})<=0),"",$I{r}-TODAY())'),
    dict(c="N", en="Status", ar="الحالة", w=17, kind="auto",
         f='=IF($C{r}="","",IF(N($K{r})<=0,"✔ Paid - مسدد",IF($I{r}="","● Open - مفتوح",IF($I{r}<TODAY(),"⚠ Overdue - متأخر",'
           'IF($I{r}-TODAY()<=DUE_SOON_DAYS,"⏰ Due soon - قريب","● Open - مفتوح")))))'),
    dict(c="O", en="Reason / notes", ar="السبب / ملاحظات", w=28, kind="in"),
    dict(c="P", en="label", ar="", w=30, kind="hidden",
         f='=IF($C{r}="",$A{r},$A{r}&" | "&$C{r}&" | "&FIXED(N($G{r}),0)&" "&IF($H{r}="","DZD",$H{r}))'),
    dict(c="Q", en="key", ar="", w=10, kind="hidden",
         f='=IF(OR($C{r}="",N($K{r})<=0),"",IF($I{r}="",100000,$I{r})+ROW()/100000)'),
]
build_log(ws, DEBT, debt_cols, "🤝 Debts & loans - الديون والسلف",
          "One line per loan: money you borrowed (I owe - عليّ) or lent (Owed to me - لي), with the person and the date you plan to return it. "
          "Record each repayment in Payments.  |  سطر لكل سلف: الشخص، المبلغ وتاريخ الإرجاع المخطط. سجّل كل دفعة في ورقة التسديد.",
          examples=[
              {"B": "I owe - عليّ", "C": "Karim (example - مثال)", "D": "0550 00 00 00", "E": "Friend - صديق",
               "F": dt.date(2026, 10, 10), "G": 50000, "H": "DZD", "I": dt.date(2026, 12, 15), "O": "Car repair - تصليح السيارة. " + EX},
              {"B": "Owed to me - لي", "C": "Yacine (example - مثال)", "E": "Cousin - ابن العم / الخال",
               "F": dt.date(2026, 9, 1), "G": 300, "H": "EUR", "I": dt.date(2026, 11, 20), "O": EX},
              {"B": "Owed to me - لي", "C": "My brother (example) - أخي", "E": "Brother - أخ",
               "F": dt.date(2026, 11, 5), "G": 30000, "H": "DZD", "I": dt.date(2026, 12, 1), "O": EX},
          ])
for c in ("C", "O"):
    for rr in range(f6, l6 + 1):
        ws[f"{c}{rr}"].alignment = Alignment(wrap_text=False)
chips(ws, 3, "C", [
    ("I owe (DZD)\nعليّ", "=I_OWE_DZD", FMT_DZD),
    ("Owed to me\nلي", "=OWED_ME_DZD", FMT_DZD),
    ("Overdue\nمتأخرة", '=COUNTIF(D_STATUS,"*Overdue*")', "0"),
    ("Due soon\nقريبة", '=COUNTIF(D_STATUS,"*Due soon*")', "0"),
])
rows_rng = f"A{f6}:O{l6}"
ws.conditional_formatting.add(rows_rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("Overdue",$N{f6}))'], fill=fill("FDE2E1"), font=Font(color=RED, bold=True)))
ws.conditional_formatting.add(rows_rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("Due soon",$N{f6}))'], fill=fill("FFF1D6"), font=Font(color=ORANGE)))
ws.conditional_formatting.add(rows_rng, FormulaRule(formula=[f'ISNUMBER(SEARCH("Paid",$N{f6}))'], fill=fill("E6F4EA"), font=Font(color="7A7A7A")))

# ==========================================================================
# PAYMENTS
# ==========================================================================
ws = WS[PAY]
f6, l6 = ROWS[PAY]
define("P_ID", PAY, f"F{f6}:F{l6}")
define("P_AMT", PAY, f"C{f6}:C{l6}")
LIST_SRC["LIST_DEBTLABEL"] = f"{q(DEBT)}$P${ROWS[DEBT][0]}:$P${ROWS[DEBT][1]}"
pay_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="B", en="Debt (choose)", ar="الدين (اختر)", w=34, kind="in",
         dv=lambda w, rg: dv_list(w, rg, "LIST_DEBTLABEL", True, "Choose the debt: ID | person | amount\nاختر الدين من القائمة")),
    dict(c="C", en="Amount paid\n(debt currency)", ar="المبلغ المدفوع", w=14, kind="in", fmt=FMT_EUR, dv=dv_number,
         tip="Same currency as the debt (EUR debt → amount in EUR).\nبنفس عملة الدين."),
    dict(c="D", en="Method", ar="الطريقة", w=18, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_PAY")),
    dict(c="E", en="Notes", ar="ملاحظات", w=26, kind="in"),
    dict(c="F", en="Debt ID", ar="رقم الدين", w=9, kind="auto", f='=IF($B{r}="","",LEFT($B{r},4))', align=Alignment(horizontal="center")),
    dict(c="G", en="Person", ar="الشخص", w=20, kind="auto", f='=IF($F{r}="","",IFERROR(INDEX(D_PERSON,MATCH($F{r},D_ID,0))&"",""))'),
    dict(c="H", en="Type", ar="النوع", w=15, kind="auto", f='=IF($F{r}="","",IFERROR(INDEX(D_TYPE,MATCH($F{r},D_ID,0))&"",""))'),
    dict(c="I", en="Currency", ar="العملة", w=9, kind="auto",
         f='=IF($F{r}="","",IFERROR(IF(INDEX(D_CUR,MATCH($F{r},D_ID,0))&""="","DZD",INDEX(D_CUR,MATCH($F{r},D_ID,0))&""),""))'),
    dict(c="J", en="Debt remaining\nnow", ar="المتبقي الآن", w=14, kind="auto", fmt=FMT_EUR,
         f='=IF($F{r}="","",IFERROR(INDEX(D_REM,MATCH($F{r},D_ID,0)),""))'),
]
build_log(ws, PAY, pay_cols, "💸 Debt payments - تسديد الديون",
          "Each time money is paid back (by you or to you), add a line and choose the debt from the list. The Debts sheet updates by itself.  |  "
          "كل دفعة (منك أو إليك) سطر جديد، اختر الدين من القائمة.",
          examples=[{"A": dt.date(2026, 11, 10), "B": "D001 | Karim (example - مثال) | 50,000 DZD", "C": 20000, "D": "Cash - نقدا", "E": EX},
                    {"A": dt.date(2026, 11, 15), "B": "D002 | Yacine (example - مثال) | 300 EUR", "C": 100, "D": "Cash - نقدا", "E": EX}])

# ==========================================================================
# FAMILY (Aboubakr & Bouchra household)
# ==========================================================================
ws = WS[FAM]
f6, l6 = ROWS[FAM]
for nm, c in (("F_DATE", "A"), ("F_TYPE", "B"), ("F_WHO", "C"), ("F_CAT", "D"), ("F_AMT", "F")):
    define(nm, FAM, f"{c}{f6}:{c}{l6}")
fam_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="B", en="Type", ar="النوع", w=15, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_TYPE", True),
         tip="Empty = Expense. Choose Income for money that comes in (other than selling EUR).\nفارغ = مصروف."),
    dict(c="C", en="Who", ar="من", w=18, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_WHO")),
    dict(c="D", en="Category", ar="الفئة", w=30, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_CAT")),
    dict(c="E", en="Description", ar="الوصف", w=30, kind="in"),
    dict(c="F", en="Amount (DZD)", ar="المبلغ (دج)", w=14, kind="in", fmt=FMT_DZD, dv=dv_number),
    dict(c="G", en="Payment method", ar="طريقة الدفع", w=20, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_PAY")),
    dict(c="H", en="Notes", ar="ملاحظات", w=26, kind="in"),
]
build_log(ws, FAM, fam_cols, "👨‍👩 Family - العائلة  (Aboubakr & Bouchra - أبوبكر و بشرى)",
          "Every expense of the house (and any extra income). Choose who paid and the category.  |  "
          "كل مصاريف البيت (وأي دخل إضافي). اختر من دفع والفئة.",
          totals={"F": (S.replace("{c}", "F"), FMT_DZD)},
          examples=[
              {"A": dt.date(2026, 11, 2), "B": "Expense - مصروف", "C": "Both - مشترك", "D": "Food & groceries - المواد الغذائية",
               "E": "Monthly groceries - مشتريات الشهر", "F": 18500, "G": "Cash - نقدا", "H": EX},
              {"A": dt.date(2026, 11, 5), "B": "Expense - مصروف", "C": "Aboubakr - أبوبكر", "D": "Electricity & gas - الكهرباء والغاز",
               "E": "Sonelgaz bill - فاتورة سونلغاز", "F": 4800, "G": "BaridiMob / CCP - بريدي موب", "H": EX},
              {"A": dt.date(2026, 11, 8), "B": "Expense - مصروف", "C": "Aboubakr - أبوبكر", "D": "Transport & fuel - النقل والوقود",
               "E": "Fuel - وقود", "F": 3000, "G": "Cash - نقدا", "H": EX},
              {"A": dt.date(2026, 11, 12), "B": "Expense - مصروف", "C": "Bouchra - بشرى", "D": "Clothes - الملابس",
               "E": "Winter clothes - ملابس الشتاء", "F": 7500, "G": "Cash - نقدا", "H": EX},
              {"A": dt.date(2026, 11, 25), "B": "Income - دخل", "C": "Bouchra - بشرى", "D": "Other - أخرى",
               "E": "Other income - دخل آخر", "F": 10000, "G": "Cash - نقدا", "H": EX},
          ])
M_SEL = 'F_DATE,">="&SEL_MONTH,F_DATE,"<"&SEL_MONTH_END'
chips(ws, 3, "C", [
    ("Spent this month\nمصاريف الشهر", f'=SUMIFS(F_AMT,F_TYPE,"<>"&TYPE_INCOME,{M_SEL})', FMT_DZD),
    ("Aboubakr\nأبوبكر", f'=SUMIFS(F_AMT,F_TYPE,"<>"&TYPE_INCOME,F_WHO,WHO_ME,{M_SEL})', FMT_DZD),
    ("Bouchra\nبشرى", f'=SUMIFS(F_AMT,F_TYPE,"<>"&TYPE_INCOME,F_WHO,WHO_WIFE,{M_SEL})', FMT_DZD),
    ("Income this month\nدخل الشهر", f'=SUMIFS(F_AMT,F_TYPE,TYPE_INCOME,{M_SEL})', FMT_DZD),
], step=2)
ws.column_dimensions["C"].width = 18

# ==========================================================================
# BUDGET
# ==========================================================================
ws = WS[BUD]
title(ws, "📊 Monthly budget - الميزانية الشهرية",
      "Type your monthly budget per category (blue). Spending is read from the Family sheet for the chosen month.  |  "
      "اكتب ميزانية كل فئة، المصاريف تقرأ من ورقة العائلة.", 9)
put(ws, "A4", "Month - الشهر:", fnt(10, True, NAVY), align=Alignment(horizontal="right"))
put(ws, "B4", "=SEL_MONTH", fnt(11, True, BLUE_IN), YELLOW, "mmmm yyyy", Alignment(horizontal="center"), BORDER)
comment(ws, "B4", "Follows the month chosen on the Dashboard. Type another date (e.g. 01/10/2026) to see another month.\n"
                  "يتبع شهر لوحة القيادة. اكتب تاريخا آخر لرؤية شهر آخر.")
define("BUD_MONTH", BUD, "B4")
put(ws, "C4", '=DATE(YEAR(B4),MONTH(B4)+1,1)', fnt(8, False, "FFFFFF"), fmt=FMT_DATE)
define("BUD_MONTH_END", BUD, "C4")
bud_hdr = [("A", "Category", "الفئة", 32), ("B", "Monthly budget\n(DZD)", "الميزانية الشهرية", 15),
           ("C", "Aboubakr", "أبوبكر", 13), ("D", "Bouchra", "بشرى", 13), ("E", "Shared / other", "مشترك / آخر", 13),
           ("F", "Total spent", "مجموع المصاريف", 14), ("G", "Remaining", "المتبقي", 13), ("H", "% used", "نسبة الاستهلاك", 12),
           ("I", "Status", "الحالة", 18)]
for c, en, ar, w in bud_hdr:
    ws.column_dimensions[c].width = w
    put(ws, f"{c}6", (en if c == "B" else ("⚙ " + en if c != "A" else en)) + "\n" + ar, fnt(9, True, "FFFFFF"),
        NAVY if c in ("A", "B") else TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
ws.row_dimensions[6].height = 40
budgets = [45000, 0, 6000, 1500, 4500, 10000, 6000, 10000, 8000, 8000, 8000, 6000, 5000, 6000, 3000, 5000]
BM = 'F_DATE,">="&BUD_MONTH,F_DATE,"<"&BUD_MONTH_END'
for i in range(25):
    rr = 7 + i
    put(ws, f"A{rr}", f'=IF({q(SET)}F{6 + i}="","",{q(SET)}F{6 + i})', fnt(10), AUTO_FILL, border=BORDER)
    put(ws, f"B{rr}", budgets[i] if i < len(budgets) else None, fnt(10, False, BLUE_IN), fmt=FMT_DZD, border=BORDER)
    put(ws, f"C{rr}", f'=IF($A{rr}="","",SUMIFS(F_AMT,F_CAT,$A{rr},F_WHO,WHO_ME,F_TYPE,"<>"&TYPE_INCOME,{BM}))', fnt(10), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"D{rr}", f'=IF($A{rr}="","",SUMIFS(F_AMT,F_CAT,$A{rr},F_WHO,WHO_WIFE,F_TYPE,"<>"&TYPE_INCOME,{BM}))', fnt(10), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"F{rr}", f'=IF($A{rr}="","",SUMIFS(F_AMT,F_CAT,$A{rr},F_TYPE,"<>"&TYPE_INCOME,{BM}))', fnt(10, True), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"E{rr}", f'=IF($A{rr}="","",F{rr}-C{rr}-D{rr})', fnt(10), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"G{rr}", f'=IF($A{rr}="","",N(B{rr})-F{rr})', fnt(10), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"H{rr}", f'=IF(OR($A{rr}="",N($B{rr})=0),"",F{rr}/B{rr})', fnt(10), AUTO_FILL, "0%", border=BORDER)
    put(ws, f"I{rr}", f'=IF($A{rr}="","",IF(N($B{rr})=0,IF(N(F{rr})>0,"No budget - بدون ميزانية",""),IF(F{rr}>B{rr},"⚠ Over - تجاوز",'
                      f'IF(F{rr}>=0.8*B{rr},"⏰ Near limit - قريب","✔ OK - جيد"))))', fnt(10), AUTO_FILL, border=BORDER)
dv_number(ws, "B7:B31")
rr = 32
put(ws, f"A{rr}", "Not in a category - بدون فئة", fnt(10, False, GRAY_TXT, italic=True), AUTO_FILL, border=BORDER)
put(ws, f"F{rr}", f'=SUMIFS(F_AMT,F_TYPE,"<>"&TYPE_INCOME,{BM})-SUM(F7:F31)', fnt(10), AUTO_FILL, FMT_DZD, border=BORDER)
comment(ws, f"A{rr}", "Spending whose category is empty or not in the list. - مصاريف بدون فئة")
rr = 33
put(ws, f"A{rr}", "TOTAL - المجموع", fnt(10, True, "FFFFFF"), NAVY, border=BORDER)
for c in "BCDEFG":
    put(ws, f"{c}{rr}", f"=SUM({c}7:{c}32)", fnt(10, True, "FFFFFF"), NAVY, FMT_DZD, border=BORDER)
put(ws, f"H{rr}", "=IF(B33>0,F33/B33,\"\")", fnt(10, True, "FFFFFF"), NAVY, "0%", border=BORDER)
put(ws, f"I{rr}", None, fill_=NAVY, border=BORDER)
ws.conditional_formatting.add("H7:H31", ColorScaleRule(start_type="num", start_value=0, start_color="C8E6C9", mid_type="num", mid_value=0.8,
                                                        mid_color="FFF59D", end_type="num", end_value=1, end_color="EF9A9A"))
ws.conditional_formatting.add("I7:I31", FormulaRule(formula=['ISNUMBER(SEARCH("Over",$I7))'], font=Font(color=RED, bold=True), fill=fill("FDE2E1")))
ws.conditional_formatting.add("I7:I31", FormulaRule(formula=['ISNUMBER(SEARCH("Near",$I7))'], font=Font(color=ORANGE, bold=True)))
ws.conditional_formatting.add("I7:I31", FormulaRule(formula=['ISNUMBER(SEARCH("OK",$I7))'], font=Font(color=GREEN)))
link(ws, "A3", DASH, "← Dashboard\nالرئيسية", 9)
ws.freeze_panes = "B7"
ws.sheet_view.showGridLines = False

# ==========================================================================
# RELATIVES (brother, mother, wife's mother ...)
# ==========================================================================
ws = WS[REL]
f6, l6 = ROWS[REL]
for nm, c in (("RL_DATE", "A"), ("RL_REL", "C"), ("RL_AMT", "E")):
    define(nm, REL, f"{c}{f6}:{c}{l6}")
rel_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="B", en="Person name", ar="الاسم", w=22, kind="in"),
    dict(c="C", en="Relation", ar="القرابة", w=20, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_REL")),
    dict(c="D", en="Help type", ar="نوع المساعدة", w=20, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_HELP")),
    dict(c="E", en="Amount (DZD)", ar="المبلغ (دج)", w=14, kind="in", fmt=FMT_DZD, dv=dv_number),
    dict(c="F", en="Given by", ar="من أعطى", w=18, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_WHO")),
    dict(c="G", en="Notes", ar="ملاحظات", w=28, kind="in"),
]
build_log(ws, REL, rel_cols, "🏡 Relatives - الأقارب  (brother, mother, wife's mother ... - الأخ، الأم، أم الزوجة)",
          "Money you GIVE to help the family. If they will give it back, write it in Debts instead.  |  "
          "المال الذي تعطيه لمساعدة الأهل. إذا كان سلفا سيرجع، اكتبه في ورقة الديون.",
          totals={"E": (S.replace("{c}", "E"), FMT_DZD)},
          examples=[
              {"A": dt.date(2026, 11, 3), "B": "My brother - أخي", "C": "Brother - أخ", "D": "Monthly support - مصروف شهري",
               "E": 15000, "F": "Aboubakr - أبوبكر", "G": EX},
              {"A": dt.date(2026, 11, 3), "B": "My mother - أمي", "C": "Mother - الأم", "D": "Monthly support - مصروف شهري",
               "E": 20000, "F": "Aboubakr - أبوبكر", "G": EX},
              {"A": dt.date(2026, 11, 15), "B": "Bouchra's mother - أم بشرى", "C": "Wife's mother - أم الزوجة", "D": "Gift - هدية",
               "E": 10000, "F": "Both - مشترك", "G": EX},
          ])
chips(ws, 3, "C", [
    ("This month\nهذا الشهر", '=SUMIFS(RL_AMT,RL_DATE,">="&SEL_MONTH,RL_DATE,"<"&SEL_MONTH_END)', FMT_DZD),
    ("This year\nهذه السنة", '=SUMIFS(RL_AMT,RL_DATE,">="&DATE(YEAR(SEL_MONTH),1,1),RL_DATE,"<"&DATE(YEAR(SEL_MONTH)+1,1,1))', FMT_DZD),
], step=2)
# summary by relation
ws.column_dimensions["H"].width = 3
for c, w in (("I", 24), ("J", 13), ("K", 13), ("L", 13)):
    ws.column_dimensions[c].width = w
ws.merge_cells("I4:L4")
put(ws, "I4", "By relation - حسب القرابة", fnt(10, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center"))
for c, txt in (("I", "Relation\nالقرابة"), ("J", "This month\nهذا الشهر"), ("K", "This year\nهذه السنة"), ("L", "All time\nالكل")):
    put(ws, f"{c}5", txt, fnt(9, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
for i in range(20):
    rr = 6 + i
    put(ws, f"I{rr}", f'=IF({q(SET)}J{6 + i}="","",{q(SET)}J{6 + i})', fnt(9), AUTO_FILL, border=BORDER)
    put(ws, f"J{rr}", f'=IF($I{rr}="","",SUMIFS(RL_AMT,RL_REL,$I{rr},RL_DATE,">="&SEL_MONTH,RL_DATE,"<"&SEL_MONTH_END))', fnt(9), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"K{rr}", f'=IF($I{rr}="","",SUMIFS(RL_AMT,RL_REL,$I{rr},RL_DATE,">="&DATE(YEAR(SEL_MONTH),1,1),RL_DATE,"<"&DATE(YEAR(SEL_MONTH)+1,1,1)))', fnt(9), AUTO_FILL, FMT_DZD, border=BORDER)
    put(ws, f"L{rr}", f'=IF($I{rr}="","",SUMIFS(RL_AMT,RL_REL,$I{rr}))', fnt(9), AUTO_FILL, FMT_DZD, border=BORDER)
put(ws, "I26", "TOTAL - المجموع", fnt(9, True, "FFFFFF"), NAVY, border=BORDER)
for c in "JKL":
    put(ws, f"{c}26", f"=SUM({c}6:{c}25)", fnt(9, True, "FFFFFF"), NAVY, FMT_DZD, border=BORDER)

# ==========================================================================
# PLANS (future goals)
# ==========================================================================
ws = WS[PLAN]
f6, l6 = ROWS[PLAN]
for nm, c in (("G_ID", "A"), ("G_NAME", "B"), ("G_TARGET", "F"), ("G_SAVED", "I"), ("G_PROG", "K"),
              ("G_MONTHLY", "M"), ("G_STATUS", "N"), ("G_LABEL", "P"), ("G_KEY", "Q")):
    define(nm, PLAN, f"{c}{f6}:{c}{l6}")
plan_cols = [
    dict(c="A", en="ID", ar="الرقم", w=6, kind="id", id=lambda n: f"G{n:02d}"),
    dict(c="B", en="Goal", ar="الهدف", w=28, kind="in"),
    dict(c="C", en="Category", ar="النوع", w=20, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_GOALCAT")),
    dict(c="D", en="For whom", ar="لمن", w=15, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_WHO")),
    dict(c="E", en="Priority", ar="الأولوية", w=13, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_PRIO")),
    dict(c="F", en="Target amount\n(DZD)", ar="المبلغ المطلوب", w=14, kind="in", fmt=FMT_DZD, dv=dv_number),
    dict(c="G", en="Start date", ar="تاريخ البداية", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="H", en="Target date", ar="التاريخ المستهدف", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="I", en="Saved so far", ar="المدخر", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF($B{r}="","",SUMIFS(SV_DZD,SV_ID,$A{r}))', tip="From the Savings sheet - من ورقة الادخار"),
    dict(c="J", en="Remaining", ar="المتبقي", w=14, kind="auto", fmt=FMT_DZD, f='=IF($B{r}="","",MAX(0,N($F{r})-$I{r}))'),
    dict(c="K", en="Progress", ar="التقدم", w=12, kind="auto", fmt="0%", f='=IF(OR($B{r}="",N($F{r})=0),"",MIN(1,MAX(0,$I{r}/$F{r})))'),
    dict(c="L", en="Months left", ar="الأشهر المتبقية", w=10, kind="auto", fmt="0",
         f='=IF(OR($B{r}="",$H{r}=""),"",MAX(0,(YEAR($H{r})-YEAR(TODAY()))*12+MONTH($H{r})-MONTH(TODAY())))'),
    dict(c="M", en="Save per month", ar="ادخار شهري لازم", w=14, kind="auto", fmt=FMT_DZD,
         f='=IF(OR($B{r}="",$J{r}=""),"",IF($J{r}<=0,0,IF(N($L{r})>0,$J{r}/$L{r},$J{r})))'),
    dict(c="N", en="Status", ar="الحالة", w=19, kind="auto",
         f='=IF($B{r}="","",IF(N($F{r})=0,"✎ Set target - حدد المبلغ",IF($J{r}<=0,"✔ Done - تحقق",IF($I{r}<=0,"○ Not started - لم يبدأ",'
           'IF(OR($G{r}="",$H{r}="",$H{r}<=$G{r}),"● In progress - جاري",IF($K{r}>=MIN(1,MAX(0,(TODAY()-$G{r})/($H{r}-$G{r})))-0.05,'
           '"✔ On track - في الطريق","⚠ Behind - متأخر"))))))'),
    dict(c="O", en="Notes", ar="ملاحظات", w=26, kind="in"),
    dict(c="P", en="label", ar="", w=30, kind="hidden", f='=IF($B{r}="",$A{r},$A{r}&" | "&$B{r})'),
    dict(c="Q", en="key", ar="", w=8, kind="hidden", f='=IF($B{r}="","",ROW())'),
]
build_log(ws, PLAN, plan_cols, "🎯 Future plans - خطط المستقبل",
          "Write your goals (house, car, Umrah, emergency fund...). Add money to a goal in the Savings sheet and the progress updates.  |  "
          "اكتب أهدافك، وأضف المال للهدف في ورقة الادخار فيتحدث التقدم تلقائيا.",
          totals={"F": (S.replace("{c}", "F"), FMT_DZD), "I": (S.replace("{c}", "I"), FMT_DZD),
                  "J": (S.replace("{c}", "J"), FMT_DZD), "M": (S.replace("{c}", "M"), FMT_DZD)},
          examples=[
              {"B": "Emergency fund (6 months) - صندوق الطوارئ", "C": "Emergency fund - صندوق الطوارئ", "D": "Both - مشترك",
               "E": "High - عالية", "F": 600000, "G": dt.date(2026, 9, 1), "H": dt.date(2027, 6, 30), "O": EX},
              {"B": "Umrah for two - عمرة لشخصين", "C": "Hajj / Umrah - الحج / العمرة", "D": "Both - مشترك",
               "E": "High - عالية", "F": 900000, "G": dt.date(2026, 10, 1), "H": dt.date(2027, 12, 31), "O": EX},
              {"B": "Car - سيارة", "C": "Car - السيارة", "D": "Aboubakr - أبوبكر", "E": "Medium - متوسطة",
               "F": 3500000, "G": dt.date(2026, 11, 1), "H": dt.date(2028, 12, 31), "O": EX},
          ])
ws["K4"] = '=IF(N(F4)>0,I4/F4,"")'
ws["K4"].number_format = "0%"
ws["K4"].font = fnt(10, True, NAVY)
ws["K4"].fill = fill(LIGHT_NAVY)
chips(ws, 3, "C", [
    ("All goals\nكل الأهداف", "=GOALS_TARGET", FMT_DZD),
    ("Saved\nالمدخر", "=SAVINGS_DZD", FMT_DZD),
    ("Progress\nالتقدم", '=IF(GOALS_TARGET>0,SAVINGS_DZD/GOALS_TARGET,0)', "0%"),
])
ws.conditional_formatting.add(f"K{f6}:K{l6}", ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=1, end_color="81C784"))
ws.conditional_formatting.add(f"N{f6}:N{l6}", FormulaRule(formula=[f'ISNUMBER(SEARCH("Behind",$N{f6}))'], font=Font(color=RED, bold=True)))
ws.conditional_formatting.add(f"N{f6}:N{l6}", FormulaRule(formula=[f'OR(ISNUMBER(SEARCH("track",$N{f6})),ISNUMBER(SEARCH("Done",$N{f6})))'], font=Font(color=GREEN, bold=True)))

# ==========================================================================
# SAVINGS
# ==========================================================================
ws = WS[SAV]
f6, l6 = ROWS[SAV]
for nm, c in (("SV_DATE", "A"), ("SV_ID", "H"), ("SV_DZD", "I")):
    define(nm, SAV, f"{c}{f6}:{c}{l6}")
LIST_SRC["LIST_GOALLABEL"] = f"{q(PLAN)}$P${ROWS[PLAN][0]}:$P${ROWS[PLAN][1]}"
sav_cols = [
    dict(c="A", en="Date", ar="التاريخ", w=12, kind="in", fmt=FMT_DATE, dv=dv_date),
    dict(c="B", en="Goal (choose)", ar="الهدف (اختر)", w=34, kind="in",
         dv=lambda w, rg: dv_list(w, rg, "LIST_GOALLABEL", True, "Choose the goal from the list\nاختر الهدف من القائمة")),
    dict(c="C", en="Amount\n(− = take out)", ar="المبلغ (− للسحب)", w=13, kind="in", fmt=FMT_EUR,
         dv=lambda w, rg: dv_number(w, rg, negative_ok=True),
         tip="Positive = put money in. Negative (e.g. -20000) = take money out.\nموجب = إيداع، سالب = سحب."),
    dict(c="D", en="Currency", ar="العملة", w=9, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_CUR", True), tip="Empty = DZD"),
    dict(c="E", en="Who", ar="من", w=16, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_WHO")),
    dict(c="F", en="Where kept", ar="أين المال", w=20, kind="in", dv=lambda w, rg: dv_list(w, rg, "LIST_KEPT")),
    dict(c="G", en="Notes", ar="ملاحظات", w=24, kind="in"),
    dict(c="H", en="Goal ID", ar="رقم الهدف", w=9, kind="auto", f='=IF($B{r}="","",LEFT($B{r},3))', align=Alignment(horizontal="center")),
    dict(c="I", en="Value in DZD\n(today)", ar="القيمة بالدينار اليوم", w=15, kind="auto", fmt=FMT_DZD,
         f='=IF($C{r}="","",$C{r}*IF($D{r}="EUR",RATE_EUR,IF($D{r}="USD",RATE_USD,1)))',
         tip="EUR savings are valued at today's square rate, so their DZD value moves every day.\nالمدخرات بالأورو تقيم بسعر اليوم."),
]
build_log(ws, SAV, sav_cols, "🏦 Savings - الادخار",
          "Each time you put money aside for a goal, add a line and choose the goal. You can save in DZD or EUR.  |  "
          "كل مرة تدخر لهدف، أضف سطرا واختر الهدف. يمكنك الادخار بالدينار أو الأورو.",
          totals={"I": (S.replace("{c}", "I"), FMT_DZD)},
          examples=[{"A": dt.date(2026, 10, 5), "B": "G01 | Emergency fund (6 months) - صندوق الطوارئ", "C": 100000, "D": "DZD",
                     "E": "Both - مشترك", "F": "CCP / bank DZD - الحساب البريدي", "G": EX},
                    {"A": dt.date(2026, 11, 16), "B": "G01 | Emergency fund (6 months) - صندوق الطوارئ", "C": 50000, "D": "DZD",
                     "E": "Both - مشترك", "F": "Cash DZD - نقدا", "G": EX},
                    {"A": dt.date(2026, 11, 16), "B": "G02 | Umrah for two - عمرة لشخصين", "C": 300, "D": "EUR",
                     "E": "Both - مشترك", "F": "EUR bank - حساب الأورو", "G": EX}])

# ==========================================================================
# SUMMARY (last 12 months)
# ==========================================================================
ws = WS[SUMM]
title(ws, "📅 Last 12 months - ملخص آخر 12 شهرا",
      "Automatic. Ends at the month chosen on the Dashboard.  |  تلقائي، ينتهي عند الشهر المختار في لوحة القيادة.", 12)
sum_hdr = [("A", "Month", "الشهر", 12), ("B", "Salary EUR\nreceived", "الراتب المستلم", 13), ("C", "EUR sold", "الأورو المباع", 12),
           ("D", "DZD from\nselling", "الدينار من البيع", 14), ("E", "Other income", "دخل آخر", 13), ("F", "TOTAL IN\n(DZD)", "مجموع الدخل", 14),
           ("G", "Family\nexpenses", "مصاريف العائلة", 14), ("H", "Help to\nrelatives", "مساعدة الأقارب", 13),
           ("I", "Saved for\ngoals", "الادخار", 13), ("J", "TOTAL OUT", "مجموع الخارج", 14), ("K", "NET\n(in − out)", "الصافي", 14),
           ("L", "Spending\nratio", "نسبة الإنفاق", 11)]
for c, en, ar, w in sum_hdr:
    ws.column_dimensions[c].width = w
    put(ws, f"{c}6", f"{en}\n{ar}", fnt(9, True, "FFFFFF"), TEAL, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
ws.row_dimensions[6].height = 44
put(ws, "A4", "Up to - حتى:", fnt(10, True, NAVY), align=Alignment(horizontal="right"))
put(ws, "B4", "=SEL_MONTH", fnt(10, True, NAVY), LIGHT_NAVY, "mmmm yyyy", Alignment(horizontal="center"), BORDER)
for k in range(1, 13):
    rr = 6 + k
    M = f'">="&$A{rr},{{D}},"<"&DATE(YEAR($A{rr}),MONTH($A{rr})+1,1)'
    rngm = lambda d: M.replace("{D}", d)
    cells = {
        "A": (f"=DATE(YEAR(SEL_MONTH),MONTH(SEL_MONTH)-12+{k},1)", FMT_MONTH),
        "B": (f"=SUMIFS(S_EUR,S_MONTH,{rngm('S_MONTH')})", FMT_EUR),
        "C": (f'=SUMIFS(E_AMT,E_DATE,{rngm("E_DATE")},E_CUR,"<>USD")', FMT_EUR),
        "D": (f"=SUMIFS(E_DZD,E_DATE,{rngm('E_DATE')})", FMT_DZD),
        "E": (f"=SUMIFS(F_AMT,F_TYPE,TYPE_INCOME,F_DATE,{rngm('F_DATE')})", FMT_DZD),
        "F": (f"=D{rr}+E{rr}", FMT_DZD),
        "G": (f'=SUMIFS(F_AMT,F_TYPE,"<>"&TYPE_INCOME,F_DATE,{rngm("F_DATE")})', FMT_DZD),
        "H": (f"=SUMIFS(RL_AMT,RL_DATE,{rngm('RL_DATE')})", FMT_DZD),
        "I": (f"=SUMIFS(SV_DZD,SV_DATE,{rngm('SV_DATE')})", FMT_DZD),
        "J": (f"=G{rr}+H{rr}+I{rr}", FMT_DZD),
        "K": (f"=F{rr}-J{rr}", FMT_DZD),
        "L": (f'=IF(F{rr}>0,(G{rr}+H{rr})/F{rr},"")', "0%"),
    }
    for c, (f, fmt) in cells.items():
        bold = c in ("F", "J", "K")
        put(ws, f"{c}{rr}", f, fnt(10, bold), AUTO_FILL if k != 12 else LIGHT_NAVY, fmt, border=BORDER)
put(ws, "A19", "TOTAL - المجموع", fnt(10, True, "FFFFFF"), NAVY, border=BORDER)
for c in "BCDEFGHIJK":
    put(ws, f"{c}19", f"=SUM({c}7:{c}18)", fnt(10, True, "FFFFFF"), NAVY, FMT_EUR if c in "BC" else FMT_DZD, border=BORDER)
put(ws, "L19", '=IF(F19>0,(G19+H19)/F19,"")', fnt(10, True, "FFFFFF"), NAVY, "0%", border=BORDER)
put(ws, "A20", "Monthly average - المتوسط الشهري", fnt(9, True, NAVY), LIGHT_NAVY, border=BORDER)
for c in "BCDEFGHIJK":
    put(ws, f"{c}20", f"=AVERAGE({c}7:{c}18)", fnt(9, True, NAVY), LIGHT_NAVY, FMT_EUR if c in "BC" else FMT_DZD, border=BORDER)
put(ws, "L20", None, fill_=LIGHT_NAVY, border=BORDER)
ws.conditional_formatting.add("K7:K18", CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED, bold=True), fill=fill("FDE2E1")))
link(ws, "A3", DASH, "← Dashboard\nالرئيسية", 9)
ws.freeze_panes = "B7"
ws.sheet_view.showGridLines = False

# ==========================================================================
# ZAKAT
# ==========================================================================
ws = WS[ZAK]
title(ws, "🌙 Zakat calculator - حاسبة الزكاة",
      "Simplified calculator (2.5% of wealth held one lunar year above the nisab of 85 g of gold). Ask a trusted imam for your own case.  |  "
      "حاسبة مبسطة: 2.5% من المال الذي بلغ النصاب (85 غ ذهب) وحال عليه الحول. استشر إماما ثقة.", 3)
ws.column_dimensions["A"].width = 50
ws.column_dimensions["B"].width = 20
ws.column_dimensions["C"].width = 60
zrows = [
    ("§", "Your wealth - أموالك"),
    ("Zakat date (one lunar year) - تاريخ حولان الحول", dt.date(2027, 3, 1), "in", FMT_DATE, "Example date - مثال"),
    ("Cash at home (DZD) - النقود في البيت", 0, "in", FMT_DZD, ""),
    ("CCP / bank account (DZD) - الحساب البريدي / البنكي", 0, "in", FMT_DZD, ""),
    ("EUR you hold - الأورو الذي تملكه", "=MAX(0,EUR_BALANCE)", "in", FMT_EUR, "Filled from Salary − Exchange. Type over it with the real amount. - اكتب المبلغ الحقيقي"),
    ("USD you hold - الدولار", 0, "in", FMT_EUR, ""),
    ("Gold kept for saving (grams, 24k) - ذهب الادخار (غرام)", 0, "in", "0.0", "Maliki view (Algeria): no zakat on jewelry that is worn. - الحلي الملبوس لا زكاة فيه عند المالكية"),
    ("Gold price per gram (DZD) - سعر غرام الذهب", 18000, "key", FMT_DZD,
     "≈17,350–18,100 DZD/g 24k (Aug 2026, goldrate24 at official rate). Ask a jeweler for today's price. - اسأل الصائغ"),
    ("Money people owe you (will come back) - ديون لك مرجوة", "=MAX(0,OWED_ME_DZD)", "in", FMT_DZD, "From Debts. Type over it if some will not come back."),
    ("Trade goods / other (DZD) - عروض التجارة / أخرى", 0, "in", FMT_DZD, ""),
    ("§", "Calculation - الحساب"),
    ("EUR value in DZD - قيمة الأورو", "=B9*RATE_EUR", "auto", FMT_DZD, "At today's square rate"),
    ("USD value in DZD - قيمة الدولار", "=B10*RATE_USD", "auto", FMT_DZD, ""),
    ("Gold value - قيمة الذهب", "=B11*B12", "auto", FMT_DZD, ""),
    ("Total wealth - مجموع الأموال", "=B7+B8+B17+B18+B19+B13+B14", "auto", FMT_DZD, ""),
    ("Debts you must pay now - ديون عليك", "=MAX(0,I_OWE_DZD)", "in", FMT_DZD, "From Debts (I owe)."),
    ("Net wealth for zakat - الوعاء الزكوي", "=MAX(0,B20-B21)", "auto", FMT_DZD, ""),
    ("Nisab = 85 g gold - النصاب", "=85*B12", "auto", FMT_DZD, ""),
    ("Reached nisab? - هل بلغ النصاب؟", '=IF(AND(B23>0,B22>=B23),"Yes - نعم","No - لا")', "auto", None, ""),
    ("ZAKAT DUE (2.5%) - الزكاة الواجبة", '=IF(AND(B23>0,B22>=B23),B22*0.025,0)', "result", FMT_DZD_U, ""),
    ("Zakat in EUR - الزكاة بالأورو", '=IF(RATE_EUR>0,B25/RATE_EUR,0)', "auto", FMT_EUR_U, ""),
]
r = 5
for item in zrows:
    if item[0] == "§":
        if r > 5:
            r += 1
        ws.merge_cells(f"A{r}:C{r}")
        put(ws, f"A{r}", item[1], fnt(11, True, "FFFFFF"), GOLD, align=Alignment(indent=1, vertical="center"))
        ws.row_dimensions[r].height = 22
        r += 1
        continue
    label, val, kind, fmt, note = item
    put(ws, f"A{r}", label, fnt(10, kind == "result"), border=BORDER)
    if kind == "in":
        put(ws, f"B{r}", val, fnt(10, True, BLUE_IN), fmt=fmt, align=Alignment(horizontal="center"), border=BORDER)
    elif kind == "key":
        put(ws, f"B{r}", val, fnt(10, True, BLUE_IN), YELLOW, fmt, Alignment(horizontal="center"), BORDER)
    elif kind == "result":
        put(ws, f"B{r}", val, fnt(13, True, "FFFFFF"), GREEN, fmt, Alignment(horizontal="center"), BORDER)
        ws[f"A{r}"].fill = fill("E6F4EA")
    else:
        put(ws, f"B{r}", val, fnt(10), AUTO_FILL, fmt, Alignment(horizontal="center"), BORDER)
    put(ws, f"C{r}", note, fnt(8, False, GRAY_TXT, italic=True), align=Alignment(wrap_text=True, vertical="center"))
    r += 1
ws.sheet_view.showGridLines = False

# ==========================================================================
# DASHBOARD
# ==========================================================================
ws = WS[DASH]
ws.sheet_view.showGridLines = False
ws.sheet_view.zoomScale = 85
widths = {"A": 2, "E": 2, "I": 2, "M": 2, "Q": 2}
for i in range(1, 18):
    c = get_column_letter(i)
    ws.column_dimensions[c].width = widths.get(c, 14)
ws.column_dimensions["R"].hidden = True
ws.column_dimensions["S"].hidden = True

ws.merge_cells("B1:P1")
put(ws, "B1", "💰  Personal Finance — Aboubakr & Bouchra   |   المالية الشخصية — أبوبكر و بشرى",
    fnt(18, True, "FFFFFF"), NAVY, align=Alignment(horizontal="center", vertical="center"))
ws.row_dimensions[1].height = 42
put(ws, "B2", "Today - اليوم", fnt(9, True, GRAY_TXT), align=Alignment(horizontal="right", vertical="center"))
put(ws, "C2", "=TODAY()", fnt(11, True, NAVY), fmt=FMT_DATE, align=Alignment(horizontal="center", vertical="center"))
put(ws, "F2", "Month - الشهر  ▶", fnt(9, True, GRAY_TXT), align=Alignment(horizontal="right", vertical="center"))
ws.merge_cells("G2:H2")
put(ws, "G2", "=DATE(YEAR(TODAY()),MONTH(TODAY()),1)", fnt(11, True, BLUE_IN), YELLOW, "mmmm yyyy",
    Alignment(horizontal="center", vertical="center"), BORDER)
ws["H2"].border = BORDER
comment(ws, "G2", "Type any date of a month (e.g. 01/10/2026) to see that month everywhere. Delete it and type =TODAY() to come back.\n"
                  "اكتب أي تاريخ من شهر لرؤية ذلك الشهر في كل الأوراق.")
define("SEL_MONTH", DASH, "G2")
ws.merge_cells("J2:P2")
put(ws, "J2", '=IF(RATE_DATE=0,"⚠ Add today\'s rate in the Rates sheet - أضف سعر اليوم",IF(TODAY()-RATE_DATE>=1,'
              '"⚠ Last rate is "&(TODAY()-RATE_DATE)&" day(s) old — update it - حدّث السعر","✔ Rate updated today - السعر محدث اليوم"))',
    fnt(10, True, ORANGE), align=Alignment(horizontal="center", vertical="center"))
ws.conditional_formatting.add("J2", FormulaRule(formula=['LEFT($J$2,1)="✔"'], font=Font(color=GREEN, bold=True)))
ws.row_dimensions[2].height = 26

# navigation
nav = [("B", RATES, "💱 Rates\nالأسعار"), ("C", SAL, "💵 Salary\nالراتب"), ("D", EXC, "🔄 Exchange\nالصرف"),
       ("F", DEBT, "🤝 Debts\nالديون"), ("G", PAY, "💸 Payments\nالتسديد"), ("H", ZAK, "🌙 Zakat\nالزكاة"),
       ("J", FAM, "👨‍👩 Family\nالعائلة"), ("K", BUD, "📊 Budget\nالميزانية"), ("L", REL, "🏡 Relatives\nالأقارب"),
       ("N", PLAN, "🎯 Plans\nالخطط"), ("O", SAV, "🏦 Savings\nالادخار"), ("P", SUMM, "📅 Summary\nالملخص")]
for c, sh, txt in nav:
    link(ws, f"{c}3", sh, txt, 9)
    ws[f"{c}3"].fill = fill("EAF1FB")
    ws[f"{c}3"].border = BORDER
link(ws, "B4", SET, "⚙ Settings\nالإعدادات", 9)
link(ws, "C4", GUIDE, "📖 Guide\nالدليل", 9)
for c in ("B4", "C4"):
    ws[c].fill = fill("F1F1F1")
    ws[c].border = BORDER
put(ws, "D4", "← start here - ابدأ هنا", fnt(8, False, GRAY_TXT, italic=True), align=Alignment(vertical="center"))
ws.row_dimensions[3].height = 32
ws.row_dimensions[4].height = 32


def card(r, c0, label, value_f, fmt, sub_f, color):
    cs = [get_column_letter(col(c0) + i) for i in range(3)]
    for rr in range(r, r + 4):
        for c in cs:
            cell = ws[f"{c}{rr}"]
            cell.fill = fill(CARD_FILL)
            top = Side(style="thick", color=color) if rr == r else None
            bottom = Side(style="thin", color="D0D5DD") if rr == r + 3 else None
            left = Side(style="thin", color="D0D5DD") if c == cs[0] else None
            right = Side(style="thin", color="D0D5DD") if c == cs[2] else None
            cell.border = Border(top=top, bottom=bottom, left=left, right=right)
    ws.merge_cells(f"{cs[0]}{r}:{cs[2]}{r}")
    put(ws, f"{cs[0]}{r}", label, fnt(9, True, GRAY_TXT), CARD_FILL, align=Alignment(horizontal="center", vertical="center", wrap_text=True))
    ws[f"{cs[0]}{r}"].border = Border(top=Side(style="thick", color=color), left=Side(style="thin", color="D0D5DD"))
    ws.merge_cells(f"{cs[0]}{r + 1}:{cs[2]}{r + 2}")
    put(ws, f"{cs[0]}{r + 1}", value_f, fnt(20, True, color), CARD_FILL, fmt, Alignment(horizontal="center", vertical="center"))
    ws.merge_cells(f"{cs[0]}{r + 3}:{cs[2]}{r + 3}")
    put(ws, f"{cs[0]}{r + 3}", sub_f, fnt(9, False, GRAY_TXT, italic=True), CARD_FILL, align=Alignment(horizontal="center", vertical="center", wrap_text=True))
    ws.row_dimensions[r].height = 30
    ws.row_dimensions[r + 3].height = 22


SM = q(SUMM)
card(6, "B", "Today's EUR price (square)\nسعر الأورو اليوم (السكوار)", "=RATE_EUR", '#,##0.00 "DZD"',
     '=IF(RATE_EUR_PREV=0,"first price - أول سعر",IF(RATE_EUR>=RATE_EUR_PREV,"▲ +","▼ ")&FIXED(RATE_EUR-RATE_EUR_PREV,2)&" DZD vs previous day - عن الأمس")', GREEN)
card(6, "F", "Salary this month in DZD\nالراتب بالدينار (سعر اليوم)", "=SALARY_DZD", FMT_DZD_U,
     '=FIXED(SALARY_USD,0)&" $  →  "&FIXED(SALARY_EUR,2)&" €  →  DZD"', NAVY)
card(6, "J", "EUR still in bank\nالأورو المتبقي في البنك", "=EUR_BALANCE", FMT_EUR_U,
     '="≈ "&FIXED(EUR_BALANCE*RATE_EUR,0)&" DZD at today\'s price - بسعر اليوم"', "1565C0")
card(6, "N", "Family spending this month\nمصاريف العائلة هذا الشهر", f"={SM}$G$18", FMT_DZD_U,
     f'=IF(SUM({q(BUD)}$B$7:$B$31)>0,"Budget used - من الميزانية: "&FIXED({SM}$G$18/SUM({q(BUD)}$B$7:$B$31)*100,0)&"%","Set a budget - حدد ميزانية")', "6A1B9A")
card(11, "B", "I owe (DZD)\nعليّ للناس", "=I_OWE_DZD", FMT_DZD_U,
     '=COUNTIFS(D_TYPE,DT_OWE,D_STATUS,"*Overdue*")&" overdue - متأخر   |   "&COUNTIFS(D_TYPE,DT_OWE,D_STATUS,"<>*Paid*",D_STATUS,"?*")&" open - مفتوح"', RED)
card(11, "F", "Owed to me (DZD)\nلي عند الناس", "=OWED_ME_DZD", FMT_DZD_U,
     '=COUNTIFS(D_TYPE,DT_OWED,D_STATUS,"*Overdue*")&" overdue - متأخر   |   "&COUNTIFS(D_TYPE,DT_OWED,D_STATUS,"<>*Paid*",D_STATUS,"?*")&" open - مفتوح"', ORANGE)
card(11, "J", "Saved for goals\nالمدخرات للأهداف", "=SAVINGS_DZD", FMT_DZD_U,
     '=IF(GOALS_TARGET>0,FIXED(SAVINGS_DZD/GOALS_TARGET*100,0)&"% of "&FIXED(GOALS_TARGET,0)&" DZD - من الأهداف","Add a goal in Plans - أضف هدفا")', "2E7D32")
card(11, "N", "Net this month (in − out)\nصافي الشهر", f"={SM}$K$18", FMT_DZD_U,
     f'="In - دخل "&FIXED({SM}$F$18,0)&"   |   Out - خرج "&FIXED({SM}$J$18,0)', NAVY)
ws.conditional_formatting.add("N12", CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED, bold=True, size=20)))


def panel(r, c0, head, rows, color):
    c1, c2, c3 = [get_column_letter(col(c0) + i) for i in range(3)]
    ws.merge_cells(f"{c1}{r}:{c3}{r}")
    put(ws, f"{c1}{r}", head, fnt(10, True, "FFFFFF"), color, align=Alignment(horizontal="center", vertical="center"))
    ws.row_dimensions[r].height = 22
    for i, (label, f, fmt, kind) in enumerate(rows):
        rr = r + 1 + i
        ws.merge_cells(f"{c1}{rr}:{c2}{rr}")
        put(ws, f"{c1}{rr}", label, fnt(9, kind == "bold"), "FFFFFF", align=Alignment(vertical="center", indent=1), border=BORDER)
        ws[f"{c2}{rr}"].border = BORDER
        if kind == "in":
            put(ws, f"{c3}{rr}", f, fnt(10, True, BLUE_IN), YELLOW, fmt, Alignment(horizontal="right"), BORDER)
        else:
            put(ws, f"{c3}{rr}", f, fnt(10, kind == "bold", NAVY if kind == "bold" else "000000"),
                LIGHT_NAVY if kind == "bold" else AUTO_FILL, fmt, Alignment(horizontal="right"), BORDER)


panel(16, "B", "📆 This month - هذا الشهر", [
    ("Salary received (EUR) - الراتب المستلم", f"={SM}$B$18", FMT_EUR, ""),
    ("EUR sold - الأورو المباع", f"={SM}$C$18", FMT_EUR, ""),
    ("DZD from selling - الدينار من البيع", f"={SM}$D$18", FMT_DZD, ""),
    ("Other income - دخل آخر", f"={SM}$E$18", FMT_DZD, ""),
    ("Family expenses - مصاريف العائلة", f"={SM}$G$18", FMT_DZD, ""),
    ("Help to relatives - مساعدة الأقارب", f"={SM}$H$18", FMT_DZD, ""),
    ("Saved for goals - الادخار", f"={SM}$I$18", FMT_DZD, ""),
    ("NET - الصافي", f"={SM}$K$18", FMT_DZD, "bold"),
], NAVY)
panel(16, "F", "💵 Salary calculator - حاسبة الراتب", [
    ("Salary (USD) - الراتب بالدولار", "=SALARY_USD", FMT_USD_U, ""),
    ("USD → EUR rate - سعر التحويل", "=USD_EUR", FMT_RATE4, ""),
    ("Bank fee - عمولة البنك", "=BANK_FEE", "0.00%", ""),
    ("Salary (EUR) - بالأورو", "=SALARY_EUR", FMT_EUR, ""),
    ("Square price EUR → DZD - سعر السكوار", "=RATE_EUR", FMT_RATE, ""),
    ("Salary in DZD (square) - بالدينار", "=SALARY_DZD", FMT_DZD, "bold"),
    ("At official bank rate - بالسعر الرسمي", "=SALARY_EUR*OFFICIAL_EUR", FMT_DZD, ""),
    ("Extra from square - الفرق لصالحك", "=SALARY_DZD-SALARY_EUR*OFFICIAL_EUR", FMT_DZD, ""),
], NAVY)
panel(16, "J", "🧮 Converter - محول العملات (type in yellow)", [
    ("EUR amount - مبلغ بالأورو", 1000, FMT_EUR, "in"),
    ("→ DZD if you sell - بالدينار", "=L17*RATE_EUR", FMT_DZD, "bold"),
    ("DZD amount - مبلغ بالدينار", 100000, FMT_DZD, "in"),
    ("→ EUR if you buy - بالأورو", "=IF(RATE_EUR_BUY>0,L19/RATE_EUR_BUY,0)", FMT_EUR, "bold"),
    ("USD amount - مبلغ بالدولار", 100, FMT_EUR, "in"),
    ("→ EUR at the bank - بالأورو", "=L21*USD_EUR", FMT_EUR, ""),
    ("→ DZD at the square - بالدينار", "=L21*RATE_USD", FMT_DZD, "bold"),
    ("100 € = DZD", "=100*RATE_EUR", FMT_DZD, ""),
], "1565C0")
RD, RE = "R_DATE", "R_EUR"
panel(16, "N", "📈 EUR price stats - إحصائيات سعر الأورو", [
    ("Now, you sell - الآن (بيع)", "=RATE_EUR", FMT_RATE, "bold"),
    ("Now, you buy - الآن (شراء)", "=RATE_EUR_BUY", FMT_RATE, ""),
    ("Change vs previous day - التغير", "=IF(RATE_EUR_PREV=0,0,RATE_EUR-RATE_EUR_PREV)", FMT_CHG, ""),
    ("7-day average - متوسط 7 أيام", f'=IFERROR(AVERAGEIFS({RE},{RD},">"&(RATE_DATE-7),{RD},"<="&RATE_DATE),0)', FMT_RATE, ""),
    ("30-day average - متوسط 30 يوما", f'=IFERROR(AVERAGEIFS({RE},{RD},">"&(RATE_DATE-30),{RD},"<="&RATE_DATE),0)', FMT_RATE, ""),
    ("30-day lowest - أدنى سعر", f'=IF(RATE_DATE=0,0,SUMPRODUCT(MIN({RE}+(({RD}<=RATE_DATE-30)+({RD}>RATE_DATE)+({RE}=""))*1000000)))', FMT_RATE, ""),
    ("30-day highest - أعلى سعر", f'=SUMPRODUCT(MAX({RE}*({RD}>RATE_DATE-30)*({RD}<=RATE_DATE)))', FMT_RATE, ""),
    ("Square vs official - الفرق مع الرسمي", "=PREMIUM", FMT_PCT, ""),
], GREEN)

# upcoming debts
ws.merge_cells("B26:H26")
put(ws, "B26", "⏰ Next debts to pay / collect - الديون القادمة", fnt(10, True, "FFFFFF"), RED, align=Alignment(horizontal="center", vertical="center"))
ws.merge_cells("J26:P26")
put(ws, "J26", "🎯 Goals progress - تقدم الأهداف", fnt(10, True, "FFFFFF"), "2E7D32", align=Alignment(horizontal="center", vertical="center"))
ws.row_dimensions[26].height = 22
for c, txt in (("B", "Person - الشخص"), ("C", "Type - النوع"), ("D", "Remaining DZD\nالمتبقي"), ("F", "Due - الموعد"),
               ("G", "Days left\nالأيام"), ("H", "Status - الحالة"),
               ("J", "Goal - الهدف"), ("K", "Target - المطلوب"), ("L", "Saved - المدخر"), ("N", "Progress - التقدم"),
               ("O", "Per month\nشهريا"), ("P", "Status - الحالة")):
    put(ws, f"{c}27", txt, fnt(8, True, NAVY), LIGHT_NAVY, align=Alignment(horizontal="center", vertical="center", wrap_text=True), border=BORDER)
for c in ("E", "M"):
    ws[f"{c}27"].fill = fill(LIGHT_NAVY)
ws.row_dimensions[27].height = 28
for k in range(1, 7):
    rr = 27 + k
    ws[f"R{rr}"] = f'=IFERROR(MATCH(SMALL(D_KEY,{k}),D_KEY,0),"")'
    ws[f"S{rr}"] = f'=IFERROR(MATCH(SMALL(G_KEY,{k}),G_KEY,0),"")'
    first_msg = '"✔ No open debts - لا توجد ديون"' if k == 1 else '""'
    first_goal = '"Add goals in Plans - أضف أهدافا"' if k == 1 else '""'
    row_cells = {
        "B": (f'=IF($R{rr}="",{first_msg},INDEX(D_PERSON,$R{rr}))', None),
        "C": (f'=IF($R{rr}="","",IF(INDEX(D_TYPE,$R{rr})=DT_OWE,"I owe - عليّ","Owed to me - لي"))', None),
        "D": (f'=IF($R{rr}="","",INDEX(D_REMDZD,$R{rr}))', FMT_DZD),
        "F": (f'=IF($R{rr}="","",IF(N(INDEX(D_DUE,$R{rr}))=0,"-",INDEX(D_DUE,$R{rr})))', FMT_DATE),
        "G": (f'=IF($R{rr}="","",INDEX(D_DAYS,$R{rr}))', FMT_INT),
        "H": (f'=IF($R{rr}="","",INDEX(D_STATUS,$R{rr}))', None),
        "J": (f'=IF($S{rr}="",{first_goal},INDEX(G_NAME,$S{rr}))', None),
        "K": (f'=IF($S{rr}="","",INDEX(G_TARGET,$S{rr}))', FMT_DZD),
        "L": (f'=IF($S{rr}="","",INDEX(G_SAVED,$S{rr}))', FMT_DZD),
        "N": (f'=IF($S{rr}="","",REPT("█",ROUND(10*N(INDEX(G_PROG,$S{rr})),0))&REPT("░",10-ROUND(10*N(INDEX(G_PROG,$S{rr})),0))'
              f'&" "&ROUND(100*N(INDEX(G_PROG,$S{rr})),0)&"%")', None),
        "O": (f'=IF($S{rr}="","",INDEX(G_MONTHLY,$S{rr}))', FMT_DZD),
        "P": (f'=IF($S{rr}="","",INDEX(G_STATUS,$S{rr}))', None),
    }
    for c, (f, fmt) in row_cells.items():
        put(ws, f"{c}{rr}", f, fnt(9), "FFFFFF", fmt,
            Alignment(horizontal="left" if c in ("B", "J", "H", "P", "C") else "center", vertical="center", shrink_to_fit=c in ("B", "J", "H", "P")),
            BORDER)
    ws[f"E{rr}"].border = BORDER
    ws[f"M{rr}"].border = BORDER
ws.conditional_formatting.add("B28:H33", FormulaRule(formula=['ISNUMBER(SEARCH("Overdue",$H28))'], fill=fill("FDE2E1"), font=Font(color=RED, bold=True)))
ws.conditional_formatting.add("B28:H33", FormulaRule(formula=['ISNUMBER(SEARCH("Due soon",$H28))'], fill=fill("FFF1D6"), font=Font(color=ORANGE, bold=True)))
for rr in range(28, 34):
    ws[f"N{rr}"].font = fnt(8, True, GREEN)
color_change(ws, "P19")
ws.conditional_formatting.add("P28:P33", FormulaRule(formula=['ISNUMBER(SEARCH("Behind",$P28))'], font=Font(color=RED, bold=True)))

ws.merge_cells("B35:P35")
put(ws, "B35", "📊 Charts - الرسوم البيانية", fnt(10, True, "FFFFFF"), NAVY, align=Alignment(horizontal="center", vertical="center"))
ws.row_dimensions[35].height = 22


# ==========================================================================
# CHARTS
# ==========================================================================
def style_chart(ch, title_text):
    ch.title = title_text
    ch.roundedCorners = False
    if ch.legend is not None:
        ch.legend.overlay = False
    ch.x_axis.delete = False
    ch.y_axis.delete = False


def rate_chart():
    rs = WS[RATES]
    ch = LineChart()
    style_chart(ch, "EUR → DZD, last 30 days\nسعر الأورو آخر 30 يوما")
    ch.add_data(Reference(rs, min_col=15, min_row=5, max_row=35), titles_from_data=True)
    ch.set_categories(Reference(rs, min_col=14, min_row=6, max_row=35))
    ch.y_axis.crossAx = 500
    ch.x_axis = DateAxis(crossAx=100)
    ch.x_axis.number_format = "dd/mm"
    ch.x_axis.majorTimeUnit = "days"
    ch.x_axis.delete = False
    ch.y_axis.number_format = "#,##0"
    ch.legend = None
    s = ch.series[0]
    s.graphicalProperties.line.solidFill = GREEN
    s.graphicalProperties.line.width = 28000
    s.smooth = False
    ch.height, ch.width = 8.5, 15.5
    return ch


def budget_chart():
    bs = WS[BUD]
    ch = BarChart()
    ch.type = "bar"
    style_chart(ch, "Budget vs spent this month\nالميزانية مقابل المصاريف")
    ch.add_data(Reference(bs, min_col=2, min_row=6, max_row=22), titles_from_data=True)
    ch.add_data(Reference(bs, min_col=6, min_row=6, max_row=22), titles_from_data=True)
    ch.set_categories(Reference(bs, min_col=1, min_row=7, max_row=22))
    ch.x_axis.scaling.orientation = "maxMin"
    ch.y_axis.number_format = "#,##0"
    ch.series[0].tx = SeriesLabel(v="Budget - الميزانية")
    ch.series[1].tx = SeriesLabel(v="Spent - المصروف")
    ch.y_axis.crosses = "max"
    ch.series[0].graphicalProperties.solidFill = "B0BEC5"
    ch.series[0].graphicalProperties.line.noFill = True
    ch.series[1].graphicalProperties.solidFill = "6A1B9A"
    ch.series[1].graphicalProperties.line.noFill = True
    ch.gapWidth = 60
    ch.legend.position = "b"
    ch.height, ch.width = 14, 15.5
    return ch


def months_chart(width=32.5):
    ss = WS[SUMM]
    ch = BarChart()
    ch.type = "col"
    style_chart(ch, "Last 12 months: money in vs out\nآخر 12 شهرا: الدخل والمصاريف")
    for cidx, color, label in ((6, "1565C0", "Money in - الدخل"), (7, "6A1B9A", "Family expenses - مصاريف العائلة"),
                               (8, ORANGE, "Help to relatives - مساعدة الأقارب"), (9, "2E7D32", "Saved - الادخار")):
        ch.add_data(Reference(ss, min_col=cidx, min_row=7, max_row=18), titles_from_data=False)
        ch.series[-1].tx = SeriesLabel(v=label)
        ch.series[-1].graphicalProperties.solidFill = color
        ch.series[-1].graphicalProperties.line.noFill = True
    ch.set_categories(Reference(ss, min_col=1, min_row=7, max_row=18))
    ch.x_axis.number_format = "mmm yy"
    ch.y_axis.number_format = "#,##0"
    ch.gapWidth = 80
    ch.legend.position = "b"
    ch.height, ch.width = 10, width
    return ch


WS[DASH].add_chart(rate_chart(), "B37")
WS[DASH].add_chart(budget_chart(), "J37")
WS[DASH].add_chart(months_chart(), "B66")
WS[RATES].add_chart(rate_chart(), "R5")
WS[BUD].add_chart(budget_chart(), "K6")
WS[SUMM].add_chart(months_chart(30), "A23")

# ==========================================================================
# GUIDE
# ==========================================================================
ws = WS[GUIDE]
ws.sheet_view.showGridLines = False
ws.column_dimensions["A"].width = 3
ws.column_dimensions["B"].width = 24
ws.column_dimensions["C"].width = 62
ws.column_dimensions["D"].width = 62
ws.merge_cells("A1:D1")
put(ws, "A1", "📖 Guide - الدليل", fnt(16, True, "FFFFFF"), NAVY, align=Alignment(horizontal="left", vertical="center", indent=1))
ws.row_dimensions[1].height = 34
link(ws, "B2", DASH, "← Dashboard - الرئيسية", 9)
ws.row_dimensions[2].height = 24
AR = Alignment(horizontal="right", vertical="top", wrap_text=True, readingOrder=2)
EN = Alignment(horizontal="left", vertical="top", wrap_text=True)
r = 4


def g_head(text):
    global r
    ws.merge_cells(f"B{r}:D{r}")
    put(ws, f"B{r}", text, fnt(12, True, "FFFFFF"), TEAL, align=Alignment(vertical="center", indent=1))
    ws.row_dimensions[r].height = 24
    r += 1


def g_row(key, en, ar, key_fill=None, h=None):
    global r
    put(ws, f"B{r}", key, fnt(10, True, NAVY), key_fill, align=Alignment(vertical="top", wrap_text=True), border=BORDER)
    put(ws, f"C{r}", en, fnt(10), align=EN, border=BORDER)
    put(ws, f"D{r}", ar, fnt(10), align=AR, border=BORDER)
    lines = max(len(en) / 70, len(ar) / 70, 1) + en.count("\n")
    ws.row_dimensions[r].height = h or max(18, 15 * (int(lines) + 1))
    r += 1


g_head("1. Start here - ابدأ من هنا")
g_row("Step 1 - الخطوة 1", "Open Settings: check your salary (2,700 USD), your names and the rates.",
      "افتح الإعدادات: تأكد من الراتب (2700 دولار)، الأسماء والأسعار.")
g_row("Step 2 - الخطوة 2", "Delete the example rows (marked 'Example - مثال') in every sheet: select the blue cells of those rows and press Delete.",
      "احذف أسطر الأمثلة (المكتوب فيها 'مثال') في كل ورقة: حدد الخلايا الزرقاء واضغط Delete.")
g_row("Every day - كل يوم", "Rates: add one line with the date and the square price of the euro. The whole workbook updates.",
      "الأسعار: أضف سطرا بالتاريخ وسعر الأورو في السكوار. كل الملف يتحدث تلقائيا.")
g_row("Salary day - يوم الراتب", "Salary: type the month (01/12/2026). USD, rate and EUR fill themselves. Type the real EUR from your bank if you have it.",
      "الراتب: اكتب الشهر فقط. الدولار والسعر والأورو تمتلئ وحدها. اكتب المبلغ الحقيقي من البنك إن وجد.")
g_row("When you sell - عند البيع", "Exchange: one line each time you sell EUR at the square (amount + price you got).",
      "الصرف: سطر لكل عملية بيع أورو في السكوار (المبلغ + السعر الذي أخذته).")
g_row("Every expense - كل مصروف", "Family: date, who, category, amount. Relatives: money you give to your brother, mother, wife's mother...",
      "العائلة: التاريخ، من، الفئة، المبلغ. الأقارب: المال الذي تعطيه لأخيك، أمك، أم زوجتك...")
g_row("Loans - السلف", "Debts: who, how much, when you plan to give it back. Payments: each time money is paid back.",
      "الديون: من، كم، ومتى تخطط لإرجاعه. التسديد: كل مرة يرجع فيها مال.")
g_row("Goals - الأهداف", "Plans: your goals with target amount and date. Savings: money you put aside for a goal.",
      "الخطط: أهدافك بالمبلغ والتاريخ. الادخار: المال الذي تضعه جانبا لهدف.")
g_row("Look - شاهد", "Dashboard: everything in one page. Change the yellow month at the top to see another month.",
      "لوحة القيادة: كل شيء في صفحة واحدة. غيّر الشهر الأصفر في الأعلى لرؤية شهر آخر.")
r += 1
g_head("2. Colors - الألوان")
g_row("Blue text", "You type here (inputs).", "نص أزرق: هنا تكتب أنت.")
ws[f"B{r - 1}"].font = fnt(10, True, BLUE_IN)
g_row("Gray cell", "Automatic formula. Do not type here.", "خلية رمادية: معادلة تلقائية، لا تكتب فيها.", AUTO_FILL)
g_row("Yellow cell", "Important setting you can change (month, salary, converter amounts).", "خلية صفراء: إعداد مهم يمكنك تغييره.", YELLOW)
g_row("⚙ Green header", "Column is calculated automatically.", "عنوان أخضر ⚙: العمود يحسب تلقائيا.")
ws[f"B{r - 1}"].fill = fill(TEAL)
ws[f"B{r - 1}"].font = fnt(10, True, "FFFFFF")
g_row("Navy header", "Column for you to fill.", "عنوان أزرق داكن: عمود تملؤه أنت.")
ws[f"B{r - 1}"].fill = fill(NAVY)
ws[f"B{r - 1}"].font = fnt(10, True, "FFFFFF")
r += 1
g_head("3. The sheets - الأوراق")
for sh, en, ar in [
    (DASH, "Summary cards, this month, salary calculator, converter, rate stats, next debts, goals, charts.",
     "بطاقات ملخصة، هذا الشهر، حاسبة الراتب، محول العملات، إحصائيات السعر، الديون القادمة، الأهداف، رسوم."),
    (RATES, "Daily square prices (EUR & USD) with change ▲▼ and a 30-day chart.", "أسعار السكوار اليومية مع التغير ▲▼ ورسم 30 يوما."),
    (SAL, "Each month: 2,700 USD → EUR (bank) → value in DZD, square gain vs the official rate.", "كل شهر: 2700 دولار ← أورو ← قيمته بالدينار، والربح مقارنة بالسعر الرسمي."),
    (EXC, "Each sale of EUR/USD for DZD, compared with the market price of that day.", "كل عملية بيع أورو/دولار، مقارنة بسعر السوق ذلك اليوم."),
    (DEBT, "Loans: person, phone, amount, currency, planned return date, remaining, status (overdue / due soon).", "السلف: الشخص، الهاتف، المبلغ، العملة، تاريخ الإرجاع، المتبقي، الحالة."),
    (PAY, "Repayments linked to a debt (choose it from the list).", "الدفعات المرتبطة بكل دين (اختره من القائمة)."),
    (FAM, "House expenses and extra income of Aboubakr & Bouchra.", "مصاريف البيت والدخل الإضافي لأبوبكر و بشرى."),
    (BUD, "Monthly budget per category vs what you really spent (per person).", "الميزانية الشهرية لكل فئة مقابل المصروف الحقيقي (لكل شخص)."),
    (REL, "Help for brother, mother, wife's mother... with totals by relation.", "مساعدة الأخ، الأم، أم الزوجة... مع المجموع حسب القرابة."),
    (PLAN, "Future goals: target, date, progress bar, how much to save per month, on track or behind.", "أهداف المستقبل: المبلغ، التاريخ، التقدم، كم تدخر شهريا، في الطريق أم متأخر."),
    (SAV, "Money put aside for each goal, in DZD or EUR.", "المال المدخر لكل هدف، بالدينار أو الأورو."),
    (SUMM, "Last 12 months: income, expenses, help, savings and net.", "آخر 12 شهرا: الدخل، المصاريف، المساعدة، الادخار والصافي."),
    (ZAK, "Simple zakat calculator using your EUR, cash, gold and debts.", "حاسبة زكاة بسيطة باستعمال الأورو، النقود، الذهب والديون."),
    (SET, "Salary, rates, names and all dropdown lists (you can add categories).", "الراتب، الأسعار، الأسماء وكل القوائم (يمكنك إضافة فئات)."),
]:
    put(ws, f"B{r}", None)
    link(ws, f"B{r}", sh, sh, 9)
    ws[f"B{r}"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws[f"B{r}"].border = BORDER
    put(ws, f"C{r}", en, fnt(10), align=EN, border=BORDER)
    put(ws, f"D{r}", ar, fnt(10), align=AR, border=BORDER)
    ws.row_dimensions[r].height = 30
    r += 1
r += 1
g_head("4. Does the price change by itself? - هل يتغير السعر وحده؟")
g_row("Square price\nسعر السكوار", "NO. Nobody publishes the square (black-market) price as a live feed (apps like Dinar Plus get it from the traders), "
      "so no Excel file can download it. You type it ONCE a day in Rates: date + price, 10 seconds.",
      "لا. لا يوجد أي مصدر مباشر لسعر السكوار (التطبيقات مثل دينار بلس تأخذه من الصرافين)، لذلك لا يستطيع أي ملف جلبه وحده. "
      "تكتبه مرة واحدة في اليوم في ورقة الأسعار: التاريخ + السعر، 10 ثوان.", h=62)
g_row("Then everything\nبعدها كل شيء", "After you type it, EVERYTHING updates by itself: salary in DZD, EUR in bank, EUR debts, savings, zakat, "
      "the ▲▼ change and the charts. Example: today 277 → salary 679,841 DZD. Tomorrow you type 279 → salary 684,750 DZD and change ▲ +2.00.",
      "بعد كتابته كل شيء يتحدث وحده: الراتب بالدينار، الأورو في البنك، الديون بالأورو، المدخرات، الزكاة، التغير ▲▼ والرسوم. "
      "مثال: اليوم 277 ← الراتب 679,841 دج. غدا تكتب 279 ← الراتب 684,750 دج والتغير ▲ +2.00.", h=62)
g_row("USD → EUR\nالدولار ← الأورو", "YES, automatic (official rate) in Google Sheets (phone or browser, laptop off) and in Excel for Windows. "
      "In the Excel phone app it uses the number in Settings. Your bank decides the real rate anyway: type the EUR you really received in Salary.",
      "نعم تلقائي (السعر الرسمي) في Google Sheets (الهاتف أو المتصفح والحاسوب مطفأ) وفي Excel على ويندوز. "
      "في تطبيق Excel على الهاتف يستعمل الرقم المكتوب في الإعدادات. البنك يحدد السعر الحقيقي: اكتب الأورو الذي وصلك فعلا في ورقة الراتب.", h=62)
g_row("Official EUR → DZD\nالسعر الرسمي", "Automatic in Google Sheets only. Elsewhere it uses the number in Settings (it moves slowly: update it once a month).",
      "تلقائي في Google Sheets فقط. غير ذلك يستعمل الرقم في الإعدادات (يتغير ببطء: حدّثه مرة في الشهر).", h=40)
r += 1
g_head("5. Google Sheets on your phone (laptop off) - Google Sheets على الهاتف")
g_row("Step 1\nUpload - رفع", "Open drive.google.com (or the Google Drive app) → New (+) → File upload → choose this file.",
      "افتح drive.google.com (أو تطبيق Google Drive) ← جديد (+) ← رفع ملف ← اختر هذا الملف.", h=34)
g_row("Step 2\nConvert - تحويل", "Open the file → File → Save as Google Sheets. From now on use only this new copy "
      "(it has no .XLSX label next to its name).",
      "افتح الملف ← ملف ← حفظ بتنسيق Google Sheets. من الآن استعمل هذه النسخة الجديدة فقط (بدون علامة XLSX بجانب الاسم).", h=48)
g_row("Step 3\nDates - التاريخ", "File → Settings → Locale: Algeria (or France) → Save. Then dates are day/month/year (27/11/2026).",
      "ملف ← الإعدادات ← اللغة والمنطقة: الجزائر (أو فرنسا) ← حفظ. هكذا يصبح التاريخ يوم/شهر/سنة.", h=34)
g_row("Step 4\nShare - مشاركة", "Share → type Bouchra's Gmail → Editor → Send. You both write in the same file from your phones, at the same time.",
      "مشاركة ← اكتب بريد بشرى (Gmail) ← محرر ← إرسال. تكتبان معا في نفس الملف من هاتفيكما.", h=34)
g_row("Step 5\nPhone - الهاتف", "Install the free Google Sheets app. Every morning open the Rates tab and add today's date and square price. "
      "Everything else updates at once, laptop off.",
      "ثبّت تطبيق Google Sheets المجاني. كل صباح افتح ورقة الأسعار وأضف التاريخ وسعر السكوار. كل شيء آخر يتحدث فورا والحاسوب مطفأ.", h=48)
g_row("Missing dropdown\nقائمة ناقصة", "If a list arrow does not appear: select the column → Data → Data validation → Dropdown (from a range) "
      "→ pick the list in the Settings sheet.",
      "إذا لم تظهر القائمة المنسدلة: حدد العمود ← بيانات ← التحقق من صحة البيانات ← قائمة من نطاق ← اختر القائمة من ورقة الإعدادات.", h=48)
g_row("Excel copy\nنسخة Excel", "You can always get an Excel copy: File → Download → Microsoft Excel (.xlsx).",
      "يمكنك دائما تنزيل نسخة Excel: ملف ← تنزيل ← Microsoft Excel.", h=34)
r += 1
g_head("6. Tips - نصائح")
g_row("Filters", "Click the arrow in any header to filter (one person, one category, one month). Row 4 totals follow the filter.",
      "اضغط السهم في أي عنوان للفلترة (شخص، فئة، شهر). المجموع في السطر 4 يتبع الفلتر.", h=34)
g_row("Dates", "Type dates as day/month/year (27/11/2026). The order of lines does not matter.",
      "اكتب التاريخ يوم/شهر/سنة (27/11/2026). ترتيب الأسطر غير مهم.")
g_row("New categories", "Settings → add a new item at the bottom of any list; dropdowns and the budget update.",
      "الإعدادات ← أضف عنصرا في أسفل أي قائمة، القوائم والميزانية تتحدث.")
g_row("Backup", "Google Sheets saves every change. To go back: File → Version history.",
      "Google Sheets يحفظ كل تغيير. للرجوع: ملف ← سجل النسخ.")
g_row("Sources", "Example rates: Awras / Dinar Plus (2 Nov 2026: EUR ≈ 277 DZD, USD ≈ 241 DZD at the square); Bank of Algeria via Observalgerie "
      "(16 Nov 2026: EUR ≈ 151 DZD official); Trading Economics (mid-Nov 2026: EUR ≈ 1.10 USD). Replace them with your real numbers.",
      "مصادر الأمثلة: أوراس / دينار بلس، بنك الجزائر، Trading Economics. استبدلها بأرقامك الحقيقية.", h=48)

# --------------------------------------------------------------------------
wb.active = 0
wb.calculation.fullCalcOnLoad = True
wb.save(OUT)
print("saved", OUT)
