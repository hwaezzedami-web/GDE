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

Version 3 adds a 💬 chat tab and two linked accounts (husband and wife) through Firebase
(Auth + Realtime Database over REST, no Google SDK). Setup steps, in Arabic: `SETUP-FIREBASE.md`.
Security rules: `firebase/database.rules.json`.
- Private chat with ✓/✓✓ read receipts, "typing…", online status, quick replies, a "💗 I miss you" button, and mood sharing.
- Shopping, dreams, coupons, occasions and the wedding date are shared live between both phones.
- Partner notifications (messages, miss you, items added or bought, coupons used, reminders done)
  arrive through a small foreground service, even when the app is closed.
- First launch asks "husband or wife" and adapts reminders and wording.

### Tests
`test/CloudTest.java` runs the app's real Cloud/Sync code as three phones (husband, wife, stranger)
against the Firebase emulator (`firebase emulators:start --only auth,database` using the rules file).
29 checks: invite and join, security (a stranger is locked out, max two people), live list sync,
simultaneous edits, chat, read receipts, inbox notifications, token refresh, and sign-in restore.

## iPhone web app (`/docs`, version 3.2)
Bouchra's iPhone uses a web app (installable from Safari via "Add to Home Screen"), served by GitHub Pages
from `/docs`: https://hwaezzedami-web.github.io/GDE/
- It uses the same Firebase project, data format and invite codes as the Android app. The wife signs up and types the 6-digit code.
- Chat, shopping, together, dreams, coupons, her own reminders (shown when due while open), mood and "miss you".
- Notifications while closed: the web app stores a Web Push subscription and its own VAPID key at
  `couples/{cid}/push/{uid}`. The Android app (`WebPush.java`) signs a VAPID JWT and sends an empty push.
  The service worker then reads the inbox from Firebase and shows the notifications. No server is needed.
- Test: `test/web-test.cjs` drives the web app in Chromium (iPhone viewport) as the wife, while `test/HusbandCli.java`
  runs the Android code as the husband, both against the Firebase emulator. It makes 25 checks, including the
  VAPID signature verified with WebCrypto.
