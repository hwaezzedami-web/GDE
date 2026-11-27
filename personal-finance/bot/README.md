# Telegram bot — بوت تيليغرام

Send short messages from your phone. The bot writes each one as a new line in
`Personal_Finance_Aboubakr_Bouchra.xlsx`.

أرسل رسائل قصيرة من هاتفك، والبوت يكتبها كسطر جديد في ملف Excel.

## 1. Create the bot — إنشاء البوت

1. In Telegram, open **@BotFather**, send `/newbot`, choose a name and copy the **token**.
   في تيليغرام افتح **@BotFather** وأرسل `/newbot`، ثم انسخ **الرمز (token)**.
2. Open **@userinfobot** to get your Telegram **id**, which is a number. Do the same for Bouchra.
   افتح **@userinfobot** لمعرفة رقمك. نفس الشيء لبشرى.

## 2. Install — التثبيت (Windows)

1. Install Python 3.10 or newer from <https://www.python.org> and tick **"Add Python to PATH"**.
2. Open PowerShell in this `bot` folder and run:

```powershell
pip install -r requirements.txt
```

## 3. Run — التشغيل

```powershell
$env:BOT_TOKEN = "123456:ABC-your-token"
$env:ALLOWED_USER_IDS = "111111111,222222222"
$env:USER_NAMES = "111111111=Aboubakr - أبوبكر,222222222=Bouchra - بشرى"
$env:EXCEL_PATH = "C:\Users\you\Documents\Personal_Finance_Aboubakr_Bouchra.xlsx"
python finance_bot.py
```

- `ALLOWED_USER_IDS` lists the only people the bot will answer. Anyone else gets a refusal that shows their own id.
  البوت يجيب فقط على الأرقام المكتوبة هنا.
- `USER_NAMES` is optional. It fills the "Who" column automatically for each sender.
- Never share the token. Anyone who has it can control the bot.
  لا تشارك الرمز مع أحد.

## 4. Commands — الأوامر

| Command | Example | What it writes |
|---|---|---|
| `/rate` | `/rate 277 279 241` | Rates: EUR sell, EUR buy, USD sell for today |
| `/sell` | `/sell 500 277 square` | Exchange: you sold 500 EUR at 277 |
| `/sellusd` | `/sellusd 100 241` | Exchange: you sold USD |
| `/spend` | `/spend 2500 food bread` | Family: expense with category and description |
| `/income` | `/income 10000 gift` | Family: extra income |
| `/give` | `/give 15000 brother Ali` | Relatives: help given to a relative |
| `/lend` | `/lend 20000 Yacine 2026-12-31 EUR` | Debts: owed to me (you lent) |
| `/borrow` | `/borrow 50000 Karim 2026-12-15` | Debts: I owe (you borrowed) |
| `/pay` | `/pay D001 20000` | Payments: a repayment on debt D001 |
| `/save` | `/save 50000 G01 EUR` | Savings: money for goal G01 |
| `/summary` | | Rate, salary in DZD, EUR in bank, spending, debts, savings |
| `/debts` | | Open debts sorted by return date |

You can write amounts as `15000`, `15,000` or `15k`.

Category words in English or Arabic all work, for example: `food`, `bread`, `sonelgaz`, `fuel`, `pharmacy`, `clothes`, `rent`, `internet`, `gift`, `sadaqa`, `اكل`, `دواء`.

## 5. Good to know — مهم

- **Close the Excel file while the bot writes.** Excel locks open files, and the bot will tell you when that happens.
  أغلق ملف Excel عندما يكتب البوت.
- The bot only answers while your PC is on and the script is running. To keep it running all day and night, use an always-on PC or a small server, such as a cheap VPS.
- Excel recalculates everything when you open the file.
- To fetch the square price automatically, a scraper could be added to `do_rate`. There is no official source, so this is left manual on purpose.
