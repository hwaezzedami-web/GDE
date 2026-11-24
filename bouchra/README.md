# Bouchra 💕 (بشرى)

Pink Arabic Android reminder app: love reminders (kiss, hug, say "I love you"…),
each with its own interval and a **تم ✓** button in the app and in the notification.

- **Install:** copy `Bouchra.apk` to the phone, open it, and allow "install unknown apps".
- Tap a reminder to change how often it fires; long-press to delete; **➕** adds your own.
- Sleep mode (on by default): no reminders between 11 PM and 8 AM.

## Rebuild
`build-tools/build.sh <android.jar> <dx.jar>` (needs a JDK, python3 + Pillow; jar sources are listed in the script).
`build-tools/bouchra.keystore` signs the app. Keep it, because updates must be signed with the same key.
