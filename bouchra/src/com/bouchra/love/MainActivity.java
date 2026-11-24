package com.bouchra.love;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.List;
import java.util.Random;

public class MainActivity extends Activity {

    static final int PINK = 0xFFE91E63;
    static final int PINK_LIGHT = 0xFFFF80AB;
    static final int PINK_SOFT = 0xFFFCE4EC;
    static final int PINK_BG = 0xFFFFF0F6;
    static final int PINK_DARK = 0xFFAD1457;
    static final int PINK_GRAY = 0xFF9C6B80;

    private static final String[] PRAISE = {
        "أحسنت يا بطل ❤️",
        "بشرى محظوظة بك 💕",
        "ما أجمل حبكما 🥰",
        "زوج رائع! 🌹",
        "الحب يكبر كل يوم 💖",
        "قلب بشرى يبتسم الآن 😍",
        "استمر هكذا يا حبيب بشرى 💗",
    };

    public static String randomPraise() {
        return PRAISE[new Random().nextInt(PRAISE.length)];
    }

    private LinearLayout listBox;
    private TextView todayText;
    private final Handler handler = new Handler();
    private final Runnable ticker = new Runnable() {
        @Override
        public void run() {
            refresh();
            handler.postDelayed(this, 30000);
        }
    };

    private int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private GradientDrawable rounded(int color, float radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(radiusDp));
        return g;
    }

    private static final String[][] TABS = {
            {"⏰", "التذكيرات", "تذكيرات الحب لأجمل زوجة 🌸"},
            {"💑", "معاً", "أيامنا ومناسباتنا 💕"},
            {"🛒", "المشتريات", "جيب معاك... 🛍️"},
            {"✨", "أحلامنا", "ما نحلم أن نحققه معاً 🌟"},
            {"🎟️", "الكوبونات", "هدايا صغيرة لبشرى 🎁"},
    };

    private Ui ui;
    private FrameLayout content;
    private LinearLayout nav;
    private TextView subtitle;
    private int tab = 0;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        setTheme(android.R.style.Theme_Material_Light_NoActionBar);
        super.onCreate(savedInstanceState);
        ui = new Ui(this);
        getWindow().setStatusBarColor(PINK_DARK);
        getWindow().setNavigationBarColor(Color.WHITE);

        // Creating the channel while visible triggers the Android 13+ notification permission prompt.
        Scheduler.createChannel(this);
        Scheduler.scheduleAll(this);
        Scheduler.scheduleDaily(this);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(PINK_BG);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);

        // ---- header ----
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.VERTICAL);
        header.setGravity(Gravity.CENTER);
        header.setPadding(dp(16), dp(14), dp(16), dp(14));
        GradientDrawable hg = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{PINK_DARK, PINK, PINK_LIGHT});
        hg.setCornerRadii(new float[]{0, 0, 0, 0, dp(26), dp(26), dp(26), dp(26)});
        header.setBackground(hg);
        header.setElevation(dp(6));

        TextView title = new TextView(this);
        title.setText("💕 بشرى 💕");
        title.setTextColor(Color.WHITE);
        title.setTextSize(28);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setGravity(Gravity.CENTER);
        header.addView(title);

        subtitle = new TextView(this);
        subtitle.setTextColor(0xFFFFE4EF);
        subtitle.setTextSize(14);
        subtitle.setGravity(Gravity.CENTER);
        header.addView(subtitle);
        root.addView(header, new LinearLayout.LayoutParams(-1, -2));

        content = new FrameLayout(this);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1f));

        // ---- bottom navigation ----
        nav = new LinearLayout(this);
        nav.setOrientation(LinearLayout.HORIZONTAL);
        nav.setBackgroundColor(Color.WHITE);
        nav.setElevation(dp(12));
        nav.setPadding(dp(4), dp(6), dp(4), dp(6));
        root.addView(nav, new LinearLayout.LayoutParams(-1, -2));

        setContentView(root);
        tab = Data.p(this).getInt("tab", 0);
        showTab(tab);
    }

    private void drawNav() {
        nav.removeAllViews();
        for (int i = 0; i < TABS.length; i++) {
            final int idx = i;
            boolean sel = i == tab;
            LinearLayout item = new LinearLayout(this);
            item.setOrientation(LinearLayout.VERTICAL);
            item.setGravity(Gravity.CENTER);
            item.setPadding(0, dp(4), 0, dp(4));
            if (sel) item.setBackground(rounded(PINK_SOFT, 16));
            TextView e = new TextView(this);
            e.setText(TABS[i][0]);
            e.setTextSize(sel ? 22 : 19);
            e.setGravity(Gravity.CENTER);
            item.addView(e);
            TextView l = new TextView(this);
            l.setText(TABS[i][1]);
            l.setTextSize(11);
            l.setGravity(Gravity.CENTER);
            l.setTextColor(sel ? PINK : PINK_GRAY);
            if (sel) l.setTypeface(Typeface.DEFAULT_BOLD);
            item.addView(l);
            item.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    showTab(idx);
                }
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, -2, 1f);
            lp.setMargins(dp(2), 0, dp(2), 0);
            nav.addView(item, lp);
        }
    }

    private void showTab(int i) {
        if (i < 0 || i >= TABS.length) i = 0;
        tab = i;
        Data.p(this).edit().putInt("tab", i).apply();
        subtitle.setText(TABS[i][2]);
        drawNav();
        content.removeAllViews();
        listBox = null;
        View v;
        switch (i) {
            case 1: v = new TogetherTab(this, ui).build(); break;
            case 2: v = new ShoppingTab(this, ui).build(); break;
            case 3: v = new DreamsTab(this, ui).build(); break;
            case 4: v = new CouponsTab(this, ui).build(); break;
            default: v = buildReminders(); break;
        }
        content.addView(v, new FrameLayout.LayoutParams(-1, -1));
        if (i == 0) refresh();
    }

    private View buildReminders() {
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);

        todayText = new TextView(this);
        todayText.setTextColor(PINK_DARK);
        todayText.setTextSize(15);
        todayText.setTypeface(Typeface.DEFAULT_BOLD);
        todayText.setGravity(Gravity.CENTER);
        todayText.setPadding(dp(18), dp(6), dp(18), dp(6));
        todayText.setBackground(rounded(Color.WHITE, 20));
        todayText.setElevation(dp(2));
        LinearLayout.LayoutParams tlp = new LinearLayout.LayoutParams(-2, -2);
        tlp.topMargin = dp(12);
        tlp.gravity = Gravity.CENTER_HORIZONTAL;
        col.addView(todayText, tlp);

        // ---- quiet hours switch ----
        Switch quiet = new Switch(this);
        quiet.setText("🌙 وضع النوم: لا تذكيرات من 11 ليلاً حتى 8 صباحاً");
        quiet.setTextColor(PINK_DARK);
        quiet.setTextSize(13);
        quiet.setChecked(Store.quietEnabled(this));
        quiet.setPadding(dp(14), dp(10), dp(14), dp(10));
        quiet.setBackground(rounded(PINK_SOFT, 16));
        quiet.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton b, boolean on) {
                Store.setQuiet(MainActivity.this, on);
                List<Store.Reminder> list = Store.load(MainActivity.this);
                for (Store.Reminder r : list) r.next = Store.adjustForQuiet(MainActivity.this, r.next);
                Store.save(MainActivity.this, list);
                for (Store.Reminder r : list) Scheduler.schedule(MainActivity.this, r);
                refresh();
            }
        });
        LinearLayout.LayoutParams qlp = new LinearLayout.LayoutParams(-1, -2);
        qlp.setMargins(dp(14), dp(10), dp(14), dp(4));
        col.addView(quiet, qlp);

        // ---- reminders list ----
        ScrollView scroll = new ScrollView(this);
        listBox = new LinearLayout(this);
        listBox.setOrientation(LinearLayout.VERTICAL);
        listBox.setPadding(dp(12), dp(6), dp(12), dp(90));
        scroll.addView(listBox);
        col.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1f));

        FrameLayout frame = new FrameLayout(this);
        frame.addView(col, new FrameLayout.LayoutParams(-1, -1));
        Button add = ui.fab("➕  إضافة تذكير");
        add.setElevation(dp(8));
        add.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showAddDialog();
            }
        });
        FrameLayout.LayoutParams alp = new FrameLayout.LayoutParams(-2, dp(52));
        alp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
        alp.bottomMargin = dp(14);
        frame.addView(add, alp);
        return frame;
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.removeCallbacks(ticker);
        handler.post(ticker);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(ticker);
    }

    private void refresh() {
        if (listBox == null || tab != 0) return;
        List<Store.Reminder> list = Store.load(this);
        int todayTotal = 0;
        for (Store.Reminder r : list) todayTotal += r.today;
        todayText.setText("❤️ أنجزت اليوم: " + todayTotal + " ❤️");

        listBox.removeAllViews();
        for (final Store.Reminder r : list) {
            listBox.addView(card(r));
        }
    }

    private View card(final Store.Reminder r) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.HORIZONTAL);
        card.setGravity(Gravity.CENTER_VERTICAL);
        card.setPadding(dp(12), dp(12), dp(12), dp(12));
        GradientDrawable bg = rounded(r.enabled ? Color.WHITE : 0xFFF5EEF1, 18);
        bg.setStroke(dp(1), r.enabled ? 0xFFF8BBD0 : 0xFFE0D0D6);
        card.setBackground(bg);
        card.setElevation(dp(2));
        LinearLayout.LayoutParams clp = new LinearLayout.LayoutParams(-1, -2);
        clp.setMargins(dp(2), dp(6), dp(2), dp(6));
        card.setLayoutParams(clp);

        // emoji bubble
        TextView emoji = new TextView(this);
        emoji.setText(r.emoji);
        emoji.setTextSize(26);
        emoji.setGravity(Gravity.CENTER);
        GradientDrawable eb = new GradientDrawable();
        eb.setShape(GradientDrawable.OVAL);
        eb.setColor(PINK_SOFT);
        emoji.setBackground(eb);
        card.addView(emoji, new LinearLayout.LayoutParams(dp(54), dp(54)));

        // texts
        LinearLayout texts = new LinearLayout(this);
        texts.setOrientation(LinearLayout.VERTICAL);
        texts.setPadding(dp(12), 0, dp(8), 0);

        TextView t = new TextView(this);
        t.setText(r.title);
        t.setTextSize(17);
        t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setTextColor(r.enabled ? PINK_DARK : PINK_GRAY);
        texts.addView(t);

        TextView info = new TextView(this);
        String line = "⏱ " + Store.intervalText(r.interval);
        if (r.enabled) line += "  •  التالي: " + Store.whenText(r.next);
        else line += "  •  متوقف";
        info.setText(line);
        info.setTextSize(12);
        info.setTextColor(PINK_GRAY);
        texts.addView(info);

        TextView count = new TextView(this);
        count.setText("✅ اليوم: " + r.today + "   •   المجموع: " + r.total);
        count.setTextSize(12);
        count.setTextColor(PINK);
        texts.addView(count);

        card.addView(texts, new LinearLayout.LayoutParams(0, -2, 1f));

        // controls
        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.VERTICAL);
        controls.setGravity(Gravity.CENTER_HORIZONTAL);

        Button done = new Button(this);
        done.setText("تم ✓");
        done.setAllCaps(false);
        done.setTextColor(Color.WHITE);
        done.setTextSize(15);
        done.setTypeface(Typeface.DEFAULT_BOLD);
        done.setBackground(rounded(r.enabled ? PINK : 0xFFD9B8C6, 22));
        done.setMinWidth(0);
        done.setMinimumWidth(0);
        done.setPadding(dp(16), 0, dp(16), 0);
        done.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                List<Store.Reminder> list = Store.load(MainActivity.this);
                Store.Reminder cur = Store.find(list, r.id);
                if (cur == null) return;
                Store.markDone(MainActivity.this, cur);
                Store.save(MainActivity.this, list);
                Scheduler.schedule(MainActivity.this, cur);
                Scheduler.dismiss(MainActivity.this, cur.id);
                Toast.makeText(MainActivity.this, randomPraise(), Toast.LENGTH_SHORT).show();
                refresh();
            }
        });
        controls.addView(done, new LinearLayout.LayoutParams(-2, dp(42)));

        Switch sw = new Switch(this);
        sw.setChecked(r.enabled);
        sw.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton b, boolean on) {
                List<Store.Reminder> list = Store.load(MainActivity.this);
                Store.Reminder cur = Store.find(list, r.id);
                if (cur == null) return;
                cur.enabled = on;
                if (on) cur.next = Store.adjustForQuiet(MainActivity.this,
                        System.currentTimeMillis() + cur.interval * 60000L);
                Store.save(MainActivity.this, list);
                if (on) Scheduler.schedule(MainActivity.this, cur);
                else Scheduler.cancel(MainActivity.this, cur.id);
                refresh();
            }
        });
        LinearLayout.LayoutParams slp = new LinearLayout.LayoutParams(-2, -2);
        slp.topMargin = dp(6);
        controls.addView(sw, slp);

        card.addView(controls, new LinearLayout.LayoutParams(-2, -2));

        card.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                showIntervalDialog(r.id);
            }
        });
        card.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                showDeleteDialog(r.id, r.title);
                return true;
            }
        });
        return card;
    }

    private String[] intervalLabels() {
        String[] labels = new String[Store.INTERVALS.length];
        for (int i = 0; i < labels.length; i++) labels[i] = Store.intervalText(Store.INTERVALS[i]);
        return labels;
    }

    private void showIntervalDialog(final int id) {
        new AlertDialog.Builder(this)
                .setTitle("⏱ كم مرة تريد التذكير؟")
                .setItems(intervalLabels(), new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which) {
                        List<Store.Reminder> list = Store.load(MainActivity.this);
                        Store.Reminder cur = Store.find(list, id);
                        if (cur == null) return;
                        cur.interval = Store.INTERVALS[which];
                        cur.next = Store.adjustForQuiet(MainActivity.this,
                                System.currentTimeMillis() + cur.interval * 60000L);
                        Store.save(MainActivity.this, list);
                        Scheduler.schedule(MainActivity.this, cur);
                        refresh();
                    }
                })
                .show();
    }

    private void showDeleteDialog(final int id, String name) {
        new AlertDialog.Builder(this)
                .setTitle("حذف التذكير؟")
                .setMessage("هل تريد حذف «" + name + "»؟")
                .setPositiveButton("حذف", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        List<Store.Reminder> list = Store.load(MainActivity.this);
                        Store.Reminder cur = Store.find(list, id);
                        if (cur != null) list.remove(cur);
                        Store.save(MainActivity.this, list);
                        Scheduler.cancel(MainActivity.this, id);
                        refresh();
                    }
                })
                .setNegativeButton("إلغاء", null)
                .show();
    }

    private void showAddDialog() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(20), dp(8), dp(20), 0);
        box.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);

        final EditText emoji = new EditText(this);
        emoji.setHint("رمز تعبيري (مثل 💗)");
        emoji.setText("💗");
        box.addView(emoji);

        final EditText name = new EditText(this);
        name.setHint("نص التذكير (مثل: قل لها إنها ملكتك)");
        name.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        box.addView(name);

        final int[] chosen = {2}; // default: every 2 hours
        final Button interval = new Button(this);
        interval.setAllCaps(false);
        interval.setText("⏱ " + Store.intervalText(Store.INTERVALS[chosen[0]]));
        interval.setTextColor(PINK_DARK);
        interval.setBackground(rounded(PINK_SOFT, 14));
        interval.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                new AlertDialog.Builder(MainActivity.this)
                        .setItems(intervalLabels(), new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int which) {
                                chosen[0] = which;
                                interval.setText("⏱ " + Store.intervalText(Store.INTERVALS[which]));
                            }
                        }).show();
            }
        });
        LinearLayout.LayoutParams ilp = new LinearLayout.LayoutParams(-1, dp(46));
        ilp.topMargin = dp(10);
        box.addView(interval, ilp);

        new AlertDialog.Builder(this)
                .setTitle("➕ تذكير جديد")
                .setView(box)
                .setPositiveButton("إضافة", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String title = name.getText().toString().trim();
                        if (title.isEmpty()) {
                            Toast.makeText(MainActivity.this, "اكتب نص التذكير أولاً", Toast.LENGTH_SHORT).show();
                            return;
                        }
                        String e = emoji.getText().toString().trim();
                        List<Store.Reminder> list = Store.load(MainActivity.this);
                        Store.Reminder r = new Store.Reminder();
                        r.id = Store.nextId(list);
                        r.emoji = e.isEmpty() ? "💗" : e;
                        r.title = title;
                        r.message = r.emoji + " " + title + " — من أجل بشرى 💕";
                        r.interval = Store.INTERVALS[chosen[0]];
                        r.next = Store.adjustForQuiet(MainActivity.this,
                                System.currentTimeMillis() + r.interval * 60000L);
                        list.add(0, r);
                        Store.save(MainActivity.this, list);
                        Scheduler.schedule(MainActivity.this, r);
                        refresh();
                    }
                })
                .setNegativeButton("إلغاء", null)
                .show();
    }
}
