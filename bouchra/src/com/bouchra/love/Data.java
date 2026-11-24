package com.bouchra.love;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Random;

/** Shared storage helpers, Arabic text helpers and love phrases. */
public class Data {

    public static final String DREAMS = "dreams";
    public static final String SHOPPING = "shopping";
    public static final String COUPONS = "coupons";
    public static final String OCCASIONS = "occasions";
    public static final String SINCE = "since";             // wedding date (ms)
    public static final String DAILY_PHRASE = "daily_phrase"; // morning love message on/off

    public static SharedPreferences p(Context c) {
        return c.getSharedPreferences("bouchra", Context.MODE_PRIVATE);
    }

    public static boolean has(Context c, String key) {
        return p(c).contains(key);
    }

    public static JSONArray list(Context c, String key) {
        try {
            return new JSONArray(p(c).getString(key, "[]"));
        } catch (Exception e) {
            return new JSONArray();
        }
    }

    /** Saves a list; shared lists are also sent to the partner when linked. */
    public static void save(Context c, String key, JSONArray a) {
        if (Sync.isShared(key) && Cloud.linked(c)) Sync.localChange(c, key, list(c, key), a);
        saveLocal(c, key, a);
    }

    public static void saveLocal(Context c, String key, JSONArray a) {
        p(c).edit().putString(key, a.toString()).commit();
    }

    // ---------- who am I ----------

    public static String role(Context c) {
        return p(c).getString("role", "husband");
    }

    public static boolean hasRole(Context c) {
        return p(c).contains("role");
    }

    public static boolean isWife(Context c) {
        return "wife".equals(role(c));
    }

    /** Picks the husband's or the wife's wording. */
    public static String g(Context c, String husband, String wife) {
        return isWife(c) ? wife : husband;
    }

    public static List<JSONObject> items(JSONArray a) {
        List<JSONObject> out = new ArrayList<JSONObject>();
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null) out.add(o);
        }
        return out;
    }

    /**
     * New ids: milliseconds * 1000 + random, so they sort by creation time and two phones
     * adding at the same moment practically never pick the same id.
     */
    public static long nextId(JSONArray a) {
        long max = 0;
        for (JSONObject o : items(a)) max = Math.max(max, o.optLong("id"));
        long timeId = System.currentTimeMillis() * 1000L + new Random().nextInt(1000);
        return Math.max(max + 1, timeId);
    }

    public static JSONObject find(JSONArray a, long id) {
        for (JSONObject o : items(a)) if (o.optLong("id") == id) return o;
        return null;
    }

    public static void remove(JSONArray a, long id) {
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && o.optLong("id") == id) {
                a.remove(i);
                return;
            }
        }
    }

    public static JSONObject obj(Object... kv) {
        JSONObject o = new JSONObject();
        try {
            for (int i = 0; i + 1 < kv.length; i += 2) o.put((String) kv[i], kv[i + 1]);
        } catch (Exception ignored) {
        }
        return o;
    }

    public static void put(JSONObject o, String k, Object v) {
        try {
            o.put(k, v);
        } catch (Exception ignored) {
        }
    }

    // ---------- Arabic text ----------

    /** Arabic number + noun agreement: 1 سنة، 2 سنتان، 3-10 سنوات، 11+ سنة. */
    public static String plural(long n, String one, String two, String few, String many) {
        if (n == 1) return one;
        if (n == 2) return two;
        if (n >= 3 && n <= 10) return n + " " + few;
        return n + " " + many;
    }

    public static String days(long n) {
        if (n == 0) return "0 يوم";
        return plural(n, "يوم واحد", "يومان", "أيام", "يوماً");
    }

    private static final String[] ORD = {"", "الأولى", "الثانية", "الثالثة", "الرابعة", "الخامسة",
            "السادسة", "السابعة", "الثامنة", "التاسعة", "العاشرة"};

    public static String ordinal(int n) {
        return n >= 1 && n < ORD.length ? ORD[n] : "رقم " + n;
    }

    public static String date(long t) {
        return new SimpleDateFormat("dd/MM/yyyy", Locale.US).format(new Date(t));
    }

    public static String money(long v) {
        return String.format(Locale.US, "%,d", v);
    }

    public static Calendar today() {
        Calendar c = Calendar.getInstance();
        c.set(Calendar.HOUR_OF_DAY, 0);
        c.set(Calendar.MINUTE, 0);
        c.set(Calendar.SECOND, 0);
        c.set(Calendar.MILLISECOND, 0);
        return c;
    }

    /** Days until the next yearly occurrence of month (0-based) / day; 0 = today. */
    public static int daysUntil(int month, int day) {
        Calendar t = today();
        Calendar n = today();
        n.set(Calendar.MONTH, month);
        n.set(Calendar.DAY_OF_MONTH, Math.min(day, n.getActualMaximum(Calendar.DAY_OF_MONTH)));
        if (n.before(t)) {
            n.add(Calendar.YEAR, 1);
            n.set(Calendar.MONTH, month);
            n.set(Calendar.DAY_OF_MONTH, Math.min(day, n.getActualMaximum(Calendar.DAY_OF_MONTH)));
        }
        return (int) Math.round((n.getTimeInMillis() - t.getTimeInMillis()) / 86400000.0);
    }

    /** How many years the next occurrence will mark, counting from the given year. */
    public static int nextYearCount(int year, int month, int day) {
        Calendar t = today();
        int count = t.get(Calendar.YEAR) - year;
        if (daysUntil(month, day) > 0) {
            Calendar n = today();
            n.add(Calendar.DAY_OF_YEAR, daysUntil(month, day));
            count = n.get(Calendar.YEAR) - year;
        }
        return count;
    }

    // ---------- love phrases (love jar + daily message) ----------

    public static final String[] PHRASES = {
            "أنتِ أجمل صدفة في حياتي 💕",
            "كل يوم معكِ هو عيد ❤️",
            "ابتسامتكِ تضيء يومي ☀️",
            "أحبكِ أكثر مما تقوله الكلمات 💗",
            "أنتِ وطني وسكني وراحتي 🏡",
            "لو عاد بي الزمن لاخترتكِ من جديد 💍",
            "قلبي ينبض باسمكِ يا بشرى 💓",
            "أنتِ نصفي الأجمل 🌹",
            "معكِ عرفت معنى السعادة 😊",
            "شكراً لأنكِ في حياتي 🙏",
            "عيناكِ أجمل ما رأيت 😍",
            "أنتِ حلمي الذي تحقق ✨",
            "وجودكِ يكفيني عن العالم كله 🌍",
            "كل شيء أجمل عندما تكونين بجانبي 💞",
            "أنتِ ملكة قلبي 👑",
            "أشتاق إليكِ حتى وأنتِ بجانبي 🥰",
            "صوتكِ أجمل موسيقى 🎶",
            "أنتِ أغلى ما أملك 💎",
            "الله يحفظكِ لي ويديمكِ نعمة في حياتي 🤲",
            "حبكِ يكبر في قلبي كل يوم 🌱",
            "أنتِ السبب في ابتسامتي كل صباح 🌸",
            "معكِ أشعر أنني في بيتي 🏠",
            "يا أجمل زوجة في الدنيا 💐",
            "أنتِ قوتي عندما أضعف 💪",
            "ضحكتكِ تمحو كل تعبي 😄",
            "أنتِ رفيقة دربي وأحلامي 🛤️",
            "لا أتخيل حياتي بدونكِ 💘",
            "يا بشرى، أنتِ بشرى الخير في حياتي 🕊️",
            "أحب تفاصيلكِ الصغيرة كلها 🧸",
            "أنتِ نعمة أحمد الله عليها كل يوم 🤍",
            "قلبي ملككِ للأبد ♾️",
            "أجمل لحظاتي هي التي أقضيها معكِ ⏳",
            "أنتِ القمر في ليلي 🌙",
            "كل الطرق تؤدي إلى قلبكِ 💌",
            "معكِ الحياة حلوة مثل الشوكولاتة 🍫",
            "أنتِ أحلى قرار اتخذته في حياتي ✅",
            "يومي لا يكتمل إلا بكِ 🌼",
            "أحبكِ اليوم أكثر من الأمس وأقل من الغد 💗",
            "أنتِ سر سعادتي 🗝️",
            "سأبقى أحبكِ حتى آخر نفس 💞",
    };

    /** Phrases for Bouchra to say to her husband. */
    public static final String[] PHRASES_HIM = {
            "أنت أجمل صدفة في حياتي 💕",
            "كل يوم معك هو عيد ❤️",
            "ابتسامتك تضيء يومي ☀️",
            "أحبك أكثر مما تقوله الكلمات 💗",
            "أنت سندي وأماني 🏡",
            "لو عاد بي الزمن لاخترتك من جديد 💍",
            "قلبي ينبض باسمك 💓",
            "أنت نصفي الأجمل 🌹",
            "معك عرفت معنى السعادة 😊",
            "شكراً لأنك في حياتي 🙏",
            "أنت حلمي الذي تحقق ✨",
            "وجودك يكفيني عن العالم كله 🌍",
            "كل شيء أجمل عندما تكون بجانبي 💞",
            "أنت ملك قلبي 👑",
            "أشتاق إليك حتى وأنت بجانبي 🥰",
            "صوتك أجمل ما أسمع 🎶",
            "أنت أغلى ما أملك 💎",
            "الله يحفظك لي ويديمك نعمة في حياتي 🤲",
            "حبك يكبر في قلبي كل يوم 🌱",
            "معك أشعر بالأمان 🛡️",
            "أنت رفيق دربي وأحلامي 🛤️",
            "لا أتخيل حياتي بدونك 💘",
            "أحب تفاصيلك الصغيرة كلها 🧸",
            "أنت نعمة أحمد الله عليها كل يوم 🤍",
            "قلبي ملكك للأبد ♾️",
            "أجمل لحظاتي هي التي أقضيها معك ⏳",
            "تعبك من أجلنا لا يُنسى، شكراً يا حبيبي 💪",
            "أنت أحلى قرار في حياتي ✅",
            "أحبك اليوم أكثر من الأمس وأقل من الغد 💗",
            "سأبقى أحبك حتى آخر نفس 💞",
    };

    public static String[] phrases(Context c) {
        return isWife(c) ? PHRASES_HIM : PHRASES;
    }

    public static String phraseOfDay(Context ctx) {
        String[] ph = phrases(ctx);
        Calendar c = Calendar.getInstance();
        int idx = (c.get(Calendar.YEAR) * 366 + c.get(Calendar.DAY_OF_YEAR)) % ph.length;
        return ph[idx];
    }

    public static String randomPhrase(Context c) {
        String[] ph = phrases(c);
        return ph[new Random().nextInt(ph.length)];
    }

    /** Opens the share sheet (WhatsApp, SMS...) with the given text. */
    public static void share(Activity a, String text) {
        Intent i = new Intent(Intent.ACTION_SEND);
        i.setType("text/plain");
        i.putExtra(Intent.EXTRA_TEXT, text);
        a.startActivity(Intent.createChooser(i, "إرسال إلى بشرى 💌"));
    }
}
