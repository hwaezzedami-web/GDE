package com.bouchra.love;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

/** Small helpers for building the pink UI in code. */
public class Ui {
    public static final int PINK = 0xFFE91E63;
    public static final int PINK_LIGHT = 0xFFFF80AB;
    public static final int PINK_SOFT = 0xFFFCE4EC;
    public static final int PINK_BG = 0xFFFFF0F6;
    public static final int PINK_DARK = 0xFFAD1457;
    public static final int PINK_GRAY = 0xFF9C6B80;
    public static final int PINK_LINE = 0xFFF8BBD0;
    public static final int MUTED_BG = 0xFFF5EEF1;
    public static final int MUTED_LINE = 0xFFE0D0D6;

    public final Activity a;

    public Ui(Activity a) {
        this.a = a;
    }

    public int dp(float v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, a.getResources().getDisplayMetrics());
    }

    public GradientDrawable rounded(int color, float radiusDp) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(dp(radiusDp));
        return g;
    }

    public TextView text(String s, float size, int color, boolean bold) {
        TextView t = new TextView(a);
        t.setText(s);
        t.setTextSize(size);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    public Button button(String s, int bg, int fg) {
        Button b = new Button(a);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextColor(fg);
        b.setTextSize(14);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        b.setBackground(rounded(bg, 22));
        b.setMinWidth(0);
        b.setMinimumWidth(0);
        b.setMinHeight(0);
        b.setMinimumHeight(0);
        b.setPadding(dp(16), dp(8), dp(16), dp(8));
        return b;
    }

    public Button pinkButton(String s) {
        return button(s, PINK, Color.WHITE);
    }

    public Button softButton(String s) {
        return button(s, PINK_SOFT, PINK_DARK);
    }

    /** White rounded card (vertical). */
    public LinearLayout card(boolean active) {
        LinearLayout c = new LinearLayout(a);
        c.setOrientation(LinearLayout.VERTICAL);
        c.setPadding(dp(14), dp(12), dp(14), dp(12));
        GradientDrawable bg = rounded(active ? Color.WHITE : MUTED_BG, 18);
        bg.setStroke(dp(1), active ? PINK_LINE : MUTED_LINE);
        c.setBackground(bg);
        c.setElevation(dp(2));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.setMargins(dp(2), dp(6), dp(2), dp(6));
        c.setLayoutParams(lp);
        return c;
    }

    public LinearLayout row() {
        LinearLayout r = new LinearLayout(a);
        r.setOrientation(LinearLayout.HORIZONTAL);
        r.setGravity(Gravity.CENTER_VERTICAL);
        return r;
    }

    public LinearLayout column() {
        LinearLayout r = new LinearLayout(a);
        r.setOrientation(LinearLayout.VERTICAL);
        return r;
    }

    public TextView section(String s) {
        TextView t = text(s, 17, PINK_DARK, true);
        t.setPadding(dp(6), dp(14), dp(6), dp(4));
        return t;
    }

    public TextView emojiBubble(String e, int sizeDp) {
        TextView t = new TextView(a);
        t.setText(e);
        t.setTextSize(sizeDp * 0.45f);
        t.setGravity(Gravity.CENTER);
        GradientDrawable g = new GradientDrawable();
        g.setShape(GradientDrawable.OVAL);
        g.setColor(PINK_SOFT);
        t.setBackground(g);
        t.setLayoutParams(new LinearLayout.LayoutParams(dp(sizeDp), dp(sizeDp)));
        return t;
    }

    public LinearLayout.LayoutParams margins(int w, int h, int l, int t, int r, int b) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(w, h);
        lp.setMargins(dp(l), dp(t), dp(r), dp(b));
        return lp;
    }

    public LinearLayout.LayoutParams weight(float w) {
        return new LinearLayout.LayoutParams(0, -2, w);
    }

    /** Pink progress bar, fraction 0..1. */
    public View progress(float fraction) {
        fraction = Math.max(0f, Math.min(1f, fraction));
        LinearLayout bar = new LinearLayout(a);
        bar.setOrientation(LinearLayout.HORIZONTAL);
        bar.setBackground(rounded(PINK_SOFT, 6));
        View fill = new View(a);
        GradientDrawable g = new GradientDrawable(GradientDrawable.Orientation.RIGHT_LEFT,
                new int[]{PINK_LIGHT, PINK});
        g.setCornerRadius(dp(6));
        fill.setBackground(g);
        bar.addView(fill, new LinearLayout.LayoutParams(0, -1, fraction));
        View rest = new View(a);
        bar.addView(rest, new LinearLayout.LayoutParams(0, -1, 1f - fraction));
        bar.setLayoutParams(margins(-1, dp(12) / 1, 0, 8, 0, 4));
        bar.getLayoutParams().height = dp(12);
        return bar;
    }

    public EditText input(String hint) {
        EditText e = new EditText(a);
        e.setHint(hint);
        e.setTextSize(15);
        e.setTextColor(PINK_DARK);
        e.setHintTextColor(0xFFC9A3B4);
        return e;
    }

    /** Vertical box used inside dialogs. */
    public LinearLayout dialogBox() {
        LinearLayout box = column();
        box.setPadding(dp(20), dp(8), dp(20), 0);
        box.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        return box;
    }

    /** Scrollable page; optional floating button at the bottom. */
    public FrameLayout page(LinearLayout body, View fab) {
        FrameLayout f = new FrameLayout(a);
        ScrollView s = new ScrollView(a);
        body.setPadding(dp(12), dp(8), dp(12), dp(fab != null ? 96 : 24));
        s.addView(body);
        f.addView(s, new FrameLayout.LayoutParams(-1, -1));
        if (fab != null) {
            fab.setElevation(dp(8));
            FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(-2, dp(52));
            lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL;
            lp.bottomMargin = dp(14);
            f.addView(fab, lp);
        }
        return f;
    }

    public Button fab(String s) {
        Button b = button(s, PINK, Color.WHITE);
        b.setTextSize(16);
        b.setBackground(rounded(PINK, 30));
        b.setPadding(dp(26), 0, dp(26), 0);
        return b;
    }

    public void toast(String s) {
        Toast.makeText(a, s, Toast.LENGTH_SHORT).show();
    }
}
