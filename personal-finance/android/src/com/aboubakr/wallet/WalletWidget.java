package com.aboubakr.wallet;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONObject;

/** Home-screen widget: today's square price, dinars in hand and euros in the bank. */
public class WalletWidget extends AppWidgetProvider {
    private static final int FLAG_IMMUTABLE = 67108864;

    @Override
    public void onUpdate(Context c, AppWidgetManager manager, int[] ids) {
        for (int id : ids) manager.updateAppWidget(id, views(c));
    }

    private static RemoteViews views(Context c) {
        JSONObject w;
        try {
            w = new JSONObject(ReminderReceiver.prefs(c).getString("widget", "{}"));
        } catch (Exception e) {
            w = new JSONObject();
        }
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget);
        v.setTextViewText(R.id.w_title, w.optString("title", c.getString(R.string.app_name)));
        v.setTextViewText(R.id.w_rate, w.optString("rate", "—"));
        v.setTextViewText(R.id.w_cash, w.optString("cash", ""));
        v.setTextViewText(R.id.w_eur, w.optString("eur", ""));
        v.setTextViewText(R.id.w_date, w.optString("date", ""));
        Intent open = new Intent(c, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        v.setOnClickPendingIntent(R.id.w_root, PendingIntent.getActivity(c, 2, open, PendingIntent.FLAG_UPDATE_CURRENT | FLAG_IMMUTABLE));
        return v;
    }

    static void refresh(Context c) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        if (m == null) return;
        int[] ids = m.getAppWidgetIds(new ComponentName(c, WalletWidget.class));
        for (int id : ids) m.updateAppWidget(id, views(c));
    }
}
