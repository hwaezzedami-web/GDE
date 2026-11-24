package com.bouchra.love;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;

import java.util.List;

/** Schedules alarms and shows notifications. */
public class Scheduler {

    public static final String CHANNEL = "bouchra_love";
    public static final int PINK = 0xFFE91E63;

    public static final String ACTION_ALARM = "com.bouchra.love.ALARM";
    public static final String ACTION_DONE = "com.bouchra.love.DONE";
    public static final String ACTION_SNOOZE = "com.bouchra.love.SNOOZE";
    public static final String EXTRA_ID = "id";

    private static int piFlags() {
        int f = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) f |= PendingIntent.FLAG_IMMUTABLE;
        return f;
    }

    private static PendingIntent pi(Context c, String action, int id) {
        Intent i = new Intent(c, ReminderReceiver.class);
        i.setAction(action);
        i.putExtra(EXTRA_ID, id);
        int code = id * 4 + (ACTION_ALARM.equals(action) ? 0 : ACTION_DONE.equals(action) ? 1 : 2);
        return PendingIntent.getBroadcast(c, code, i, piFlags());
    }

    public static void createChannel(Context c) {
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "تذكيرات بشرى 💕",
                    NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("تذكيرات الحب لبشرى");
            ch.enableLights(true);
            ch.setLightColor(PINK);
            ch.enableVibration(true);
            ch.setVibrationPattern(new long[]{0, 300, 200, 300});
            ch.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                    new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build());
            ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).createNotificationChannel(ch);
        }
    }

    public static void schedule(Context c, Store.Reminder r) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        PendingIntent p = pi(c, ACTION_ALARM, r.id);
        am.cancel(p);
        if (!r.enabled) return;
        long t = Math.max(r.next, System.currentTimeMillis() + 5000);
        if (Build.VERSION.SDK_INT >= 23) {
            am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, t, p);
        } else {
            am.setExact(AlarmManager.RTC_WAKEUP, t, p);
        }
    }

    public static void cancel(Context c, int id) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        am.cancel(pi(c, ACTION_ALARM, id));
        dismiss(c, id);
    }

    /** Reschedules everything; reminders whose time passed are moved forward. */
    public static void scheduleAll(Context c) {
        List<Store.Reminder> list = Store.load(c);
        long now = System.currentTimeMillis();
        for (Store.Reminder r : list) {
            if (r.enabled && r.next < now) {
                r.next = Store.adjustForQuiet(c, now + 60000L);
            }
        }
        Store.save(c, list);
        for (Store.Reminder r : list) schedule(c, r);
    }

    public static void dismiss(Context c, int id) {
        ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).cancel(id);
    }

    @SuppressWarnings("deprecation")
    public static void notify(Context c, Store.Reminder r) {
        createChannel(c);
        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent contentPi = PendingIntent.getActivity(c, r.id * 4 + 3, open, piFlags());

        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(c, CHANNEL)
                : new Notification.Builder(c);
        b.setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(r.emoji + " " + r.title)
                .setContentText(r.message)
                .setStyle(new Notification.BigTextStyle().bigText(r.message))
                .setColor(PINK)
                .setAutoCancel(true)
                .setContentIntent(contentPi)
                .setCategory(Notification.CATEGORY_REMINDER)
                .addAction(new Notification.Action.Builder(0, "تم ✓", pi(c, ACTION_DONE, r.id)).build())
                .addAction(new Notification.Action.Builder(0, "بعد 15 دقيقة ⏰", pi(c, ACTION_SNOOZE, r.id)).build());
        if (Build.VERSION.SDK_INT < 26) {
            b.setPriority(Notification.PRIORITY_HIGH)
                    .setDefaults(Notification.DEFAULT_ALL)
                    .setLights(PINK, 800, 1600);
        }
        ((NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE)).notify(r.id, b.build());
    }
}
