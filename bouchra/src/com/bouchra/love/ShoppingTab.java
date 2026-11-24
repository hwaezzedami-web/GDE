package com.bouchra.love;

import android.app.AlertDialog;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.widget.Button;
import android.widget.EditText;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;

/** Shopping list ("جيب معاك"), grouped by category, shareable on WhatsApp. */
public class ShoppingTab {

    private final MainActivity a;
    private final Ui ui;
    private LinearLayout body;
    private LinearLayout listBox;
    private int category = 0;

    static final String[] CATS = {"🥬 خضروات", "🍎 فواكه", "🍗 لحوم ودجاج", "🥛 ألبان وبيض",
            "🍞 مخبوزات", "🍚 بقالة", "🧴 منظفات", "🏠 أخرى"};

    // quick suggestions: name, category index
    static final Object[][] SUGGEST = {
            {"طماطم", 0}, {"بصل", 0}, {"بطاطا", 0}, {"جزر", 0}, {"خيار", 0}, {"فلفل", 0}, {"ثوم", 0}, {"خس", 0},
            {"تفاح", 1}, {"موز", 1}, {"برتقال", 1}, {"فراولة", 1}, {"عنب", 1},
            {"دجاج", 2}, {"لحم", 2}, {"سمك", 2}, {"كفتة", 2},
            {"حليب", 3}, {"بيض", 3}, {"جبن", 3}, {"ياغورت", 3}, {"زبدة", 3},
            {"خبز", 4}, {"كرواسون", 4},
            {"أرز", 5}, {"سكر", 5}, {"زيت", 5}, {"قهوة", 5}, {"شاي", 5}, {"معكرونة", 5}, {"طحين", 5}, {"ملح", 5},
            {"صابون", 6}, {"منظف أواني", 6}, {"مسحوق غسيل", 6}, {"مناديل", 6},
    };

    public ShoppingTab(MainActivity a, Ui ui) {
        this.a = a;
        this.ui = ui;
    }

    public View build() {
        body = ui.column();

        // ---- input card ----
        LinearLayout in = ui.card(true);
        in.addView(ui.text("🛒 جيب معاك...", 18, Ui.PINK_DARK, true));
        LinearLayout r = ui.row();
        final EditText e = ui.input("مثل: 2 كيلو طماطم");
        e.setSingleLine(true);
        e.setImeOptions(EditorInfo.IME_ACTION_DONE);
        r.addView(e, ui.weight(1));
        Button add = ui.pinkButton("➕");
        r.addView(add);
        in.addView(r);

        final LinearLayout chips = ui.row();
        HorizontalScrollView hs = new HorizontalScrollView(a);
        hs.setHorizontalScrollBarEnabled(false);
        hs.addView(chips);
        in.addView(hs, ui.margins(-1, -2, 0, 6, 0, 0));
        drawCategoryChips(chips);

        in.addView(ui.text("اقتراحات سريعة (اضغط للإضافة):", 12, Ui.PINK_GRAY, false), ui.margins(-2, -2, 0, 10, 0, 2));
        LinearLayout sugg = ui.row();
        HorizontalScrollView hs2 = new HorizontalScrollView(a);
        hs2.setHorizontalScrollBarEnabled(false);
        hs2.addView(sugg);
        for (final Object[] s : SUGGEST) {
            Button b = ui.button((String) s[0], 0xFFFFF7FA, Ui.PINK);
            b.setTextSize(13);
            b.setPadding(ui.dp(12), ui.dp(5), ui.dp(12), ui.dp(5));
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    addItem((String) s[0], (Integer) s[1]);
                }
            });
            sugg.addView(b, ui.margins(-2, -2, 3, 0, 3, 0));
        }
        in.addView(hs2);

        View.OnClickListener doAdd = new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String t = e.getText().toString().trim();
                if (t.isEmpty()) return;
                addItem(t, category);
                e.setText("");
            }
        };
        add.setOnClickListener(doAdd);
        final View.OnClickListener addRef = doAdd;
        e.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override
            public boolean onEditorAction(TextView v, int id, KeyEvent ev) {
                addRef.onClick(v);
                return true;
            }
        });
        body.addView(in);

        // ---- actions ----
        LinearLayout actions = ui.row();
        actions.setGravity(Gravity.CENTER);
        Button share = ui.pinkButton("📤 أرسل القائمة (واتساب)");
        share.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                shareList();
            }
        });
        actions.addView(share);
        Button clear = ui.softButton("🧹 حذف المُشترى");
        clear.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                clearBought();
            }
        });
        actions.addView(clear, ui.margins(-2, -2, 8, 0, 0, 0));
        body.addView(actions, ui.margins(-1, -2, 0, 6, 0, 0));

        listBox = ui.column();
        body.addView(listBox);
        fillList();
        return ui.page(body, null);
    }

    private void drawCategoryChips(final LinearLayout chips) {
        chips.removeAllViews();
        for (int i = 0; i < CATS.length; i++) {
            final int idx = i;
            boolean sel = i == category;
            Button b = ui.button(CATS[i], sel ? Ui.PINK : Ui.PINK_SOFT, sel ? Color.WHITE : Ui.PINK_DARK);
            b.setTextSize(12);
            b.setPadding(ui.dp(12), ui.dp(5), ui.dp(12), ui.dp(5));
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    category = idx;
                    drawCategoryChips(chips);
                }
            });
            chips.addView(b, ui.margins(-2, -2, 3, 0, 3, 0));
        }
    }

    private void addItem(String text, int cat) {
        JSONArray arr = Data.list(a, Data.SHOPPING);
        for (JSONObject o : Data.items(arr)) {
            if (!o.optBoolean("bought") && o.optString("text").equals(text)) {
                ui.toast("موجود في القائمة ✅");
                return;
            }
        }
        arr.put(Data.obj("id", Data.nextId(arr), "text", text, "cat", cat, "bought", false));
        Data.save(a, Data.SHOPPING, arr);
        ui.toast("أُضيف: " + text);
        fillList();
    }

    private void fillList() {
        listBox.removeAllViews();
        List<JSONObject> items = Data.items(Data.list(a, Data.SHOPPING));
        int left = 0;
        for (JSONObject o : items) if (!o.optBoolean("bought")) left++;

        TextView count = ui.section(items.isEmpty() ? "القائمة فارغة 🌸"
                : "📝 تبقّى " + left + " من " + items.size());
        listBox.addView(count);

        for (int c = 0; c < CATS.length; c++) {
            LinearLayout group = null;
            for (final JSONObject o : items) {
                int cat = o.optInt("cat", CATS.length - 1);
                if (cat < 0 || cat >= CATS.length) cat = CATS.length - 1;
                if (cat != c) continue;
                if (group == null) {
                    group = ui.card(true);
                    group.addView(ui.text(CATS[c], 14, Ui.PINK, true));
                    listBox.addView(group);
                }
                group.addView(itemRow(o));
            }
        }
    }

    private View itemRow(final JSONObject o) {
        boolean bought = o.optBoolean("bought");
        TextView t = ui.text((bought ? "✅  " : "⬜  ") + o.optString("text"), 16,
                bought ? Ui.PINK_GRAY : Ui.PINK_DARK, false);
        if (bought) t.setPaintFlags(t.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
        t.setPadding(ui.dp(4), ui.dp(10), ui.dp(4), ui.dp(10));
        t.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                JSONArray arr = Data.list(a, Data.SHOPPING);
                JSONObject cur = Data.find(arr, o.optInt("id"));
                if (cur == null) return;
                Data.put(cur, "bought", !cur.optBoolean("bought"));
                Data.save(a, Data.SHOPPING, arr);
                fillList();
            }
        });
        t.setOnLongClickListener(new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                JSONArray arr = Data.list(a, Data.SHOPPING);
                Data.remove(arr, o.optInt("id"));
                Data.save(a, Data.SHOPPING, arr);
                ui.toast("حُذف: " + o.optString("text"));
                fillList();
                return true;
            }
        });
        return t;
    }

    private void clearBought() {
        new AlertDialog.Builder(a)
                .setTitle("حذف كل ما تم شراؤه؟")
                .setPositiveButton("حذف", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        JSONArray arr = Data.list(a, Data.SHOPPING);
                        JSONArray keep = new JSONArray();
                        for (JSONObject o : Data.items(arr)) if (!o.optBoolean("bought")) keep.put(o);
                        Data.save(a, Data.SHOPPING, keep);
                        fillList();
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }

    private void shareList() {
        List<JSONObject> items = Data.items(Data.list(a, Data.SHOPPING));
        StringBuilder sb = new StringBuilder("🛒 جيب معاك يا حبيبي 💕\n");
        int n = 0;
        for (int c = 0; c < CATS.length; c++) {
            boolean header = false;
            for (JSONObject o : items) {
                if (o.optBoolean("bought") || o.optInt("cat", CATS.length - 1) != c) continue;
                if (!header) {
                    sb.append("\n").append(CATS[c]).append(":\n");
                    header = true;
                }
                sb.append("• ").append(o.optString("text")).append("\n");
                n++;
            }
        }
        if (n == 0) {
            ui.toast("لا يوجد شيء لإرساله");
            return;
        }
        Data.share(a, sb.toString());
    }
}
