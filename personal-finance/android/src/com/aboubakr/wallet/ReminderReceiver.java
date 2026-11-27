package com.aboubakr.wallet;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.HashSet;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Once a day, at the time chosen in the app, shows the reminders the page planned
 * (salary day, debts, monthly expenses, backup, dinars running low) and the
 * "add today's price" reminder when no price was typed today.
 * The plan is written by the page through MainActivity.Bridge.setReminders.
 */
public class ReminderReceiver extends BroadcastReceiver {
    static final String ACTION = "com.aboubakr.wallet.REMIND";
    private static final String CHANNEL = "wallet_reminders";
    private static final int FLAG_IMMUTABLE = 67108864;

    @Override
    public void onReceive(Context c, Intent intent) {
        if (ACTION.equals(intent.getAction())) {
            try {
                fire(c);
            } catch (Exception ignored) {
                // a broken plan must never crash the phone's broadcast
            }
        }
        schedule(c);
    }

    static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences("wallet", Context.MODE_PRIVATE);
    }

    private static JSONObject plan(Context c) {
        try {
            return new JSONObject(prefs(c).getString("plan", "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    private static String day(long t) {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date(t));
    }

    static void schedule(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        Intent i = new Intent(c, ReminderReceiver.class).setAction(ACTION);
        PendingIntent pi = PendingIntent.getBroadcast(c, 1, i, PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE);
        JSONObject p = plan(c);
        if (!p.optBoolean("on", false)) {
            am.cancel(pi);
            return;
        }
        int hour = 9, minute = 0;
        try {
            String[] hm = p.optString("time", "09:00").split(":");
            hour = Integer.parseInt(hm[0]);
            minute = Integer.parseInt(hm[1]);
        } catch (Exception ignored) {
            // keep 09:00
        }
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.HOUR_OF_DAY, hour);
        cal.set(Calendar.MINUTE, minute);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        if (cal.getTimeInMillis() <= System.currentTimeMillis() + 1000) cal.add(Calendar.DAY_OF_YEAR, 1);
        if (Build.VERSION.SDK_INT >= 23) am.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, cal.getTimeInMillis(), pi);
        else am.set(AlarmManager.RTC_WAKEUP, cal.getTimeInMillis(), pi);
    }

    private static void fire(Context c) throws Exception {
        JSONObject p = plan(c);
        if (!p.optBoolean("on", false)) return;
        long now = System.currentTimeMillis();
        String today = day(now);
        String from = day(now - 3L * 86400000L);
        SharedPreferences sp = prefs(c);
        JSONArray shown;
        try {
            shown = new JSONArray(sp.getString("shown", "[]"));
        } catch (Exception e) {
            shown = new JSONArray();
        }
        Set<String> seen = new HashSet<String>();
        for (int k = 0; k < shown.length(); k++) seen.add(shown.optString(k));
        List<String> added = new ArrayList<String>();

        JSONArray events = p.optJSONArray("events");
        if (events != null) {
            for (int k = 0; k < events.length(); k++) {
                JSONObject e = events.optJSONObject(k);
                if (e == null) continue;
                String d = e.optString("date");
                if (d.compareTo(today) > 0 || d.compareTo(from) < 0) continue;
                String key = d + "|" + e.optString("title") + "|" + e.optString("text");
                if (seen.contains(key)) continue;
                notify(c, p, key.hashCode(), e.optString("title"), e.optString("text"));
                seen.add(key);
                added.add(key);
            }
        }
        if (p.optBoolean("rate", false) && !hasRateToday(c, today)) {
            String key = today + "|rate";
            if (!seen.contains(key)) {
                notify(c, p, 1001, p.optString("rateTitle"), p.optString("rateText"));
                added.add(key);
            }
        }
        if (!added.isEmpty()) {
            List<String> all = new ArrayList<String>();
            for (int k = 0; k < shown.length(); k++) all.add(shown.optString(k));
            all.addAll(added);
            JSONArray out = new JSONArray();
            for (int k = Math.max(0, all.size() - 300); k < all.size(); k++) out.put(all.get(k));
            sp.edit().putString("shown", out.toString()).apply();
        }
    }

    private static boolean hasRateToday(Context c, String today) {
        try {
            File f = new File(c.getFilesDir(), "wallet.json");
            if (!f.exists()) return false;
            JSONObject colls = new JSONObject(MainActivity.readFile(f)).optJSONObject("colls");
            JSONObject rates = colls == null ? null : colls.optJSONObject("rates");
            if (rates == null) return false;
            Iterator<String> it = rates.keys();
            while (it.hasNext()) {
                JSONObject r = rates.optJSONObject(it.next());
                if (r != null && today.equals(r.optString("date"))) return true;
            }
        } catch (Exception ignored) {
            // treat as no price
        }
        return false;
    }

    private static void notify(Context c, JSONObject p, int id, String title, String text) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        Notification.Builder b = null;
        if (Build.VERSION.SDK_INT >= 26) {
            // NotificationChannel is newer than the SDK this app compiles against, so reach it by reflection.
            try {
                Class<?> ch = Class.forName("android.app.NotificationChannel");
                Object channel = ch.getConstructor(String.class, CharSequence.class, int.class)
                        .newInstance(CHANNEL, p.optString("channel", "Wallet"), 3);
                nm.getClass().getMethod("createNotificationChannel", ch).invoke(nm, channel);
                b = Notification.Builder.class.getConstructor(Context.class, String.class).newInstance(c, CHANNEL);
            } catch (Exception ignored) {
                b = null;
            }
        }
        if (b == null) b = new Notification.Builder(c);
        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(c, 3, open, PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE);
        b.setSmallIcon(R.drawable.ic_stat)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setAutoCancel(true)
                .setContentIntent(pi);
        if (Build.VERSION.SDK_INT >= 21) b.setColor(0xFF0B3D2E);
        nm.notify(id, b.build());
    }
}
