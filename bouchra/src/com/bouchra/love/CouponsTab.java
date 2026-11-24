package com.bouchra.love;

import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/** "كوبونات الحب": gift coupons Bouchra can redeem any time. */
public class CouponsTab {

    private final MainActivity a;
    private final Ui ui;
    private LinearLayout body;

    private static final String[][] DEFAULTS = {
            {"💆‍♀️", "مساج 30 دقيقة"},
            {"🍽️", "أنا أغسل الصحون اليوم"},
            {"🍕", "عشاء في مطعم من اختيارك"},
            {"👩‍🍳", "يوم كامل بدون طبخ"},
            {"🍳", "فطور في السرير"},
            {"🎬", "فيلم من اختيارك وأنا لا أعترض"},
            {"🤗", "حضن طويل 10 دقائق"},
            {"🚶‍♀️", "نزهة إلى المكان الذي تحبينه"},
            {"👑", "أنتِ تأمرين وأنا أطيع لمدة ساعة"},
            {"🎁", "هدية مفاجئة"},
            {"🛍️", "يوم تسوق معاً"},
            {"📵", "سهرة كاملة بدون هاتف"},
            {"🍦", "آيس كريم في أي وقت"},
            {"🧹", "أنظف البيت بدلاً منكِ"},
            {"😴", "نوم إضافي وأنا أتكفل بكل شيء"},
            {"💐", "باقة ورد"},
    };

    public CouponsTab(MainActivity a, Ui ui) {
        this.a = a;
        this.ui = ui;
    }

    private JSONArray load() {
        if (!Data.has(a, Data.COUPONS)) {
            JSONArray arr = new JSONArray();
            for (int i = 0; i < DEFAULTS.length; i++) {
                arr.put(Data.obj("id", i + 1, "emoji", DEFAULTS[i][0], "title", DEFAULTS[i][1],
                        "used", false, "usedDate", 0L));
            }
            Data.save(a, Data.COUPONS, arr);
            return arr;
        }
        return Data.list(a, Data.COUPONS);
    }

    public View build() {
        body = ui.column();
        fill();
        Button fab = ui.fab("➕  كوبون جديد");
        fab.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                addCoupon();
            }
        });
        return ui.page(body, fab);
    }

    private void fill() {
        body.removeAllViews();
        List<JSONObject> items = Data.items(load());
        int active = 0;
        for (JSONObject o : items) if (!o.optBoolean("used")) active++;

        TextView intro = ui.text("🎟️ كوبونات الحب\nهدايا لبشرى تستعملها متى شاءت، وعلى الزوج التنفيذ 😄", 14,
                Ui.PINK_DARK, true);
        intro.setGravity(Gravity.CENTER);
        intro.setBackground(ui.rounded(Ui.PINK_SOFT, 16));
        intro.setPadding(ui.dp(12), ui.dp(12), ui.dp(12), ui.dp(12));
        body.addView(intro, ui.margins(-1, -2, 2, 6, 2, 4));

        body.addView(ui.section("✨ متاحة (" + active + ")"));
        for (JSONObject o : items) if (!o.optBoolean("used")) body.addView(ticket(o));
        if (active < items.size()) {
            body.addView(ui.section("✔ مُستعملة"));
            for (JSONObject o : items) if (o.optBoolean("used")) body.addView(ticket(o));
        }
    }

    private View ticket(final JSONObject o) {
        final boolean used = o.optBoolean("used");
        LinearLayout c = ui.row();
        c.setPadding(ui.dp(14), ui.dp(14), ui.dp(14), ui.dp(14));
        GradientDrawable bg;
        if (used) {
            bg = ui.rounded(Ui.MUTED_BG, 16);
            bg.setStroke(ui.dp(2), Ui.MUTED_LINE, ui.dp(8), ui.dp(5));
        } else {
            bg = new GradientDrawable(GradientDrawable.Orientation.RIGHT_LEFT, new int[]{Ui.PINK, Ui.PINK_LIGHT});
            bg.setCornerRadius(ui.dp(16));
            bg.setStroke(ui.dp(2), Color.WHITE, ui.dp(8), ui.dp(5));
        }
        c.setBackground(bg);
        c.setElevation(ui.dp(used ? 0 : 3));
        c.setLayoutParams(ui.margins(-1, -2, 2, 6, 2, 6));

        TextView emoji = ui.text(o.optString("emoji", "🎟️"), 30, Color.WHITE, false);
        c.addView(emoji);

        LinearLayout texts = ui.column();
        texts.setPadding(ui.dp(12), 0, ui.dp(8), 0);
        texts.addView(ui.text("كوبون: " + o.optString("title"), 16, used ? Ui.PINK_GRAY : Color.WHITE, true));
        texts.addView(ui.text(used ? "استُعمل في " + Data.date(o.optLong("usedDate")) : "صالح دائماً 💕",
                12, used ? Ui.PINK_GRAY : 0xFFFFE4EF, false));
        c.addView(texts, ui.weight(1));

        if (!used) {
            LinearLayout btns = ui.column();
            Button use = ui.button("💝 استعمال", Color.WHITE, Ui.PINK_DARK);
            use.setTextSize(13);
            use.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    redeem(o);
                }
            });
            btns.addView(use);
            Button send = ui.button("📤 إرسال", 0x33FFFFFF, Color.WHITE);
            send.setTextSize(12);
            send.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    Data.share(a, "🎟️ كوبون حب من زوجك 💕\n\n" + o.optString("emoji") + " " + o.optString("title")
                            + "\n\nصالح دائماً، استعمليه متى شئتِ يا بشرى ❤️");
                }
            });
            btns.addView(send, ui.margins(-1, -2, 0, 6, 0, 0));
            c.addView(btns);
        }

        c.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                String[] opts = used ? new String[]{"♻️ إعادة تفعيل", "🗑️ حذف"} : new String[]{"🗑️ حذف"};
                new AlertDialog.Builder(a)
                        .setTitle(o.optString("title"))
                        .setItems(opts, new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface d, int which) {
                                JSONArray arr = load();
                                if (used && which == 0) {
                                    JSONObject cur = Data.find(arr, o.optInt("id"));
                                    if (cur != null) Data.put(cur, "used", false);
                                } else {
                                    Data.remove(arr, o.optInt("id"));
                                }
                                Data.save(a, Data.COUPONS, arr);
                                fill();
                            }
                        }).show();
                return true;
            }
        });
        return c;
    }

    private void redeem(final JSONObject o) {
        new AlertDialog.Builder(a)
                .setTitle(o.optString("emoji") + " استعمال الكوبون؟")
                .setMessage(o.optString("title"))
                .setPositiveButton("نعم 💝", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        JSONArray arr = load();
                        JSONObject cur = Data.find(arr, o.optInt("id"));
                        if (cur == null) return;
                        Data.put(cur, "used", true);
                        Data.put(cur, "usedDate", System.currentTimeMillis());
                        Data.save(a, Data.COUPONS, arr);
                        ui.toast("🎉 تم! على زوجك التنفيذ الآن 😄");
                        fill();
                    }
                })
                .setNegativeButton("ليس الآن", null).show();
    }

    private void addCoupon() {
        LinearLayout box = ui.dialogBox();
        final EditText emoji = ui.input("رمز تعبيري");
        emoji.setText("🎟️");
        box.addView(emoji);
        final EditText title = ui.input("الكوبون (مثل: رحلة نهاية الأسبوع)");
        box.addView(title);
        new AlertDialog.Builder(a)
                .setTitle("🎟️ كوبون جديد")
                .setView(box)
                .setPositiveButton("إضافة", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String t = title.getText().toString().trim();
                        if (t.isEmpty()) return;
                        String e = emoji.getText().toString().trim();
                        JSONArray arr = load();
                        JSONArray out = new JSONArray();
                        out.put(Data.obj("id", Data.nextId(arr), "emoji", e.isEmpty() ? "🎟️" : e, "title", t,
                                "used", false, "usedDate", 0L));
                        for (JSONObject o : Data.items(arr)) out.put(o);
                        Data.save(a, Data.COUPONS, out);
                        fill();
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }
}
