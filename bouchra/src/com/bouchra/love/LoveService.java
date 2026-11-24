package com.bouchra.love;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONObject;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Set;

/**
 * Keeps two live connections while the couple is linked:
 * the partner's notifications for me (inbox) and the shared lists.
 * Runs as a quiet foreground service so Android doesn't stop it.
 */
public class LoveService extends Service {

    static final String CH_BG = "bouchra_bg";
    static final String CH_PARTNER = "bouchra_partner";
    static final int ONGOING_ID = 4242;
    static final long[] HEARTBEAT = {0, 120, 120, 120, 500, 120, 120, 120};

    /** True while the chat screen is visible (then new-message notifications are skipped). */
    public static volatile boolean chatVisible;

    private Cloud.Stream inbox;
    private Cloud.Stream shared;
    private final Set<String> handled = new HashSet<String>();

    public static void start(Context c) {
        if (!Cloud.linked(c)) return;
        Intent i = new Intent(c, LoveService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Exception ignored) {
        }
    }

    public static void stop(Context c) {
        c.stopService(new Intent(c, LoveService.class));
    }

    static void channels(Context c) {
        if (Build.VERSION.SDK_INT < 26) return;
        NotificationManager nm = (NotificationManager) c.getSystemService(NOTIFICATION_SERVICE);
        NotificationChannel bg = new NotificationChannel(CH_BG, "الاتصال بالشريك", NotificationManager.IMPORTANCE_MIN);
        bg.setDescription("يبقي التطبيق متصلاً لتصلك رسائل شريكك");
        bg.setShowBadge(false);
        nm.createNotificationChannel(bg);
        NotificationChannel p = new NotificationChannel(CH_PARTNER, "رسائل الشريك 💕", NotificationManager.IMPORTANCE_HIGH);
        p.setDescription("الرسائل، اشتقت لك، المشتريات والكوبونات");
        p.enableLights(true);
        p.setLightColor(Scheduler.PINK);
        p.enableVibration(true);
        p.setVibrationPattern(HEARTBEAT);
        p.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
                new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build());
        nm.createNotificationChannel(p);
    }

    @SuppressWarnings("deprecation")
    private Notification ongoing() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 4242, open, flags());
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CH_BG) : new Notification.Builder(this);
        b.setSmallIcon(R.drawable.ic_notif)
                .setContentTitle("💕 متصل مع " + Cloud.partnerName(this))
                .setContentText("ستصلك رسائله وتنبيهاته فوراً")
                .setColor(Scheduler.PINK)
                .setOngoing(true)
                .setContentIntent(pi);
        if (Build.VERSION.SDK_INT < 26) b.setPriority(Notification.PRIORITY_MIN);
        return b.build();
    }

    static int flags() {
        int f = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= 23) f |= PendingIntent.FLAG_IMMUTABLE;
        return f;
    }

    @Override
    public int onStartCommand(Intent intent, int fl, int startId) {
        channels(this);
        startForeground(ONGOING_ID, ongoing());
        if (!Cloud.linked(this)) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (inbox == null) {
            final Context c = getApplicationContext();
            Sync.flushAsync(c);
            String uid = Cloud.uid(c);
            String base = "couples/" + Cloud.cid(c);
            inbox = new Cloud.Stream(c, base + "/inbox/" + uid, null, new Cloud.StreamListener() {
                @Override
                public void onEvent(String event, String path, Object data) {
                    onInbox(path, data);
                }
            }).start();
            shared = new Cloud.Stream(c, base + "/shared", null, new Cloud.StreamListener() {
                @Override
                public void onEvent(String event, String path, Object data) {
                    if ("put".equals(event) && "/".equals(path)) Sync.flushAsync(c); // reconnected: send queued edits
                    Sync.onEvent(c, event, path, data);
                }
            }).start();
        }
        return START_STICKY;
    }

    private void onInbox(String path, Object data) {
        if (!(data instanceof JSONObject)) return;
        JSONObject d = (JSONObject) data;
        if ("/".equals(path)) {
            Iterator<String> it = d.keys();
            while (it.hasNext()) {
                String k = it.next();
                JSONObject item = d.optJSONObject(k);
                if (item != null) handle(k, item);
            }
        } else {
            String key = path.startsWith("/") ? path.substring(1) : path;
            if (!key.isEmpty() && !key.contains("/")) handle(key, d);
        }
    }

    private void handle(final String key, JSONObject item) {
        synchronized (handled) {
            if (!handled.add(key)) return;
        }
        String kind = item.optString("kind");
        boolean skip = chatVisible && ("msg".equals(kind) || "miss".equals(kind) || "mood".equals(kind));
        if (!skip) show(kind, item.optString("title"), item.optString("text"));
        final Context c = getApplicationContext();
        Cloud.EX.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    Cloud.delete(c, "couples/" + Cloud.cid(c) + "/inbox/" + Cloud.uid(c) + "/" + key);
                } catch (Exception ignored) {
                }
            }
        });
    }

    /** Tab to open for each kind of partner notification. */
    static int tabFor(String kind) {
        if ("shop".equals(kind)) return MainActivity.TAB_SHOP;
        if ("coupon".equals(kind)) return MainActivity.TAB_COUPONS;
        if ("dream".equals(kind)) return MainActivity.TAB_DREAMS;
        if ("done".equals(kind)) return MainActivity.TAB_REMINDERS;
        return MainActivity.TAB_CHAT;
    }

    @SuppressWarnings("deprecation")
    private void show(String kind, String title, String text) {
        channels(this);
        int id = 30000 + Math.abs(kind.hashCode() % 1000);
        Intent open = new Intent(this, MainActivity.class);
        open.putExtra("tab", tabFor(kind));
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, id, open, flags());
        Notification.Builder b = Build.VERSION.SDK_INT >= 26
                ? new Notification.Builder(this, CH_PARTNER) : new Notification.Builder(this);
        b.setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setColor(Scheduler.PINK)
                .setAutoCancel(true)
                .setContentIntent(pi);
        if (Build.VERSION.SDK_INT < 26) {
            b.setPriority(Notification.PRIORITY_HIGH).setVibrate(HEARTBEAT)
                    .setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION));
        }
        ((NotificationManager) getSystemService(NOTIFICATION_SERVICE)).notify(id, b.build());
    }

    @Override
    public void onDestroy() {
        if (inbox != null) inbox.close();
        if (shared != null) shared.close();
        inbox = null;
        shared = null;
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
