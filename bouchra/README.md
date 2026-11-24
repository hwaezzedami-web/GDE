# Bouchra 💕 (بشرى)

Pink Arabic Android reminder app: love reminders (kiss, hug, say "I love you"…),
each with its own interval and a **تم ✓** button in the app and in the notification.

- **Install:** copy `Bouchra.apk` to the phone, open it, and allow "install unknown apps".
- Tap a reminder to change how often it fires; long-press to delete; **➕** adds your own.
- Sleep mode (on by default): no reminders between 11 PM and 8 AM.

Version 2 adds a bottom bar with 5 sections:
- ⏰ **التذكيرات**: the love reminders.
- 💑 **معاً**: "together since" counter from the wedding date, love jar (daily/random love phrase, share to WhatsApp), occasions with notifications a week and a day before.
- 🛒 **المشتريات**: shopping list by category, quick suggestions, send the list on WhatsApp.
- ✨ **أحلامنا**: dreams and goals with an optional savings jar and progress bar.
- 🎟️ **الكوبونات**: love coupons she can redeem.

## Rebuild
`build-tools/build.sh <android.jar> <dx.jar>` (needs a JDK, python3 + Pillow; jar sources are listed in the script).
`build-tools/bouchra.keystore` signs the app. Keep it, because updates must be signed with the same key.
