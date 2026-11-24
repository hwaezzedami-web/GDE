package com.bouchra.love;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.security.SecureRandom;
import java.util.Iterator;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Talks to Firebase (Auth + Realtime Database) over plain REST, so the app
 * needs no Google libraries. Database layout:
 * users/{uid}            {name, role, couple, joinCode}
 * codes/{code}           {couple, owner, t}               invite codes
 * couples/{cid}/members  {uid: true}                       max 2
 * couples/{cid}/profiles/{uid} {name, role, online, lastSeen, typing, mood, moodText}
 * couples/{cid}/messages/{push} {from, text, type, t, read}
 * couples/{cid}/shared/{list}/{i<id>}  shopping, dreams, coupons, occasions; shared/since
 * couples/{cid}/inbox/{uid}/{push} {kind, title, text, t}   notifications for that person
 */
public class Cloud {

    /** Optional built-in config. Empty = entered inside the app (or pasted from an invite). */
    static final String BUILTIN_KEY = "";
    static final String BUILTIN_DB = "";

    public static final ExecutorService EX = Executors.newSingleThreadExecutor();
    private static Handler main;

    /** UI-thread handler (created lazily). */
    public static synchronized Handler main() {
        if (main == null) main = new Handler(Looper.getMainLooper());
        return main;
    }

    // Google endpoints (overridable for local testing against the Firebase emulator)
    static String AUTH_BASE = "https://identitytoolkit.googleapis.com/v1/accounts:";
    static String TOKEN_BASE = "https://securetoken.googleapis.com/v1/token";
    static String EXTRA_QUERY = "";

    static SharedPreferences p(Context c) {
        return Data.p(c);
    }

    // ---------------- state ----------------

    public static String apiKey(Context c) {
        String k = p(c).getString("fb_key", "");
        return k.isEmpty() ? BUILTIN_KEY : k;
    }

    public static String dbUrl(Context c) {
        String d = p(c).getString("fb_db", "");
        return d.isEmpty() ? BUILTIN_DB : d;
    }

    public static boolean configured(Context c) {
        return !apiKey(c).isEmpty() && !dbUrl(c).isEmpty();
    }

    public static String normalizeDb(String d) {
        d = d.trim();
        if (d.isEmpty()) return d;
        if (!d.startsWith("http")) d = "https://" + d;
        while (d.endsWith("/")) d = d.substring(0, d.length() - 1);
        return d;
    }

    public static void setConfig(Context c, String key, String db) {
        p(c).edit().putString("fb_key", key.trim()).putString("fb_db", normalizeDb(db)).commit();
    }

    public static String uid(Context c) {
        return p(c).getString("uid", "");
    }

    public static String myName(Context c) {
        return p(c).getString("my_name", "");
    }

    public static String email(Context c) {
        return p(c).getString("email", "");
    }

    public static String cid(Context c) {
        return p(c).getString("cid", "");
    }

    public static String partnerUid(Context c) {
        return p(c).getString("partner", "");
    }

    public static String partnerName(Context c) {
        String n = p(c).getString("partner_name", "");
        if (!n.isEmpty()) return n;
        return Data.isWife(c) ? "زوجي" : "بشرى";
    }

    public static boolean signedIn(Context c) {
        return !uid(c).isEmpty() && !p(c).getString("refresh", "").isEmpty();
    }

    public static boolean linked(Context c) {
        return configured(c) && signedIn(c) && !cid(c).isEmpty();
    }

    public static void setPartner(Context c, String uid, String name, String role) {
        SharedPreferences.Editor e = p(c).edit().putString("partner", uid);
        if (name != null && !name.isEmpty()) e.putString("partner_name", name);
        if (role != null && !role.isEmpty()) e.putString("partner_role", role);
        e.commit();
    }

    public static void signOut(Context c) {
        LoveService.stop(c);
        p(c).edit().remove("uid").remove("refresh").remove("token").remove("token_exp").remove("email")
                .remove("cid").remove("partner").remove("partner_name").remove("partner_role")
                .remove("my_invite").remove("pending_invite").remove("shared_cache").remove("pending").commit();
    }

    // ---------------- HTTP ----------------

    public static class HttpError extends IOException {
        public final int code;
        public final String body;

        HttpError(int code, String body) {
            super("HTTP " + code + ": " + body);
            this.code = code;
            this.body = body;
        }
    }

    /** An error whose message is already user-facing Arabic text. */
    public static class Msg extends IOException {
        public Msg(String m) {
            super(m);
        }
    }

    static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");
        } catch (Exception e) {
            return s;
        }
    }

    static String readAll(InputStream is) throws IOException {
        ByteArrayOutputStream bo = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) > 0) bo.write(buf, 0, n);
        is.close();
        return new String(bo.toByteArray(), "UTF-8");
    }

    static String http(String method, String url, String body, String type) throws IOException {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        try {
            con.setConnectTimeout(15000);
            con.setReadTimeout(25000);
            if ("PATCH".equals(method)) {
                con.setRequestMethod("POST");
                con.setRequestProperty("X-HTTP-Method-Override", "PATCH");
            } else {
                con.setRequestMethod(method);
            }
            if (body != null) {
                con.setDoOutput(true);
                con.setRequestProperty("Content-Type", type);
                OutputStream os = con.getOutputStream();
                os.write(body.getBytes("UTF-8"));
                os.close();
            }
            int code = con.getResponseCode();
            InputStream is = code >= 400 ? con.getErrorStream() : con.getInputStream();
            String resp = is == null ? "" : readAll(is);
            if (code >= 400) throw new HttpError(code, resp);
            return resp;
        } finally {
            con.disconnect();
        }
    }

    // ---------------- auth ----------------

    private static JSONObject authCall(Context c, String endpoint, JSONObject body) throws IOException {
        if (!configured(c)) throw new Msg("لم يتم إعداد الخادم بعد");
        try {
            return new JSONObject(http("POST", AUTH_BASE + endpoint
                    + "?key=" + enc(apiKey(c)), body.toString(), "application/json"));
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        }
    }

    private static void saveAuth(Context c, JSONObject r, String email) {
        long exp = System.currentTimeMillis() + (r.optLong("expiresIn", 3600) - 120) * 1000L;
        p(c).edit().putString("uid", r.optString("localId")).putString("token", r.optString("idToken"))
                .putString("refresh", r.optString("refreshToken")).putLong("token_exp", exp)
                .putString("email", email).commit();
    }

    /** Creates the account and the users/{uid} record. Blocking. */
    public static void signUp(Context c, String email, String pass, String name) throws IOException {
        JSONObject r = authCall(c, "signUp", Data.obj("email", email, "password", pass, "returnSecureToken", true));
        saveAuth(c, r, email);
        p(c).edit().putString("my_name", name).commit();
        patch(c, "users/" + uid(c), Data.obj("name", name, "role", Data.role(c)));
    }

    /** Signs in and restores the couple link, if any. Blocking. */
    public static void signIn(Context c, String email, String pass) throws IOException {
        JSONObject r = authCall(c, "signInWithPassword",
                Data.obj("email", email, "password", pass, "returnSecureToken", true));
        saveAuth(c, r, email);
        Object u = get(c, "users/" + uid(c));
        if (u instanceof JSONObject) {
            JSONObject o = (JSONObject) u;
            SharedPreferences.Editor e = p(c).edit();
            if (o.has("name")) e.putString("my_name", o.optString("name"));
            String couple = o.optString("couple", "");
            if (!couple.isEmpty()) e.putString("cid", couple);
            e.commit();
            if (!couple.isEmpty()) {
                Sync.resetLocal(c);
                findPartner(c);
            }
        }
    }

    public static synchronized String token(Context c) throws IOException {
        String t = p(c).getString("token", "");
        if (!t.isEmpty() && System.currentTimeMillis() < p(c).getLong("token_exp", 0)) return t;
        String rt = p(c).getString("refresh", "");
        if (rt.isEmpty()) throw new Msg("يجب تسجيل الدخول");
        try {
            JSONObject r = new JSONObject(http("POST", TOKEN_BASE + "?key="
                    + enc(apiKey(c)), "grant_type=refresh_token&refresh_token=" + enc(rt),
                    "application/x-www-form-urlencoded"));
            t = r.optString("id_token");
            long exp = System.currentTimeMillis() + (r.optLong("expires_in", 3600) - 120) * 1000L;
            p(c).edit().putString("token", t).putString("refresh", r.optString("refresh_token", rt))
                    .putLong("token_exp", exp).commit();
            return t;
        } catch (org.json.JSONException e) {
            throw new IOException(e);
        }
    }

    public static void invalidateToken(Context c) {
        p(c).edit().putLong("token_exp", 0).commit();
    }

    // ---------------- database ----------------

    static String url(Context c, String path, String query) throws IOException {
        return dbUrl(c) + "/" + path + ".json?auth=" + enc(token(c)) + (query == null ? "" : "&" + query) + EXTRA_QUERY;
    }

    static Object parse(String s) {
        try {
            Object o = new JSONTokener(s).nextValue();
            return o == null ? JSONObject.NULL : o;
        } catch (Exception e) {
            return JSONObject.NULL;
        }
    }

    static String json(Object v) {
        if (v instanceof String) return JSONObject.quote((String) v);
        return String.valueOf(v);
    }

    private static String db(Context c, String method, String path, Object body) throws IOException {
        try {
            return http(method, url(c, path, null), body == null ? null : json(body), "application/json");
        } catch (HttpError e) {
            if (e.code == 401) { // token may have expired early: refresh once and retry
                invalidateToken(c);
                return http(method, url(c, path, null), body == null ? null : json(body), "application/json");
            }
            throw e;
        }
    }

    public static Object get(Context c, String path) throws IOException {
        return parse(db(c, "GET", path, null));
    }

    public static void put(Context c, String path, Object v) throws IOException {
        db(c, "PUT", path, v);
    }

    public static void patch(Context c, String path, JSONObject v) throws IOException {
        db(c, "PATCH", path, v);
    }

    public static String post(Context c, String path, Object v) throws IOException {
        Object r = parse(db(c, "POST", path, v));
        return r instanceof JSONObject ? ((JSONObject) r).optString("name") : "";
    }

    public static void delete(Context c, String path) throws IOException {
        db(c, "DELETE", path, null);
    }

    public static JSONObject serverTime() {
        return Data.obj(".sv", "timestamp");
    }

    // ---------------- couple ----------------

    static String randomId(int n) {
        String chars = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
        SecureRandom r = new SecureRandom();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < n; i++) sb.append(chars.charAt(r.nextInt(chars.length())));
        return sb.toString();
    }

    static JSONObject myProfile(Context c) {
        return Data.obj("name", myName(c), "role", Data.role(c), "lastSeen", System.currentTimeMillis());
    }

    /** Creates our couple space (we are its first member) and uploads local lists. Blocking. */
    public static void createCouple(Context c) throws IOException {
        String uid = uid(c);
        String cid = randomId(20);
        put(c, "couples/" + cid + "/members/" + uid, true);
        put(c, "couples/" + cid + "/profiles/" + uid, myProfile(c));
        patch(c, "users/" + uid, Data.obj("couple", cid));
        p(c).edit().putString("cid", cid).commit();
        Sync.uploadAll(c);
    }

    /** Makes a 6-digit invite code for our couple and returns the text to send. Blocking. */
    public static String createInvite(Context c) throws IOException {
        if (cid(c).isEmpty()) createCouple(c);
        SecureRandom r = new SecureRandom();
        for (int attempt = 0; attempt < 6; attempt++) {
            String code = String.valueOf(100000 + r.nextInt(900000));
            try {
                put(c, "codes/" + code, Data.obj("couple", cid(c), "owner", uid(c), "t", System.currentTimeMillis()));
            } catch (HttpError e) {
                if (e.code == 401 || e.code == 403) continue; // code taken by someone else
                throw e;
            }
            String payload = Data.obj("k", apiKey(c), "d", dbUrl(c), "c", code).toString();
            String b64 = android.util.Base64.encodeToString(payload.getBytes("UTF-8"),
                    android.util.Base64.NO_WRAP | android.util.Base64.URL_SAFE);
            String who = Data.isWife(c) ? "زوجتك" : "زوجك";
            String text = "💌 دعوة من " + who + " " + myName(c) + " إلى تطبيق Bouchra 💕\n\n"
                    + "1) افتح تطبيق Bouchra ← الدردشة 💬\n"
                    + "2) اضغط «📥 لدي دعوة» والصق هذه الرسالة كاملة\n\n"
                    + "رمز الربط: " + code + "\n"
                    + "BOUCHRA:" + b64;
            p(c).edit().putString("my_invite", text).putString("my_invite_code", code).commit();
            return text;
        }
        throw new Msg("تعذّر إنشاء رمز، حاول مرة أخرى");
    }

    /** Parses a pasted invite. Saves server config from it. Returns the code or null. */
    public static String readInvite(Context c, String text) {
        int i = text.indexOf("BOUCHRA:");
        if (i < 0) return null;
        String b64 = text.substring(i + 8).trim().split("\\s")[0];
        try {
            String js = new String(android.util.Base64.decode(b64,
                    android.util.Base64.NO_WRAP | android.util.Base64.URL_SAFE), "UTF-8");
            JSONObject o = new JSONObject(js);
            String code = o.optString("c");
            if (code.isEmpty()) return null;
            if (!o.optString("k").isEmpty() && !o.optString("d").isEmpty()) setConfig(c, o.optString("k"), o.optString("d"));
            p(c).edit().putString("pending_invite", code).commit();
            return code;
        } catch (Exception e) {
            return null;
        }
    }

    /** Joins the couple behind an invite code. Blocking. */
    public static void join(Context c, String code) throws IOException {
        String uid = uid(c);
        put(c, "users/" + uid + "/joinCode", code);
        Object o = get(c, "codes/" + code);
        if (!(o instanceof JSONObject)) {
            p(c).edit().remove("pending_invite").commit();
            throw new Msg("الدعوة غير صالحة أو استُعملت من قبل. اطلب دعوة جديدة 💌");
        }
        String cid = ((JSONObject) o).optString("couple");
        // Join and use up the code in one atomic write (the rules require both together).
        JSONObject both = Data.obj("couples/" + cid + "/members/" + uid, true);
        Data.put(both, "couples/" + cid + "/full", true);
        Data.put(both, "codes/" + code, JSONObject.NULL);
        try {
            patch(c, "", both);
        } catch (HttpError e) {
            if (e.code == 401 || e.code == 403) throw new Msg("لا يمكن الانضمام بهذه الدعوة. اطلب دعوة جديدة 💌");
            throw e;
        }
        put(c, "couples/" + cid + "/profiles/" + uid, myProfile(c));
        patch(c, "users/" + uid, Data.obj("couple", cid));
        p(c).edit().putString("cid", cid).remove("pending_invite").commit();
        Sync.resetLocal(c);
        findPartner(c);
        sendInbox(c, "join", "💞 " + myName(c), Data.isWife(c) ? "انضمت إليك! أصبحتما مرتبطين 💕" : "انضم إليك! أصبحتما مرتبطين 💕");
    }

    /** Looks up the other member's uid and name. Blocking. */
    public static String findPartner(Context c) throws IOException {
        if (!partnerUid(c).isEmpty()) return partnerUid(c);
        Object m = get(c, "couples/" + cid(c) + "/profiles");
        if (m instanceof JSONObject) {
            JSONObject o = (JSONObject) m;
            Iterator<String> it = o.keys();
            while (it.hasNext()) {
                String k = it.next();
                if (!k.equals(uid(c))) {
                    JSONObject pr = o.optJSONObject(k);
                    setPartner(c, k, pr == null ? "" : pr.optString("name"), pr == null ? "" : pr.optString("role"));
                    return k;
                }
            }
        }
        return "";
    }

    /** Blocking: posts a notification into the partner's inbox. */
    static void sendInbox(Context c, String kind, String title, String text) throws IOException {
        String pu = findPartner(c);
        if (pu.isEmpty()) return;
        post(c, "couples/" + cid(c) + "/inbox/" + pu,
                Data.obj("kind", kind, "title", title, "text", text, "t", System.currentTimeMillis()));
    }

    /** Fire-and-forget partner notification (no-op when not linked). */
    public static void notifyPartner(Context ctx, final String kind, final String title, final String text) {
        final Context c = ctx.getApplicationContext();
        if (!linked(c)) return;
        EX.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    sendInbox(c, kind, title, text);
                } catch (Exception ignored) {
                }
            }
        });
    }

    public static void patchAsync(Context ctx, final String path, final JSONObject v) {
        final Context c = ctx.getApplicationContext();
        if (!linked(c)) return;
        EX.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    patch(c, path, v);
                } catch (Exception ignored) {
                }
            }
        });
    }

    // ---------------- async helper ----------------

    public interface Job {
        Object run() throws Exception;
    }

    public interface Done {
        void ok(Object result);

        void fail(String message);
    }

    /** Runs a blocking job off the UI thread and reports back on the UI thread. */
    public static void async(final Context c, final Job job, final Done done) {
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    final Object r = job.run();
                    main().post(new Runnable() {
                        @Override
                        public void run() {
                            done.ok(r);
                        }
                    });
                } catch (final Exception e) {
                    final String m = errorText(e);
                    main().post(new Runnable() {
                        @Override
                        public void run() {
                            done.fail(m);
                        }
                    });
                }
            }
        }).start();
    }

    public static String errorText(Exception e) {
        if (e instanceof Msg) return e.getMessage();
        if (e instanceof HttpError) {
            String b = ((HttpError) e).body;
            String m = b;
            try {
                JSONObject o = new JSONObject(b);
                Object err = o.opt("error");
                if (err instanceof JSONObject) m = ((JSONObject) err).optString("message");
                else if (err != null) m = String.valueOf(err);
            } catch (Exception ignored) {
            }
            if (m.contains("EMAIL_EXISTS")) return "هذا البريد مسجل من قبل، استعمل «تسجيل الدخول»";
            if (m.contains("EMAIL_NOT_FOUND") || m.contains("INVALID_PASSWORD") || m.contains("INVALID_LOGIN_CREDENTIALS"))
                return "البريد أو كلمة السر غير صحيحة";
            if (m.contains("WEAK_PASSWORD")) return "كلمة السر قصيرة: 6 أحرف على الأقل";
            if (m.contains("INVALID_EMAIL")) return "البريد الإلكتروني غير صحيح";
            if (m.contains("OPERATION_NOT_ALLOWED")) return "فعّل «Email/Password» في Firebase Authentication";
            if (m.contains("API key not valid") || m.contains("API_KEY_INVALID")) return "مفتاح API غير صحيح";
            if (m.contains("TOO_MANY_ATTEMPTS")) return "محاولات كثيرة، انتظر قليلاً";
            if (m.contains("Permission denied")) return "رُفض الوصول: تحقق من قواعد قاعدة البيانات (Rules)";
            if (((HttpError) e).code == 404) return "رابط قاعدة البيانات غير صحيح";
            return "خطأ من الخادم: " + m;
        }
        if (e instanceof java.net.UnknownHostException) return "لا يوجد اتصال بالإنترنت أو الرابط غير صحيح";
        if (e instanceof IOException) return "تعذّر الاتصال، تحقق من الإنترنت";
        return "خطأ: " + e;
    }

    // ---------------- live stream (Server-Sent Events) ----------------

    public interface StreamListener {
        /** event is "put" or "patch"; data may be JSONObject.NULL. Called on the stream thread. */
        void onEvent(String event, String path, Object data);
    }

    /** Keeps a live connection to one database path and reconnects when it drops. */
    public static class Stream {
        private final Context c;
        private final String path;
        private final String query;
        private final StreamListener l;
        private volatile boolean stopped;
        private volatile HttpURLConnection con;
        private Thread t;

        public Stream(Context c, String path, String query, StreamListener l) {
            this.c = c.getApplicationContext();
            this.path = path;
            this.query = query;
            this.l = l;
        }

        public Stream start() {
            t = new Thread(new Runnable() {
                @Override
                public void run() {
                    loop();
                }
            });
            t.setDaemon(true);
            t.start();
            return this;
        }

        private void loop() {
            long backoff = 2000;
            while (!stopped) {
                if (!linked(c)) break;
                try {
                    HttpURLConnection h = (HttpURLConnection) new URL(url(c, path, query)).openConnection();
                    con = h;
                    h.setRequestProperty("Accept", "text/event-stream");
                    h.setConnectTimeout(15000);
                    h.setReadTimeout(90000);
                    int code = h.getResponseCode();
                    if (code == 401) {
                        invalidateToken(c);
                        throw new IOException("401");
                    }
                    if (code >= 400) throw new IOException("HTTP " + code);
                    BufferedReader r = new BufferedReader(new InputStreamReader(h.getInputStream(), "UTF-8"));
                    String line;
                    String event = "";
                    backoff = 2000;
                    while (!stopped && (line = r.readLine()) != null) {
                        if (line.startsWith("event:")) {
                            event = line.substring(6).trim();
                        } else if (line.startsWith("data:")) {
                            String d = line.substring(5).trim();
                            if ("put".equals(event) || "patch".equals(event)) {
                                JSONObject o = new JSONObject(d);
                                Object data = o.opt("data");
                                l.onEvent(event, o.optString("path", "/"), data == null ? JSONObject.NULL : data);
                            } else if ("auth_revoked".equals(event)) {
                                invalidateToken(c);
                                break;
                            } else if ("cancel".equals(event)) {
                                break;
                            }
                        }
                    }
                } catch (Exception ignored) {
                } finally {
                    HttpURLConnection h = con;
                    if (h != null) h.disconnect();
                }
                if (stopped) break;
                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException e) {
                    break;
                }
                backoff = Math.min(backoff * 2, 60000);
            }
        }

        public void close() {
            stopped = true;
            HttpURLConnection h = con;
            if (h != null) {
                try {
                    h.disconnect();
                } catch (Exception ignored) {
                }
            }
            if (t != null) t.interrupt();
        }
    }

    /** Applies a stream event to a local JSON tree. Returns the (possibly new) root. */
    public static JSONObject apply(JSONObject root, String event, String path, Object data) {
        if ("patch".equals(event) && data instanceof JSONObject) {
            JSONObject d = (JSONObject) data;
            Iterator<String> it = d.keys();
            while (it.hasNext()) {
                String k = it.next();
                root = setAt(root, path + "/" + k, d.opt(k));
            }
            return root;
        }
        return setAt(root, path, data);
    }

    static JSONObject setAt(JSONObject root, String path, Object val) {
        String[] parts = path.split("/");
        java.util.List<String> segs = new java.util.ArrayList<String>();
        for (String s : parts) if (!s.isEmpty()) segs.add(s);
        boolean remove = val == null || val == JSONObject.NULL;
        if (segs.isEmpty()) return val instanceof JSONObject ? (JSONObject) val : new JSONObject();
        JSONObject cur = root;
        for (int i = 0; i < segs.size() - 1; i++) {
            JSONObject next = cur.optJSONObject(segs.get(i));
            if (next == null) {
                if (remove) return root;
                next = new JSONObject();
                Data.put(cur, segs.get(i), next);
            }
            cur = next;
        }
        String last = segs.get(segs.size() - 1);
        if (remove) cur.remove(last);
        else Data.put(cur, last, val instanceof JSONArray ? toObject((JSONArray) val) : val);
        return root;
    }

    /** Firebase may return integer-keyed maps as arrays; turn them back into objects. */
    static JSONObject toObject(JSONArray a) {
        JSONObject o = new JSONObject();
        for (int i = 0; i < a.length(); i++) {
            if (!a.isNull(i)) Data.put(o, String.valueOf(i), a.opt(i));
        }
        return o;
    }
}
