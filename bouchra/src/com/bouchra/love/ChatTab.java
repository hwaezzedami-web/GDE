package com.bouchra.love;

import android.app.AlertDialog;
import android.app.ProgressDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.DialogInterface;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.os.Handler;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Collections;
import java.util.Date;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Private chat between the two of us, plus the account / linking setup. */
@SuppressWarnings("deprecation")
public class ChatTab implements Tab {

    private final MainActivity a;
    private final Ui ui;
    private FrameLayout root;

    private Cloud.Stream msgStream;
    private Cloud.Stream profStream;
    private JSONObject msgs = new JSONObject();
    private JSONObject profiles = new JSONObject();
    private final Map<String, JSONObject> sending = new LinkedHashMap<String, JSONObject>();
    private final Set<String> markedRead = new HashSet<String>();

    private LinearLayout list;
    private ScrollView scroll;
    private TextView nameView;
    private TextView statusView;
    private TextView moodLine;
    private TextView avatar;
    private EditText input;
    private View inviteBox;
    private long lastTyping;
    private long lastPresence;
    private boolean active;
    private boolean busy;
    private final Handler h = new Handler();
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            if (!active) return;
            updateHeader();
            if (System.currentTimeMillis() - lastPresence > 60000) presence(true);
            h.postDelayed(this, 4000);
        }
    };

    private static final String[][] MOODS = {
            {"😊", "سعيد", "سعيدة"}, {"🥰", "مشتاق", "مشتاقة"}, {"😴", "متعب", "متعبة"},
            {"😢", "حزين", "حزينة"}, {"😡", "غاضب", "غاضبة"}, {"🤒", "مريض", "مريضة"},
            {"🤩", "متحمس", "متحمسة"}, {"😌", "هادئ", "هادئة"}, {"🍽️", "جائع", "جائعة"},
            {"🤗", "أحتاج حضناً", "أحتاج حضناً"},
    };

    public ChatTab(MainActivity a, Ui ui) {
        this.a = a;
        this.ui = ui;
    }

    public View build() {
        root = new FrameLayout(a);
        active = true;
        render();
        return root;
    }

    public void refresh() {
    }

    public void hide() {
        active = false;
        LoveService.chatVisible = false;
        h.removeCallbacks(tick);
        closeStreams();
        if (Cloud.linked(a)) presence(false);
    }

    private void closeStreams() {
        if (msgStream != null) msgStream.close();
        if (profStream != null) profStream.close();
        msgStream = null;
        profStream = null;
    }

    private String base() {
        return "couples/" + Cloud.cid(a);
    }

    private void render() {
        closeStreams();
        h.removeCallbacks(tick);
        root.removeAllViews();
        if (Cloud.linked(a)) {
            LoveService.start(a);
            root.addView(chatView(), new FrameLayout.LayoutParams(-1, -1));
            msgs = new JSONObject();
            profiles = new JSONObject();
            startStreams();
            LoveService.chatVisible = true;
            presence(true);
            h.post(tick);
        } else {
            LoveService.chatVisible = false;
            root.addView(setupView(), new FrameLayout.LayoutParams(-1, -1));
            String pending = Data.p(a).getString("pending_invite", "");
            if (Cloud.signedIn(a) && !pending.isEmpty() && !busy) doJoin(pending);
        }
    }

    // =====================================================================
    // setup: server config -> account -> link
    // =====================================================================

    private View setupView() {
        LinearLayout body = ui.column();

        LinearLayout intro = ui.card(true);
        intro.setGravity(Gravity.CENTER_HORIZONTAL);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{Ui.PINK, Ui.PINK_LIGHT});
        g.setCornerRadius(ui.dp(20));
        intro.setBackground(g);
        TextView t = ui.text("💬 مساحتكما الخاصة", 20, Color.WHITE, true);
        t.setGravity(Gravity.CENTER);
        intro.addView(t);
        TextView d = ui.text(Data.g(a,
                "دردشة بينك وبين بشرى فقط 💕\nوتصبح المشتريات والأحلام والكوبونات والمناسبات مشتركة بين هاتفيكما.",
                "دردشة بينك وبين زوجك فقط 💕\nوتصبح المشتريات والأحلام والكوبونات والمناسبات مشتركة بين هاتفيكما."),
                14, 0xFFFFE4EF, false);
        d.setGravity(Gravity.CENTER);
        intro.addView(d);
        body.addView(intro);

        if (!Cloud.configured(a)) body.addView(configCard());
        else if (!Cloud.signedIn(a)) body.addView(accountCard());
        else body.addView(linkCard());
        return ui.page(body, null);
    }

    private View configCard() {
        LinearLayout c = ui.card(true);
        if (Data.isWife(a)) {
            c.addView(ui.text("💌 الخطوة 1: الدعوة", 17, Ui.PINK_DARK, true));
            c.addView(ui.text("اطلبي من زوجك إرسال رسالة الدعوة من تطبيقه، ثم انسخيها والصقيها هنا.", 13, Ui.PINK_GRAY, false));
            Button inv = ui.pinkButton("📥 لدي دعوة");
            inv.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    pasteInvite();
                }
            });
            c.addView(inv, ui.margins(-1, -2, 0, 12, 0, 0));
            c.addView(ui.text("أو إن كان لديك إعدادات Firebase:", 12, Ui.PINK_GRAY, false), ui.margins(-2, -2, 0, 16, 0, 0));
        } else {
            c.addView(ui.text("⚙️ الخطوة 1: ربط الخادم (مرة واحدة)", 17, Ui.PINK_DARK, true));
            c.addView(ui.text("الصق القيمتين من مشروع Firebase الخاص بك. بشرى لن تحتاج هذا: يكفيها لصق رسالة الدعوة 💌",
                    13, Ui.PINK_GRAY, false));
        }
        final EditText key = ui.input("Web API Key  (يبدأ بـ AIza)");
        key.setSingleLine(true);
        key.setTextDirection(View.TEXT_DIRECTION_LTR);
        c.addView(key);
        final EditText db = ui.input("Database URL  (https://...firebaseio.com)");
        db.setSingleLine(true);
        db.setTextDirection(View.TEXT_DIRECTION_LTR);
        db.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        c.addView(db);
        Button save = Data.isWife(a) ? ui.softButton("💾 حفظ") : ui.pinkButton("💾 حفظ ومتابعة");
        save.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String k = key.getText().toString().trim();
                String u = db.getText().toString().trim();
                if (k.length() < 20 || u.length() < 10) {
                    ui.toast("الصق المفتاح والرابط كاملين");
                    return;
                }
                if (!u.contains("firebaseio.com") && !u.contains("firebasedatabase.app")) {
                    ui.toast("الرابط يجب أن يكون رابط Realtime Database");
                    return;
                }
                Cloud.setConfig(a, k, u);
                render();
            }
        });
        c.addView(save, ui.margins(-1, -2, 0, 10, 0, 0));
        if (!Data.isWife(a)) {
            Button inv = ui.softButton("📥 لدي دعوة بدلاً من ذلك");
            inv.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    pasteInvite();
                }
            });
            c.addView(inv, ui.margins(-1, -2, 0, 8, 0, 0));
        }
        return c;
    }

    private View accountCard() {
        LinearLayout c = ui.card(true);
        c.addView(ui.text("👤 الخطوة 2: حسابك", 17, Ui.PINK_DARK, true));
        final boolean invited = !Data.p(a).getString("pending_invite", "").isEmpty();
        if (invited) {
            TextView n = ui.text(Data.g(a, "💌 تم قبول الدعوة! أنشئ حسابك وسيتم ربطك تلقائياً",
                    "💌 تم قبول الدعوة! أنشئي حسابك وسيتم ربطك تلقائياً"), 13, Ui.PINK, true);
            c.addView(n);
        } else {
            c.addView(ui.text(Data.g(a, "حساب خاص بك. بشرى ستنشئ حسابها على هاتفها.",
                    "حساب خاص بكِ. زوجك له حسابه على هاتفه."), 13, Ui.PINK_GRAY, false));
        }
        final EditText name = ui.input("الاسم");
        String n0 = Cloud.myName(a);
        name.setText(n0.isEmpty() && Data.isWife(a) ? "بشرى" : n0);
        c.addView(name);
        final EditText email = ui.input("البريد الإلكتروني");
        email.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS);
        email.setTextDirection(View.TEXT_DIRECTION_LTR);
        c.addView(email);
        final EditText pass = ui.input("كلمة السر (6 أحرف على الأقل)");
        pass.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        c.addView(pass);

        LinearLayout btns = ui.row();
        Button create = ui.pinkButton("✨ إنشاء حساب");
        Button login = ui.softButton("🔑 لدي حساب");
        btns.addView(create, ui.weight(1));
        btns.addView(login, ui.margins(0, -2, 8, 0, 0, 0));
        ((LinearLayout.LayoutParams) login.getLayoutParams()).weight = 1;
        c.addView(btns, ui.margins(-1, -2, 0, 12, 0, 0));

        create.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                final String nm = name.getText().toString().trim();
                final String em = email.getText().toString().trim();
                final String pw = pass.getText().toString();
                if (nm.isEmpty()) {
                    ui.toast("اكتب الاسم");
                    return;
                }
                if (em.isEmpty() || pw.length() < 6) {
                    ui.toast("اكتب البريد وكلمة سر من 6 أحرف أو أكثر");
                    return;
                }
                run("⏳ جاري إنشاء الحساب...", new Cloud.Job() {
                    @Override
                    public Object run() throws Exception {
                        Cloud.signUp(a, em, pw, nm);
                        return null;
                    }
                }, "🎉 تم إنشاء الحساب");
            }
        });
        login.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                final String em = email.getText().toString().trim();
                final String pw = pass.getText().toString();
                final String nm = name.getText().toString().trim();
                if (em.isEmpty() || pw.isEmpty()) {
                    ui.toast("اكتب البريد وكلمة السر");
                    return;
                }
                run("⏳ جاري تسجيل الدخول...", new Cloud.Job() {
                    @Override
                    public Object run() throws Exception {
                        Cloud.signIn(a, em, pw);
                        if (Cloud.myName(a).isEmpty() && !nm.isEmpty()) {
                            Data.p(a).edit().putString("my_name", nm).commit();
                            Cloud.patch(a, "users/" + Cloud.uid(a), Data.obj("name", nm, "role", Data.role(a)));
                        }
                        return null;
                    }
                }, "👋 أهلاً بعودتك");
            }
        });

        if (!invited) {
            Button inv = ui.softButton("📥 لدي دعوة");
            inv.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    pasteInvite();
                }
            });
            c.addView(inv, ui.margins(-1, -2, 0, 8, 0, 0));
        }
        return c;
    }

    private View linkCard() {
        LinearLayout c = ui.card(true);
        c.addView(ui.text("💞 الخطوة 3: الربط", 17, Ui.PINK_DARK, true));
        if (!Data.p(a).getString("pending_invite", "").isEmpty()) {
            c.addView(ui.text("⏳ جاري الربط...", 14, Ui.PINK, true));
            return c;
        }
        c.addView(ui.text(Data.g(a,
                "أنشئ دعوة وأرسلها لبشرى على واتساب، أو الصق دعوة وصلتك منها.",
                "الصقي رسالة الدعوة التي أرسلها لكِ زوجك 💌"), 13, Ui.PINK_GRAY, false));

        Button inv = Data.isWife(a) ? ui.pinkButton("📥 لدي دعوة") : ui.softButton("📥 لدي دعوة");
        inv.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pasteInvite();
            }
        });
        Button create = Data.isWife(a) ? ui.softButton("💌 إنشاء دعوة") : ui.pinkButton("💌 إنشاء دعوة");
        create.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                run("⏳ جاري الإنشاء...", new Cloud.Job() {
                    @Override
                    public Object run() throws Exception {
                        Cloud.createInvite(a);
                        return null;
                    }
                }, "✅ تم! أرسل الدعوة الآن");
            }
        });
        if (Data.isWife(a)) {
            c.addView(inv, ui.margins(-1, -2, 0, 12, 0, 0));
            c.addView(create, ui.margins(-1, -2, 0, 8, 0, 0));
        } else {
            c.addView(create, ui.margins(-1, -2, 0, 12, 0, 0));
            c.addView(inv, ui.margins(-1, -2, 0, 8, 0, 0));
        }
        Button out = ui.button("تسجيل الخروج", Color.TRANSPARENT, Ui.PINK_GRAY);
        out.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                Cloud.signOut(a);
                render();
            }
        });
        c.addView(out, ui.margins(-1, -2, 0, 8, 0, 0));
        return c;
    }

    /** Runs a blocking job with a progress dialog, then re-renders. */
    private void run(String waitText, Cloud.Job job, final String okText) {
        if (busy) return;
        busy = true;
        final ProgressDialog pd = ProgressDialog.show(a, null, waitText, true, false);
        Cloud.async(a, job, new Cloud.Done() {
            @Override
            public void ok(Object r) {
                busy = false;
                dismiss(pd);
                ui.toast(okText);
                if (active) render();
            }

            @Override
            public void fail(String m) {
                busy = false;
                dismiss(pd);
                new AlertDialog.Builder(a).setTitle("😕 لم ينجح").setMessage(m).setPositiveButton("حسناً", null).show();
                if (active) render();
            }
        });
    }

    private static void dismiss(ProgressDialog pd) {
        try {
            pd.dismiss();
        } catch (Exception ignored) {
        }
    }

    private void doJoin(final String code) {
        run("💞 جاري الربط...", new Cloud.Job() {
            @Override
            public Object run() throws Exception {
                Cloud.join(a, code);
                return null;
            }
        }, "🎉 تم الربط! أصبحتما معاً 💕");
    }

    private void pasteInvite() {
        LinearLayout box = ui.dialogBox();
        final EditText e = ui.input("الصق رسالة الدعوة كاملة هنا");
        e.setMinLines(3);
        e.setTextSize(13);
        try {
            ClipboardManager cm = (ClipboardManager) a.getSystemService(Context.CLIPBOARD_SERVICE);
            ClipData cd = cm.getPrimaryClip();
            if (cd != null && cd.getItemCount() > 0) {
                CharSequence s = cd.getItemAt(0).coerceToText(a);
                if (s != null && s.toString().contains("BOUCHRA:")) e.setText(s);
            }
        } catch (Exception ignored) {
        }
        box.addView(e);
        new AlertDialog.Builder(a)
                .setTitle("📥 رسالة الدعوة")
                .setView(box)
                .setPositiveButton("متابعة", new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int w) {
                        String code = Cloud.readInvite(a, e.getText().toString());
                        if (code == null) {
                            ui.toast("الرسالة غير صحيحة. انسخ الرسالة كاملة من واتساب");
                            return;
                        }
                        render();
                    }
                })
                .setNegativeButton("إلغاء", null).show();
    }

    // =====================================================================
    // chat
    // =====================================================================

    private View chatView() {
        LinearLayout col = ui.column();

        // ---- partner header ----
        LinearLayout top = ui.row();
        top.setPadding(ui.dp(14), ui.dp(10), ui.dp(14), ui.dp(10));
        top.setBackgroundColor(Color.WHITE);
        top.setElevation(ui.dp(3));
        avatar = ui.emojiBubble(Data.isWife(a) ? "🤵" : "👰", 46);
        top.addView(avatar);
        LinearLayout mid = ui.column();
        mid.setPadding(ui.dp(10), 0, ui.dp(6), 0);
        nameView = ui.text(Cloud.partnerName(a), 17, Ui.PINK_DARK, true);
        mid.addView(nameView);
        statusView = ui.text("", 12, Ui.PINK_GRAY, false);
        mid.addView(statusView);
        moodLine = ui.text("", 12, Ui.PINK, false);
        mid.addView(moodLine);
        top.addView(mid, ui.weight(1));

        LinearLayout actions = ui.column();
        Button miss = ui.pinkButton(Data.g(a, "💗 اشتقت لكِ", "💗 اشتقت لك"));
        miss.setTextSize(13);
        miss.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                v.animate().scaleX(1.15f).scaleY(1.15f).setDuration(120).withEndAction(new Runnable() {
                    @Override
                    public void run() {
                        v.animate().scaleX(1f).scaleY(1f).setDuration(160).start();
                    }
                }).start();
                send(Data.g(a, "اشتقت لكِ 💗", "اشتقت لك 💗"), "miss");
            }
        });
        actions.addView(miss);
        Button mood = ui.softButton("🎭 مزاجي");
        mood.setTextSize(12);
        mood.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                pickMood();
            }
        });
        actions.addView(mood, ui.margins(-1, -2, 0, 4, 0, 0));
        top.addView(actions);
        col.addView(top, new LinearLayout.LayoutParams(-1, -2));

        // ---- waiting for partner ----
        inviteBox = inviteView();
        col.addView(inviteBox);

        // ---- messages ----
        scroll = new ScrollView(a);
        list = ui.column();
        list.setPadding(ui.dp(10), ui.dp(8), ui.dp(10), ui.dp(8));
        scroll.addView(list);
        col.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1f));

        // ---- quick replies ----
        String[] quick = Data.isWife(a)
                ? new String[]{"أحبك ❤️", "متى ترجع؟ 🏠", "أنا في الطريق 🚗", "وصلت ✅", "اتصل بي 📞", "حاضر يا عمري 😘", "تصبح على خير 🌙"}
                : new String[]{"أحبكِ ❤️", "ماذا تحتاجين؟ 🛒", "أنا في الطريق 🚗", "وصلت ✅", "اتصلي بي 📞", "حاضر يا عمري 😘", "تصبحين على خير 🌙"};
        LinearLayout chips = ui.row();
        chips.setPadding(ui.dp(6), ui.dp(4), ui.dp(6), ui.dp(2));
        for (final String q : quick) {
            Button b = ui.button(q, Color.WHITE, Ui.PINK);
            b.setTextSize(12);
            b.setPadding(ui.dp(12), ui.dp(5), ui.dp(12), ui.dp(5));
            GradientDrawable bg = ui.rounded(Color.WHITE, 16);
            bg.setStroke(ui.dp(1), Ui.PINK_LINE);
            b.setBackground(bg);
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    send(q, "text");
                }
            });
            chips.addView(b, ui.margins(-2, -2, 3, 0, 3, 0));
        }
        HorizontalScrollView hs = new HorizontalScrollView(a);
        hs.setHorizontalScrollBarEnabled(false);
        hs.addView(chips);
        col.addView(hs);

        // ---- input ----
        LinearLayout in = ui.row();
        in.setPadding(ui.dp(8), ui.dp(4), ui.dp(8), ui.dp(8));
        input = ui.input(Data.g(a, "اكتب رسالة حب...", "اكتبي رسالة حب..."));
        input.setMaxLines(4);
        input.setBackground(ui.rounded(Color.WHITE, 22));
        input.setPadding(ui.dp(16), ui.dp(10), ui.dp(16), ui.dp(10));
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE
                | InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        input.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int st, int c, int af) {
            }

            public void onTextChanged(CharSequence s, int st, int b, int c) {
                long now = System.currentTimeMillis();
                if (s.length() > 0 && now - lastTyping > 3000) {
                    lastTyping = now;
                    Cloud.patchAsync(a, base() + "/profiles/" + Cloud.uid(a), Data.obj("typing", now));
                }
            }

            public void afterTextChanged(Editable s) {
            }
        });
        in.addView(input, ui.weight(1));
        TextView sendBtn = ui.text("➤", 22, Color.WHITE, true);
        sendBtn.setGravity(Gravity.CENTER);
        GradientDrawable sb = new GradientDrawable();
        sb.setShape(GradientDrawable.OVAL);
        sb.setColor(Ui.PINK);
        sendBtn.setBackground(sb);
        sendBtn.setScaleX(-1f); // point left for right-to-left
        sendBtn.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                String t = input.getText().toString().trim();
                if (t.isEmpty()) return;
                input.setText("");
                send(t, "text");
            }
        });
        in.addView(sendBtn, ui.margins(ui.dp(46), ui.dp(46), 8, 0, 0, 0));
        col.addView(in);

        renderMessages();
        updateHeader();
        return col;
    }

    private View inviteView() {
        LinearLayout c = ui.card(true);
        c.setGravity(Gravity.CENTER_HORIZONTAL);
        LinearLayout.LayoutParams lp = (LinearLayout.LayoutParams) c.getLayoutParams();
        lp.setMargins(ui.dp(12), ui.dp(10), ui.dp(12), ui.dp(4));
        TextView t = ui.text(Data.g(a, "⏳ بانتظار انضمام بشرى 💞", "⏳ بانتظار انضمام زوجك 💞"), 16, Ui.PINK_DARK, true);
        t.setGravity(Gravity.CENTER);
        c.addView(t);
        final String code = Data.p(a).getString("my_invite_code", "");
        TextView info = ui.text(code.isEmpty()
                ? Data.g(a, "أرسل لها دعوة على واتساب لتنضم إليك", "أرسلي له دعوة على واتساب لينضم إليكِ")
                : "رمز الربط: " + code, 14, Ui.PINK_GRAY, false);
        info.setGravity(Gravity.CENTER);
        c.addView(info);
        Button send = ui.pinkButton(Data.g(a, "💌 أرسل الدعوة", "💌 أرسلي الدعوة"));
        send.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                final String saved = Data.p(a).getString("my_invite", "");
                if (!saved.isEmpty()) {
                    Data.share(a, saved);
                    return;
                }
                newInvite();
            }
        });
        c.addView(send, ui.margins(-2, -2, 0, 10, 0, 0));
        if (!code.isEmpty()) {
            Button renew = ui.button("🔄 دعوة جديدة", Color.TRANSPARENT, Ui.PINK_GRAY);
            renew.setTextSize(12);
            renew.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    newInvite();
                }
            });
            c.addView(renew);
        }
        return c;
    }

    private void newInvite() {
        final ProgressDialog pd = ProgressDialog.show(a, null, "⏳ جاري إنشاء الدعوة...", true, false);
        Cloud.async(a, new Cloud.Job() {
            @Override
            public Object run() throws Exception {
                return Cloud.createInvite(a);
            }
        }, new Cloud.Done() {
            @Override
            public void ok(Object r) {
                dismiss(pd);
                Data.share(a, (String) r);
                if (active) render();
            }

            @Override
            public void fail(String m) {
                dismiss(pd);
                ui.toast(m);
            }
        });
    }

    private void startStreams() {
        msgStream = new Cloud.Stream(a, base() + "/messages", "orderBy=%22%24key%22&limitToLast=150",
                new Cloud.StreamListener() {
                    @Override
                    public void onEvent(final String event, final String path, final Object data) {
                        Cloud.main().post(new Runnable() {
                            @Override
                            public void run() {
                                if (!active) return;
                                msgs = Cloud.apply(msgs, event, path, data);
                                renderMessages();
                            }
                        });
                    }
                }).start();
        profStream = new Cloud.Stream(a, base() + "/profiles", null, new Cloud.StreamListener() {
            @Override
            public void onEvent(final String event, final String path, final Object data) {
                Cloud.main().post(new Runnable() {
                    @Override
                    public void run() {
                        if (!active) return;
                        profiles = Cloud.apply(profiles, event, path, data);
                        updateHeader();
                    }
                });
            }
        }).start();
    }

    private void presence(boolean online) {
        lastPresence = System.currentTimeMillis();
        Cloud.patchAsync(a, base() + "/profiles/" + Cloud.uid(a), Data.obj("online", online,
                "lastSeen", System.currentTimeMillis(), "name", Cloud.myName(a), "role", Data.role(a)));
    }

    private JSONObject partnerProfile() {
        Iterator<String> it = profiles.keys();
        while (it.hasNext()) {
            String k = it.next();
            if (!k.equals(Cloud.uid(a))) {
                JSONObject p = profiles.optJSONObject(k);
                if (p != null) {
                    if (!k.equals(Cloud.partnerUid(a)) || !p.optString("name").equals(Cloud.partnerName(a))) {
                        Cloud.setPartner(a, k, p.optString("name"), p.optString("role"));
                    }
                    return p;
                }
            }
        }
        return null;
    }

    private void updateHeader() {
        if (nameView == null) return;
        JSONObject pp = partnerProfile();
        if (pp == null) {
            nameView.setText(Data.g(a, "بشرى 💕", "زوجي 💕"));
            statusView.setText("لم تنضم بعد");
            moodLine.setText("");
            inviteBox.setVisibility(Cloud.partnerUid(a).isEmpty() ? View.VISIBLE : View.GONE);
            return;
        }
        inviteBox.setVisibility(View.GONE);
        boolean fem = "wife".equals(pp.optString("role"));
        avatar.setText(fem ? "👰" : "🤵");
        nameView.setText(pp.optString("name", Cloud.partnerName(a)) + " 💕");
        long now = System.currentTimeMillis();
        String st;
        if (now - pp.optLong("typing") < 6000) st = fem ? "تكتب الآن... ✍️" : "يكتب الآن... ✍️";
        else if (pp.optBoolean("online") && now - pp.optLong("lastSeen") < 150000) st = fem ? "متصلة الآن 🟢" : "متصل الآن 🟢";
        else if (pp.optLong("lastSeen") > 0) st = "آخر ظهور " + Store.whenText(pp.optLong("lastSeen"));
        else st = "";
        statusView.setText(st);
        String mood = pp.optString("mood", "");
        moodLine.setText(mood.isEmpty() ? "" : (fem ? "مزاجها: " : "مزاجه: ") + mood + " " + pp.optString("moodText", ""));
    }

    private void pickMood() {
        final boolean wife = Data.isWife(a);
        String[] labels = new String[MOODS.length];
        for (int i = 0; i < MOODS.length; i++) labels[i] = MOODS[i][0] + "  " + MOODS[i][wife ? 2 : 1];
        new AlertDialog.Builder(a)
                .setTitle(wife ? "🎭 كيف مزاجكِ الآن؟" : "🎭 كيف مزاجك الآن؟")
                .setItems(labels, new DialogInterface.OnClickListener() {
                    @Override
                    public void onClick(DialogInterface d, int i) {
                        String e = MOODS[i][0];
                        String label = MOODS[i][wife ? 2 : 1];
                        Cloud.patchAsync(a, base() + "/profiles/" + Cloud.uid(a),
                                Data.obj("mood", e, "moodText", label, "moodAt", System.currentTimeMillis()));
                        Cloud.notifyPartner(a, "mood", "🎭 " + Cloud.myName(a), "مزاجي الآن: " + e + " " + label);
                        ui.toast("تم إرسال مزاجك " + e);
                    }
                }).show();
    }

    // ---------------- messages ----------------

    private void send(final String text, final String type) {
        final String tmp = "~" + System.nanoTime();
        sending.put(tmp, Data.obj("from", Cloud.uid(a), "text", text, "type", type, "t", System.currentTimeMillis()));
        renderMessages();
        final JSONObject body = Data.obj("from", Cloud.uid(a), "text", text, "type", type,
                "t", Cloud.serverTime(), "read", false);
        final boolean miss = "miss".equals(type);
        Cloud.async(a, new Cloud.Job() {
            @Override
            public Object run() throws Exception {
                Cloud.post(a, base() + "/messages", body);
                try {
                    if (miss) Cloud.sendInbox(a, "miss", "💗 " + Cloud.myName(a),
                            Data.g(a, "مشتاق لكِ كثيراً 🥺", "مشتاقة لك كثيراً 🥺"));
                    else Cloud.sendInbox(a, "msg", "💬 " + Cloud.myName(a), text);
                } catch (Exception ignored) {
                }
                return null;
            }
        }, new Cloud.Done() {
            @Override
            public void ok(Object r) {
                sending.remove(tmp);
                if (active) renderMessages();
            }

            @Override
            public void fail(String m) {
                sending.remove(tmp);
                if (!active) return;
                renderMessages();
                if (!miss && input != null && input.getText().length() == 0) input.setText(text);
                ui.toast("لم تُرسل 😢 " + m);
            }
        });
    }

    private void renderMessages() {
        if (list == null) return;
        list.removeAllViews();
        List<String> keys = new ArrayList<String>();
        Iterator<String> it = msgs.keys();
        while (it.hasNext()) keys.add(it.next());
        Collections.sort(keys);
        String uid = Cloud.uid(a);
        String lastDay = "";
        JSONObject toRead = new JSONObject();
        List<Object[]> all = new ArrayList<Object[]>();
        for (String k : keys) {
            JSONObject m = msgs.optJSONObject(k);
            if (m != null) all.add(new Object[]{k, m, false});
        }
        for (Map.Entry<String, JSONObject> e : sending.entrySet()) all.add(new Object[]{e.getKey(), e.getValue(), true});

        if (all.isEmpty()) {
            TextView empty = ui.text(Data.g(a, "ابدأ أول رسالة حب 💌", "ابدئي أول رسالة حب 💌"), 15, Ui.PINK_GRAY, false);
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(0, ui.dp(40), 0, 0);
            list.addView(empty, new LinearLayout.LayoutParams(-1, -2));
        }
        for (Object[] row : all) {
            String k = (String) row[0];
            JSONObject m = (JSONObject) row[1];
            boolean pending = (Boolean) row[2];
            long t = m.optLong("t", System.currentTimeMillis());
            String day = dayText(t);
            if (!day.equals(lastDay)) {
                lastDay = day;
                TextView sep = ui.text(day, 11, Ui.PINK_GRAY, true);
                sep.setBackground(ui.rounded(Ui.PINK_SOFT, 10));
                sep.setPadding(ui.dp(10), ui.dp(3), ui.dp(10), ui.dp(3));
                LinearLayout.LayoutParams lp = ui.margins(-2, -2, 0, 8, 0, 6);
                lp.gravity = Gravity.CENTER_HORIZONTAL;
                list.addView(sep, lp);
            }
            list.addView(bubble(k, m, pending, uid));
            if (!pending && !uid.equals(m.optString("from")) && !m.optBoolean("read") && !markedRead.contains(k)) {
                Data.put(toRead, k + "/read", true);
                markedRead.add(k);
            }
        }
        scroll.post(new Runnable() {
            @Override
            public void run() {
                scroll.fullScroll(View.FOCUS_DOWN);
            }
        });
        if (toRead.length() > 0 && active) Cloud.patchAsync(a, base() + "/messages", toRead);
    }

    private static String dayText(long t) {
        Calendar now = Calendar.getInstance();
        Calendar c = Calendar.getInstance();
        c.setTimeInMillis(t);
        if (now.get(Calendar.YEAR) == c.get(Calendar.YEAR) && now.get(Calendar.DAY_OF_YEAR) == c.get(Calendar.DAY_OF_YEAR))
            return "اليوم";
        now.add(Calendar.DAY_OF_YEAR, -1);
        if (now.get(Calendar.YEAR) == c.get(Calendar.YEAR) && now.get(Calendar.DAY_OF_YEAR) == c.get(Calendar.DAY_OF_YEAR))
            return "أمس";
        return new SimpleDateFormat("dd/MM/yyyy", Locale.US).format(new Date(t));
    }

    private View bubble(final String key, final JSONObject m, boolean pending, String uid) {
        final boolean mine = uid.equals(m.optString("from"));
        boolean miss = "miss".equals(m.optString("type"));
        LinearLayout wrap = new LinearLayout(a);
        wrap.setGravity(mine ? Gravity.END : Gravity.START);
        wrap.setPadding(0, ui.dp(2), 0, ui.dp(2));

        LinearLayout b = ui.column();
        b.setPadding(ui.dp(12), ui.dp(7), ui.dp(12), ui.dp(5));
        float r = ui.dp(18), s = ui.dp(4);
        GradientDrawable bg;
        if (miss) {
            bg = new GradientDrawable(GradientDrawable.Orientation.TL_BR, new int[]{Ui.PINK, 0xFFFF4081});
        } else {
            bg = new GradientDrawable();
            bg.setColor(mine ? Ui.PINK : Color.WHITE);
            if (!mine) bg.setStroke(ui.dp(1), Ui.PINK_LINE);
        }
        // corners: TL, TR, BR, BL — a small "tail" corner at the bottom on the sender's side
        bg.setCornerRadii(mine ? new float[]{r, r, r, r, r, r, s, s} : new float[]{r, r, r, r, s, s, r, r});
        b.setBackground(bg);
        b.setElevation(ui.dp(1));

        TextView tv = ui.text(m.optString("text"), miss ? 20 : 16, mine || miss ? Color.WHITE : 0xFF3A2A30, miss);
        tv.setMaxWidth((int) (a.getResources().getDisplayMetrics().widthPixels * 0.72));
        tv.setTextIsSelectable(false);
        b.addView(tv);

        String time = new SimpleDateFormat("HH:mm", Locale.US).format(new Date(m.optLong("t", System.currentTimeMillis())));
        if (mine) time += pending ? "  🕓" : m.optBoolean("read") ? "  ✓✓" : "  ✓";
        TextView meta = ui.text(time, 10, mine || miss ? 0xFFFFE4EF : Ui.PINK_GRAY, mine && m.optBoolean("read"));
        meta.setGravity(Gravity.END);
        b.addView(meta, new LinearLayout.LayoutParams(-1, -2));
        wrap.addView(b);

        if (!pending) {
            b.setOnLongClickListener(new View.OnLongClickListener() {
                @Override
                public boolean onLongClick(View v) {
                    String[] opts = mine ? new String[]{"📋 نسخ", "🗑️ حذف للجميع"} : new String[]{"📋 نسخ"};
                    new AlertDialog.Builder(a).setItems(opts, new DialogInterface.OnClickListener() {
                        @Override
                        public void onClick(DialogInterface d, int i) {
                            if (i == 0) {
                                ClipboardManager cm = (ClipboardManager) a.getSystemService(Context.CLIPBOARD_SERVICE);
                                cm.setPrimaryClip(ClipData.newPlainText("bouchra", m.optString("text")));
                                ui.toast("تم النسخ");
                            } else {
                                final Context c = a.getApplicationContext();
                                Cloud.EX.execute(new Runnable() {
                                    @Override
                                    public void run() {
                                        try {
                                            Cloud.delete(c, base() + "/messages/" + key);
                                        } catch (Exception ignored) {
                                        }
                                    }
                                });
                            }
                        }
                    }).show();
                    return true;
                }
            });
        }
        return wrap;
    }
}
