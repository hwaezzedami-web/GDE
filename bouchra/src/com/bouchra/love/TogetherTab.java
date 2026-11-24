package com.bouchra.love;

import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.animation.OvershootInterpolator;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.DatePicker;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/** "معاً": days together counter, love jar, and our occasions. */
public class TogetherTab {

    private final MainActivity a;
    private final Ui ui;
    private LinearLayout body;

    private static final String[][] OCCASION_TYPES = {
            {"🎂", "عيد ميلاد بشرى"},
            {"🎂", "عيد ميلادي"},
            {"💞", "أول لقاء"},
            {"💐", "خطوبتنا"},
            {"🎉", "مناسبة أخرى..."},
    };

    public TogetherTab(MainActivity a, Ui ui) {
        this.a = a;
        this.ui = ui;
    }

    public View build() {
        body = ui.column();
        fill();
        return ui.page(body, null);
    }

    private void fill() {
        body.removeAllViews();
        body.addView(sinceCard());
        body.addView(jarCard());

        LinearLayout head = ui.row();
        head.addView(ui.section("📅 مناسباتنا"), ui.weight(1));
        Button add = ui.softButton("➕ إضافة");
        add.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                addOccasion();
            }
        });
        head.addView(add);
        body.addView(head);

        List<JSONObject> occ = Data.items(Data.list(a, Data.OCCASIONS));
        Collections.sort(occ, new Comparator<JSONObject>() {
            @Override
            public int compare(JSONObject x, JSONObject y) {
                return Data.daysUntil(x.optInt("m"), x.optInt("d")) - Data.daysUntil(y.optInt("m"), y.optInt("d"));
            }
        });
        if (occ.isEmpty()) {
            TextView t = ui.text("أضف عيد ميلادها وأول لقاء بينكما، وسأذكّرك قبلها بأسبوع وبيوم 🎁", 13, Ui.PINK_GRAY, false);
            t.setPadding(ui.dp(8), ui.dp(4), ui.dp(8), ui.dp(4));
            body.addView(t);
        }
        for (JSONObject o : occ) body.addView(occasionCard(o));
    }

    // ---------------- together since ----------------

    private View sinceCard() {
        LinearLayout c = ui.card(true);
        c.setGravity(Gravity.CENTER_HORIZONTAL);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{Ui.PINK, Ui.PINK_LIGHT});
        g.setCornerRadius(ui.dp(20));
        c.setBackground(g);
        c.setPadding(ui.dp(16), ui.dp(18), ui.dp(16), ui.dp(18));

        TextView title = ui.text("💑 معاً منذ", 18, Color.WHITE, true);
        title.setGravity(Gravity.CENTER);
        c.addView(title);

        final long since = Data.p(a).getLong(Data.SINCE, 0);
        if (since == 0) {
            TextView t = ui.text("اختر تاريخ زواجكما لنحسب أيام حبكما 💕", 14, Color.WHITE, false);
            t.setGravity(Gravity.CENTER);
            t.setPadding(0, ui.dp(8), 0, ui.dp(10));
            c.addView(t);
            Button b = ui.button("📅 اختر التاريخ", Color.WHITE, Ui.PINK_DARK);
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    pickSince(0);
                }
            });
            c.addView(b);
            return c;
        }

        Calendar s = Calendar.getInstance();
        s.setTimeInMillis(since);
        Calendar n = Data.today();
        int y = n.get(Calendar.YEAR) - s.get(Calendar.YEAR);
        int m = n.get(Calendar.MONTH) - s.get(Calendar.MONTH);
        int d = n.get(Calendar.DAY_OF_MONTH) - s.get(Calendar.DAY_OF_MONTH);
        if (d < 0) {
            m--;
            Calendar prev = (Calendar) n.clone();
            prev.add(Calendar.MONTH, -1);
            d += prev.getActualMaximum(Calendar.DAY_OF_MONTH);
        }
        if (m < 0) {
            y--;
            m += 12;
        }
        List<String> parts = new ArrayList<String>();
        if (y > 0) parts.add(Data.plural(y, "سنة", "سنتان", "سنوات", "سنة"));
        if (m > 0) parts.add(Data.plural(m, "شهر", "شهران", "أشهر", "شهراً"));
        if (d > 0 || parts.isEmpty()) parts.add(Data.days(d));
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) sb.append(" و ");
            sb.append(parts.get(i));
        }
        TextView big = ui.text(sb.toString(), 24, Color.WHITE, true);
        big.setGravity(Gravity.CENTER);
        big.setPadding(0, ui.dp(8), 0, ui.dp(4));
        c.addView(big);

        long totalDays = Math.max(0, (Data.today().getTimeInMillis() - since) / 86400000L);
        TextView total = ui.text("أي " + Data.money(totalDays) + " يوماً من الحب 💕", 14, 0xFFFFE4EF, false);
        total.setGravity(Gravity.CENTER);
        c.addView(total);

        int du = Data.daysUntil(s.get(Calendar.MONTH), s.get(Calendar.DAY_OF_MONTH));
        int count = Data.nextYearCount(s.get(Calendar.YEAR), s.get(Calendar.MONTH), s.get(Calendar.DAY_OF_MONTH));
        String ann = du == 0
                ? "🎉 اليوم ذكرى زواجكما " + Data.ordinal(count) + "! مبروك 💍"
                : "💍 الذكرى " + Data.ordinal(count) + " بعد " + Data.days(du);
        TextView next = ui.text(ann, 14, Ui.PINK_DARK, true);
        next.setGravity(Gravity.CENTER);
        next.setBackground(ui.rounded(Color.WHITE, 16));
        next.setPadding(ui.dp(14), ui.dp(6), ui.dp(14), ui.dp(6));
        c.addView(next, ui.margins(-2, -2, 0, 12, 0, 0));

        c.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pickSince(since);
            }
        });
        return c;
    }

    private void pickSince(long current) {
        Calendar c = Calendar.getInstance();
        if (current > 0) c.setTimeInMillis(current);
        else c.add(Calendar.YEAR, -1);
        DatePickerDialog dlg = new DatePickerDialog(a, new DatePickerDialog.OnDateSetListener() {
            @Override
            public void onDateSet(DatePicker v, int y, int m, int d) {
                Calendar s = Data.today();
                s.set(y, m, d);
                Data.p(a).edit().putLong(Data.SINCE, s.getTimeInMillis()).commit();
                fill();
            }
        }, c.get(Calendar.YEAR), c.get(Calendar.MONTH), c.get(Calendar.DAY_OF_MONTH));
        dlg.getDatePicker().setMaxDate(System.currentTimeMillis());
        dlg.setTitle("💍 تاريخ زواجكما");
        dlg.show();
    }

    // ---------------- love jar ----------------

    private View jarCard() {
        LinearLayout c = ui.card(true);
        c.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView title = ui.text("🫙 جرّة الحب", 18, Ui.PINK_DARK, true);
        c.addView(title);
        TextView hint = ui.text("رسالة اليوم — قلها لبشرى أو أرسلها لها", 12, Ui.PINK_GRAY, false);
        c.addView(hint);

        final TextView phrase = ui.text(Data.phraseOfDay(), 19, Ui.PINK, true);
        phrase.setGravity(Gravity.CENTER);
        phrase.setBackground(ui.rounded(Ui.PINK_SOFT, 16));
        phrase.setPadding(ui.dp(14), ui.dp(16), ui.dp(14), ui.dp(16));
        c.addView(phrase, ui.margins(-1, -2, 0, 10, 0, 10));

        LinearLayout btns = ui.row();
        btns.setGravity(Gravity.CENTER);
        Button draw = ui.pinkButton("💌 اسحب ورقة");
        draw.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String p = Data.randomPhrase();
                while (p.contentEquals(phrase.getText())) p = Data.randomPhrase();
                phrase.setText(p);
                phrase.setScaleX(0.6f);
                phrase.setScaleY(0.6f);
                phrase.setAlpha(0f);
                phrase.animate().scaleX(1f).scaleY(1f).alpha(1f).setDuration(380)
                        .setInterpolator(new OvershootInterpolator()).start();
            }
        });
        btns.addView(draw);
        Button send = ui.softButton("📤 أرسلها لها");
        send.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Data.share(a, phrase.getText().toString());
            }
        });
        btns.addView(send, ui.margins(-2, -2, 8, 0, 0, 0));
        c.addView(btns);

        Switch daily = new Switch(a);
        daily.setText("🔔 ذكّرني برسالة اليوم كل صباح (9:00)");
        daily.setTextColor(Ui.PINK_GRAY);
        daily.setTextSize(12);
        daily.setChecked(Data.p(a).getBoolean(Data.DAILY_PHRASE, true));
        daily.setOnCheckedChangeListener(new CompoundButton.OnCheckedChangeListener() {
            @Override
            public void onCheckedChanged(CompoundButton b, boolean on) {
                Data.p(a).edit().putBoolean(Data.DAILY_PHRASE, on).commit();
            }
        });
        c.addView(daily, ui.margins(-1, -2, 0, 10, 0, 0));
        return c;
    }

    // ---------------- occasions ----------------

    private View occasionCard(final JSONObject o) {
        LinearLayout c = ui.card(true);
        c.setOrientation(LinearLayout.HORIZONTAL);
        c.setGravity(Gravity.CENTER_VERTICAL);
        c.addView(ui.emojiBubble(o.optString("emoji", "🎉"), 48));

        LinearLayout texts = ui.column();
        texts.setPadding(ui.dp(12), 0, ui.dp(8), 0);
        texts.addView(ui.text(o.optString("title"), 16, Ui.PINK_DARK, true));
        Calendar cal = Calendar.getInstance();
        cal.set(o.optInt("y"), o.optInt("m"), o.optInt("d"));
        int count = Data.nextYearCount(o.optInt("y"), o.optInt("m"), o.optInt("d"));
        String info = "📆 " + Data.date(cal.getTimeInMillis());
        if (count > 0) info += "  •  " + (o.optString("title").contains("ميلاد") ? "العمر " + count : "الذكرى " + Data.ordinal(count));
        texts.addView(ui.text(info, 12, Ui.PINK_GRAY, false));
        c.addView(texts, ui.weight(1));

        int du = Data.daysUntil(o.optInt("m"), o.optInt("d"));
        TextView badge = ui.text(du == 0 ? "اليوم! 🎉" : du == 1 ? "غداً" : "بعد\n" + Data.days(du),
                13, Color.WHITE, true);
        badge.setGravity(Gravity.CENTER);
        badge.setBackground(ui.rounded(du <= 7 ? Ui.PINK : Ui.PINK_LIGHT, 14));
        badge.setPadding(ui.dp(10), ui.dp(6), ui.dp(10), ui.dp(6));
        c.addView(badge);

        c.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                new AlertDialog.Builder(a)
                        .setTitle("حذف المناسبة؟")
                        .setMessage(o.optString("title"))
                        .setPositiveButton("حذف", new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int w) {
                                JSONArray arr = Data.list(a, Data.OCCASIONS);
                                Data.remove(arr, o.optInt("id"));
                                Data.save(a, Data.OCCASIONS, arr);
                                fill();
                            }
                        })
                        .setNegativeButton("إلغاء", null).show();
                return true;
            }
        });
        return c;
    }

    private void addOccasion() {
        String[] labels = new String[OCCASION_TYPES.length];
        for (int i = 0; i < labels.length; i++) labels[i] = OCCASION_TYPES[i][0] + "  " + OCCASION_TYPES[i][1];
        new AlertDialog.Builder(a)
                .setTitle("📅 أي مناسبة؟")
                .setItems(labels, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int which) {
                        if (which == OCCASION_TYPES.length - 1) askName();
                        else pickOccasionDate(OCCASION_TYPES[which][0], OCCASION_TYPES[which][1]);
                    }
                }).show();
    }

    private void askName() {
        LinearLayout box = ui.dialogBox();
        final EditText emoji = ui.input("رمز تعبيري");
        emoji.setText("🎉");
        box.addView(emoji);
        final EditText name = ui.input("اسم المناسبة");
        box.addView(name);
        new AlertDialog.Builder(a)
                .setTitle("🎉 مناسبة جديدة")
                .setView(box)
                .setPositiveButton("التالي: التاريخ", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String n = name.getText().toString().trim();
                        if (n.isEmpty()) {
                            ui.toast("اكتب اسم المناسبة");
                            return;
                        }
                        String e = emoji.getText().toString().trim();
                        pickOccasionDate(e.isEmpty() ? "🎉" : e, n);
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }

    private void pickOccasionDate(final String emoji, final String title) {
        Calendar c = Calendar.getInstance();
        DatePickerDialog dlg = new DatePickerDialog(a, new DatePickerDialog.OnDateSetListener() {
            @Override
            public void onDateSet(DatePicker v, int y, int m, int d) {
                JSONArray arr = Data.list(a, Data.OCCASIONS);
                arr.put(Data.obj("id", Data.nextId(arr), "emoji", emoji, "title", title,
                        "y", y, "m", m, "d", d));
                Data.save(a, Data.OCCASIONS, arr);
                ui.toast("تم الحفظ ✅ سأذكّرك قبلها بأسبوع وبيوم");
                fill();
            }
        }, c.get(Calendar.YEAR), c.get(Calendar.MONTH), c.get(Calendar.DAY_OF_MONTH));
        dlg.setTitle(emoji + " " + title);
        dlg.show();
    }
}
