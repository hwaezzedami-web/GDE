package com.bouchra.love;

import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/** "أحلامنا": dreams and goals, with an optional savings target. */
public class DreamsTab {

    private final MainActivity a;
    private final Ui ui;
    private LinearLayout body;

    private static final Object[][] DEFAULTS = {
            {"🕋", "عمرة معاً", 0L},
            {"✈️", "رحلة سفر لبلد جديد", 0L},
            {"🏡", "بيت أحلامنا", 0L},
            {"🍽️", "تجربة مطعم جديد", 0L},
            {"🌊", "يوم كامل على البحر", 0L},
    };

    public DreamsTab(MainActivity a, Ui ui) {
        this.a = a;
        this.ui = ui;
    }

    private JSONArray load() {
        if (!Data.has(a, Data.DREAMS)) {
            JSONArray arr = new JSONArray();
            for (int i = 0; i < DEFAULTS.length; i++) {
                arr.put(Data.obj("id", i + 1, "emoji", DEFAULTS[i][0], "title", DEFAULTS[i][1],
                        "target", DEFAULTS[i][2], "saved", 0L, "done", false, "doneDate", 0L));
            }
            Data.save(a, Data.DREAMS, arr);
            return arr;
        }
        return Data.list(a, Data.DREAMS);
    }

    public View build() {
        body = ui.column();
        fill();
        Button fab = ui.fab("➕  حلم جديد");
        fab.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                addDream();
            }
        });
        return ui.page(body, fab);
    }

    private void fill() {
        body.removeAllViews();
        List<JSONObject> items = Data.items(load());
        int done = 0;
        for (JSONObject o : items) if (o.optBoolean("done")) done++;

        LinearLayout head = ui.card(true);
        head.setGravity(Gravity.CENTER_HORIZONTAL);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{0xFFC2185B, Ui.PINK_LIGHT});
        g.setCornerRadius(ui.dp(20));
        head.setBackground(g);
        TextView t = ui.text("✨ أحلامنا معاً ✨", 20, Color.WHITE, true);
        t.setGravity(Gravity.CENTER);
        head.addView(t);
        TextView s = ui.text("حققنا " + done + " من " + items.size() + " أحلام 🌟", 14, 0xFFFFE4EF, false);
        s.setGravity(Gravity.CENTER);
        head.addView(s);
        if (!items.isEmpty()) {
            head.addView(ui.progress(items.isEmpty() ? 0 : done / (float) items.size()));
        }
        body.addView(head);

        body.addView(ui.section("💭 نحلم بـ..."));
        for (JSONObject o : items) if (!o.optBoolean("done")) body.addView(dreamCard(o));
        if (done > 0) {
            body.addView(ui.section("🎉 تحققت الحمد لله"));
            for (JSONObject o : items) if (o.optBoolean("done")) body.addView(dreamCard(o));
        }
        TextView tip = ui.text("اضغط مطولاً على أي حلم لحذفه", 11, Ui.PINK_GRAY, false);
        tip.setGravity(Gravity.CENTER);
        tip.setPadding(0, ui.dp(10), 0, 0);
        body.addView(tip);
    }

    private View dreamCard(final JSONObject o) {
        final boolean done = o.optBoolean("done");
        LinearLayout c = ui.card(!done);

        LinearLayout top = ui.row();
        top.addView(ui.emojiBubble(o.optString("emoji", "✨"), 46));
        LinearLayout texts = ui.column();
        texts.setPadding(ui.dp(12), 0, 0, 0);
        texts.addView(ui.text(o.optString("title"), 16, done ? Ui.PINK_GRAY : Ui.PINK_DARK, true));
        if (done) {
            texts.addView(ui.text("✅ تحقق في " + Data.date(o.optLong("doneDate")), 12, Ui.PINK, false));
        }
        top.addView(texts, ui.weight(1));
        c.addView(top);

        long target = o.optLong("target");
        long saved = o.optLong("saved");
        if (target > 0) {
            int pct = (int) Math.min(100, saved * 100 / target);
            c.addView(ui.progress(saved / (float) target));
            c.addView(ui.text("💰 جمعنا " + Data.money(saved) + " من " + Data.money(target) + "  (" + pct + "%)",
                    12, Ui.PINK_GRAY, false));
        }

        if (!done) {
            LinearLayout btns = ui.row();
            btns.setGravity(Gravity.START);
            if (target > 0) {
                Button money = ui.softButton("➕ أضف مبلغاً");
                money.setOnClickListener(new View.OnClickListener() {
                    @Override
                    public void onClick(View v) {
                        addMoney(o.optInt("id"));
                    }
                });
                btns.addView(money, ui.margins(-2, -2, 0, 0, 8, 0));
            }
            Button ok = ui.pinkButton("🎉 تحقق!");
            ok.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    JSONArray arr = load();
                    JSONObject cur = Data.find(arr, o.optInt("id"));
                    if (cur == null) return;
                    Data.put(cur, "done", true);
                    Data.put(cur, "doneDate", System.currentTimeMillis());
                    Data.save(a, Data.DREAMS, arr);
                    celebrate(cur.optString("title"));
                    fill();
                }
            });
            btns.addView(ok);
            c.addView(btns, ui.margins(-1, -2, 0, 10, 0, 0));
        }

        c.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                String[] opts = done ? new String[]{"↩️ إرجاعه إلى الأحلام", "🗑️ حذف"} : new String[]{"🗑️ حذف"};
                new AlertDialog.Builder(a)
                        .setTitle(o.optString("title"))
                        .setItems(opts, new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int which) {
                                JSONArray arr = load();
                                if (done && which == 0) {
                                    JSONObject cur = Data.find(arr, o.optInt("id"));
                                    if (cur != null) Data.put(cur, "done", false);
                                } else {
                                    Data.remove(arr, o.optInt("id"));
                                }
                                Data.save(a, Data.DREAMS, arr);
                                fill();
                            }
                        }).show();
                return true;
            }
        });
        return c;
    }

    private void celebrate(String title) {
        new AlertDialog.Builder(a)
                .setTitle("🎉🎊 مبروك! 🎊🎉")
                .setMessage("تحقق حلمكما: " + title + "\n\nالحمد لله، وعقبال باقي الأحلام 💕")
                .setPositiveButton("الحمد لله ❤️", null).show();
    }

    private void addMoney(final int id) {
        LinearLayout box = ui.dialogBox();
        final EditText amount = ui.input("المبلغ");
        amount.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_SIGNED);
        box.addView(amount);
        box.addView(ui.text("اكتب رقماً سالباً (مثل -500) لإنقاص المبلغ", 11, Ui.PINK_GRAY, false));
        new AlertDialog.Builder(a)
                .setTitle("💰 أضف إلى الحصالة")
                .setView(box)
                .setPositiveButton("إضافة", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        long v;
                        try {
                            v = Long.parseLong(amount.getText().toString().trim());
                        } catch (Exception e) {
                            return;
                        }
                        JSONArray arr = load();
                        JSONObject cur = Data.find(arr, id);
                        if (cur == null) return;
                        long saved = Math.max(0, cur.optLong("saved") + v);
                        Data.put(cur, "saved", saved);
                        Data.save(a, Data.DREAMS, arr);
                        if (saved >= cur.optLong("target") && v > 0) ui.toast("🎯 وصلتما للهدف! اضغطا «تحقق»");
                        fill();
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }

    private void addDream() {
        LinearLayout box = ui.dialogBox();
        final EditText emoji = ui.input("رمز تعبيري");
        emoji.setText("✨");
        box.addView(emoji);
        final EditText title = ui.input("ما هو حلمكما؟ (مثل: سفر إلى تركيا)");
        box.addView(title);
        final EditText target = ui.input("المبلغ المطلوب (اختياري)");
        target.setInputType(InputType.TYPE_CLASS_NUMBER);
        box.addView(target);
        new AlertDialog.Builder(a)
                .setTitle("✨ حلم جديد")
                .setView(box)
                .setPositiveButton("إضافة", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String t = title.getText().toString().trim();
                        if (t.isEmpty()) {
                            ui.toast("اكتب الحلم أولاً");
                            return;
                        }
                        long tg = 0;
                        try {
                            tg = Long.parseLong(target.getText().toString().trim());
                        } catch (Exception ignored) {
                        }
                        String e = emoji.getText().toString().trim();
                        JSONArray arr = load();
                        arr.put(Data.obj("id", Data.nextId(arr), "emoji", e.isEmpty() ? "✨" : e, "title", t,
                                "target", tg, "saved", 0L, "done", false, "doneDate", 0L));
                        Data.save(a, Data.DREAMS, arr);
                        fill();
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }
}
