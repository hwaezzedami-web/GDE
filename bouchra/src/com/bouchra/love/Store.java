package com.bouchra.love;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** Keeps the reminders and settings in SharedPreferences. */
public class Store {

    public static class Reminder {
        public int id;
        public String emoji;
        public String title;
        public String message;
        public int interval;      // minutes
        public boolean enabled = true;
        public long next;         // epoch ms of next reminder
        public int today;         // times done today
        public String todayDate = "";
        public int total;         // times done ever
    }

    private static final String PREFS = "bouchra";
    private static final String KEY = "reminders";

    // emoji, title, notification message, interval (minutes)
    private static final Object[][] DEFAULTS = {
        {"💋", "قبّلها", "حان وقت قبلة لبشرى 💋 لا تنسَ!", 120},
        {"🤗", "احضنها", "حضن دافئ لبشرى الآن 🤗", 180},
        {"❤️", "قل لها: أحبك", "قل لبشرى «أحبك» من قلبك ❤️", 240},
        {"🤲", "امسك يدها", "امسك يد بشرى بحنان 🤲", 180},
        {"👀", "انظر في عينيها وابتسم", "انظر في عيني بشرى وابتسم لها 😍", 240},
        {"🌹", "امدح جمالها", "قل لبشرى كم هي جميلة اليوم 🌹", 300},
        {"📱", "أرسل لها رسالة حب", "أرسل رسالة حب لبشرى الآن 💌", 180},
        {"📞", "اتصل بها واسأل عنها", "اتصل ببشرى واسأل عن حالها 📞", 360},
        {"😊", "أضحكها", "أضحك بشرى بنكتة أو موقف لطيف 😂", 240},
        {"🙌", "اشكرها على تعبها", "اشكر بشرى على كل ما تفعله 🙏", 480},
        {"👂", "استمع لها باهتمام", "اجلس مع بشرى واستمع لها باهتمام 👂", 480},
        {"🤲", "ادعُ لها", "ادعُ لبشرى بالخير والسعادة 🤲", 360},
        {"💧", "ذكّرها تشرب ماء", "ذكّر بشرى تشرب كوب ماء 💧", 120},
        {"☀️", "صباح الخير يا حبيبتي", "قل لبشرى: صباح الخير يا أجمل ما في حياتي ☀️", 1440},
        {"🌙", "تصبحين على خير", "قل لبشرى: تصبحين على خير يا قمري 🌙", 1440},
        {"☕", "حضّر لها قهوة أو شاي", "حضّر لبشرى مشروبها المفضل ☕", 1440},
        {"🧹", "ساعدها في البيت", "ساعد بشرى في أعمال البيت اليوم 🧹", 1440},
        {"💆‍♀️", "دلّكها (مساج)", "مساج لطيف لبشرى لتريح تعبها 💆‍♀️", 1440},
        {"🍫", "فاجئها بشوكولاتة", "فاجئ بشرى بشوكولاتة أو حلوى 🍫", 4320},
        {"📸", "التقط صورة معها", "التقط صورة جميلة مع بشرى 📸", 4320},
        {"💐", "اشترِ لها ورداً", "اشترِ باقة ورد لبشرى 💐", 10080},
        {"🎁", "هدية صغيرة", "فاجئ بشرى بهدية صغيرة 🎁", 10080},
        {"🚶‍♀️", "نزهة معها", "خذ بشرى في نزهة جميلة 🚶‍♀️", 10080},
        {"🎬", "سهرة فيلم معاً", "سهرة فيلم مع بشرى الليلة 🍿", 10080},
        {"🕯️", "عشاء رومانسي", "حضّر عشاءً رومانسياً لبشرى 🕯️", 10080},
        {"💌", "اكتب لها رسالة بخط يدك", "اكتب لبشرى رسالة حب بخط يدك 💌", 10080},
    };

    // Bouchra's own reminders (about her husband)
    private static final Object[][] DEFAULTS_WIFE = {
        {"💋", "قبّليه", "حان وقت قبلة لزوجك 💋", 120},
        {"🤗", "احضنيه", "حضن دافئ لزوجك الآن 🤗", 180},
        {"❤️", "قولي له: أحبك", "قولي لزوجك «أحبك» من قلبك ❤️", 240},
        {"😊", "ابتسمي له", "ابتسامتك تسعده، ابتسمي له 😊", 180},
        {"👀", "انظري في عينيه", "انظري في عيني زوجك وابتسمي 😍", 240},
        {"🌹", "امدحيه", "قولي لزوجك كلمة جميلة عنه 🌹", 300},
        {"📱", "أرسلي له رسالة حب", "أرسلي رسالة حب لزوجك الآن 💌", 180},
        {"📞", "اتصلي واسألي عنه", "اتصلي بزوجك واسألي عن يومه 📞", 360},
        {"😂", "أضحكيه", "أضحكي زوجك بموقف لطيف 😂", 240},
        {"🙌", "اشكريه على تعبه", "اشكري زوجك على تعبه من أجلكم 🙏", 480},
        {"👂", "استمعي ليومه", "اسأليه عن يومه واستمعي له 👂", 480},
        {"🤲", "ادعي له", "ادعي لزوجك بالخير والتوفيق 🤲", 360},
        {"💧", "ذكّريه يشرب ماء", "ذكّري زوجك يشرب كوب ماء 💧", 120},
        {"☀️", "صباح الخير يا حبيبي", "قولي لزوجك: صباح الخير يا أغلى الناس ☀️", 1440},
        {"🌙", "تصبح على خير", "قولي لزوجك: تصبح على خير يا عمري 🌙", 1440},
        {"☕", "حضّري له قهوته", "حضّري لزوجك مشروبه المفضل ☕", 1440},
        {"🍰", "حلوى يحبها", "فاجئي زوجك بحلوى يحبها 🍰", 4320},
        {"📸", "صورة معه", "التقطي صورة جميلة معه 📸", 4320},
        {"🎁", "مفاجأة صغيرة", "فاجئي زوجك بهدية صغيرة 🎁", 10080},
        {"🎬", "سهرة معاً", "اقترحي سهرة فيلم معاً 🍿", 10080},
        {"💌", "رسالة بخط يدك", "اكتبي لزوجك رسالة حب بخط يدك 💌", 10080},
    };

    private static SharedPreferences prefs(Context c) {
        return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static String todayKey() {
        return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(new Date());
    }

    public static List<Reminder> load(Context c) {
        List<Reminder> list = new ArrayList<Reminder>();
        String raw = prefs(c).getString(KEY, null);
        if (raw == null) {
            long now = System.currentTimeMillis();
            Object[][] DEFAULTS = Data.isWife(c) ? DEFAULTS_WIFE : Store.DEFAULTS;
            for (int i = 0; i < DEFAULTS.length; i++) {
                Reminder r = new Reminder();
                r.id = i + 1;
                r.emoji = (String) DEFAULTS[i][0];
                r.title = (String) DEFAULTS[i][1];
                r.message = (String) DEFAULTS[i][2];
                r.interval = (Integer) DEFAULTS[i][3];
                r.next = adjustForQuiet(c, now + r.interval * 60000L);
                list.add(r);
            }
            save(c, list);
            return list;
        }
        try {
            JSONArray arr = new JSONArray(raw);
            String today = todayKey();
            for (int i = 0; i < arr.length(); i++) {
                JSONObject o = arr.getJSONObject(i);
                Reminder r = new Reminder();
                r.id = o.getInt("id");
                r.emoji = o.optString("emoji", "💗");
                r.title = o.getString("title");
                r.message = o.optString("message", r.title);
                r.interval = o.getInt("interval");
                r.enabled = o.optBoolean("enabled", true);
                r.next = o.optLong("next", 0);
                r.todayDate = o.optString("todayDate", "");
                r.today = today.equals(r.todayDate) ? o.optInt("today", 0) : 0;
                r.total = o.optInt("total", 0);
                list.add(r);
            }
        } catch (Exception e) {
            // corrupted data: start over with defaults
            prefs(c).edit().remove(KEY).commit();
            return load(c);
        }
        return list;
    }

    public static void save(Context c, List<Reminder> list) {
        JSONArray arr = new JSONArray();
        try {
            for (Reminder r : list) {
                JSONObject o = new JSONObject();
                o.put("id", r.id);
                o.put("emoji", r.emoji);
                o.put("title", r.title);
                o.put("message", r.message);
                o.put("interval", r.interval);
                o.put("enabled", r.enabled);
                o.put("next", r.next);
                o.put("today", r.today);
                o.put("todayDate", r.todayDate);
                o.put("total", r.total);
                arr.put(o);
            }
        } catch (Exception ignored) {
        }
        prefs(c).edit().putString(KEY, arr.toString()).commit();
    }

    public static Reminder find(List<Reminder> list, int id) {
        for (Reminder r : list) if (r.id == id) return r;
        return null;
    }

    public static int nextId(List<Reminder> list) {
        int max = 0;
        for (Reminder r : list) max = Math.max(max, r.id);
        return max + 1;
    }

    /** Records a "done" and returns the updated reminder. */
    public static void markDone(Context c, Reminder r) {
        String today = todayKey();
        if (!today.equals(r.todayDate)) {
            r.todayDate = today;
            r.today = 0;
        }
        r.today++;
        r.total++;
        r.next = adjustForQuiet(c, System.currentTimeMillis() + r.interval * 60000L);
    }

    /** Lets the partner know a reminder was done (setting "tell_partner", on by default). */
    public static void tellPartner(Context c, Reminder r) {
        if (!prefs(c).getBoolean("tell_partner", true)) return;
        Cloud.notifyPartner(c, "done", r.emoji + " " + Cloud.myName(c),
                Data.g(c, "أنجز من أجلك: ", "أنجزت من أجلك: ") + r.title + " 💕");
    }

    // ---- quiet (sleep) hours ----

    public static boolean quietEnabled(Context c) {
        return prefs(c).getBoolean("quiet", true);
    }

    public static void setQuiet(Context c, boolean on) {
        prefs(c).edit().putBoolean("quiet", on).commit();
    }

    public static final int QUIET_START = 23; // 11 PM
    public static final int QUIET_END = 8;    // 8 AM

    /** Moves a time that falls inside sleep hours to the morning. */
    public static long adjustForQuiet(Context c, long t) {
        if (!quietEnabled(c)) return t;
        Calendar cal = Calendar.getInstance();
        cal.setTimeInMillis(t);
        int h = cal.get(Calendar.HOUR_OF_DAY);
        if (h >= QUIET_START || h < QUIET_END) {
            if (h >= QUIET_START) cal.add(Calendar.DAY_OF_YEAR, 1);
            cal.set(Calendar.HOUR_OF_DAY, QUIET_END);
            cal.set(Calendar.MINUTE, 0);
            cal.set(Calendar.SECOND, 0);
            cal.set(Calendar.MILLISECOND, 0);
            return cal.getTimeInMillis();
        }
        return t;
    }

    // ---- text helpers ----

    public static final int[] INTERVALS = {30, 60, 120, 180, 240, 300, 360, 480, 720, 1440, 2880, 4320, 10080};

    public static String intervalText(int m) {
        if (m < 60) return "كل " + m + " دقيقة";
        if (m == 60) return "كل ساعة";
        if (m == 120) return "كل ساعتين";
        if (m < 1440 && m % 60 == 0) {
            int h = m / 60;
            return h <= 10 ? "كل " + h + " ساعات" : "كل " + h + " ساعة";
        }
        if (m < 1440) return "كل " + m + " دقيقة";
        if (m == 1440) return "يومياً";
        if (m == 2880) return "كل يومين";
        if (m == 10080) return "أسبوعياً";
        if (m % 1440 == 0) return "كل " + (m / 1440) + " أيام";
        return "كل " + m + " دقيقة";
    }

    public static String whenText(long t) {
        Calendar now = Calendar.getInstance();
        Calendar c = Calendar.getInstance();
        c.setTimeInMillis(t);
        String time = new SimpleDateFormat("HH:mm", Locale.US).format(new Date(t));
        if (now.get(Calendar.YEAR) == c.get(Calendar.YEAR)
                && now.get(Calendar.DAY_OF_YEAR) == c.get(Calendar.DAY_OF_YEAR)) {
            return "اليوم " + time;
        }
        now.add(Calendar.DAY_OF_YEAR, 1);
        if (now.get(Calendar.YEAR) == c.get(Calendar.YEAR)
                && now.get(Calendar.DAY_OF_YEAR) == c.get(Calendar.DAY_OF_YEAR)) {
            return "غداً " + time;
        }
        return new SimpleDateFormat("dd/MM", Locale.US).format(new Date(t)) + " " + time;
    }
}
