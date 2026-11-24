package com.bouchra.love;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.widget.Toast;

import java.util.List;

/** Handles alarms, the "Done" / "Snooze" notification buttons, and reboot. */
public class ReminderReceiver extends BroadcastReceiver {

    @Override
    public void onReceive(Context c, Intent intent) {
        String action = intent.getAction();
        if (action == null) return;

        if (Intent.ACTION_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)
                || "android.intent.action.QUICKBOOT_POWERON".equals(action)) {
            Scheduler.scheduleAll(c);
            return;
        }

        int id = intent.getIntExtra(Scheduler.EXTRA_ID, -1);
        List<Store.Reminder> list = Store.load(c);
        Store.Reminder r = Store.find(list, id);
        if (r == null) return;

        if (Scheduler.ACTION_ALARM.equals(action)) {
            if (!r.enabled) return;
            Scheduler.notify(c, r);
            r.next = Store.adjustForQuiet(c, System.currentTimeMillis() + r.interval * 60000L);
        } else if (Scheduler.ACTION_DONE.equals(action)) {
            Store.markDone(c, r);
            Scheduler.dismiss(c, r.id);
            Toast.makeText(c, MainActivity.randomPraise(), Toast.LENGTH_SHORT).show();
        } else if (Scheduler.ACTION_SNOOZE.equals(action)) {
            r.next = System.currentTimeMillis() + 15 * 60000L;
            Scheduler.dismiss(c, r.id);
        } else {
            return;
        }
        Store.save(c, list);
        Scheduler.schedule(c, r);
    }
}
