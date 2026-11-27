# Personal Finance — Aboubakr & Bouchra · المالية الشخصية

**File:** `Personal_Finance_Aboubakr_Bouchra.xlsx`. It is bilingual (English and Arabic), has 15 sheets, and every number is a live Excel formula.

## Sheets — الأوراق

| Sheet | Purpose |
|---|---|
| Dashboard - الرئيسية | Cards (EUR price, salary in DZD, EUR in bank, spending, debts, savings, net), salary calculator, currency converter, rate stats, next debts, goals and 3 charts. Change the yellow month to see another month. |
| Rates - الأسعار | One line per day with the square price (EUR and USD). It shows the change ▲▼ against the previous day and a 30-day chart. The newest line updates the whole workbook. |
| Salary - الراتب | 2,700 USD → EUR (bank rate) → DZD value at the square, compared with the official rate. |
| Exchange - الصرف | Each time you sell EUR or USD for DZD, compared with the market price that day. |
| Debts - الديون | Loans you owe (I owe - عليّ) or are owed (Owed to me - لي): person, phone, currency, planned return date, remaining amount, and status (overdue / due soon / paid). |
| Payments - التسديد | Repayments, each linked to a debt through a dropdown. |
| Family - العائلة | Household expenses and extra income for Aboubakr & Bouchra. |
| Budget - الميزانية | Monthly budget per category against actual spending, per person. |
| Relatives - الأقارب | Help for brother, mother, wife's mother and others, with totals by relation. |
| Plans - الخطط | Future goals: target, date, progress bar, how much to save per month, and whether you are on track or behind. |
| Savings - الادخار | Money put aside for each goal, in DZD or EUR. EUR is valued at today's square price. |
| Summary - الملخص | The last 12 months of money in and out. |
| Zakat - الزكاة | A simple zakat calculator (nisab = 85 g of gold). |
| Settings - الإعدادات | Salary, USD→EUR rate (a live ECB rate in Excel for Windows), the official rate, names, and all the dropdown lists. |
| Guide - الدليل | Step-by-step instructions in English and Arabic. |

Rows marked **"Example - مثال"** are samples. Delete them before you start.

## Telegram bot

See [`bot/README.md`](bot/README.md).

## Rebuild the workbook (optional)

```bash
python tools/build_workbook.py Personal_Finance_Aboubakr_Bouchra.xlsx
```

## Sources for the example numbers

- Square rate ≈ 277 DZD/EUR and ≈ 241 DZD/USD on 2 Nov 2026 (Awras, citing the "Dinar Plus" app).
- Official rate ≈ 151 DZD/EUR on 16 Nov 2026 (Bank of Algeria, via Observalgerie).
- EUR/USD ≈ 1.10 in mid-November 2026 (Trading Economics).
- Gold ≈ 17,350–18,100 DZD per gram of 24k in August 2026 (goldrate24).

Replace them with your real numbers.
