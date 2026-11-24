import android.content.ContextWrapper;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import com.bouchra.love.Cloud;
import com.bouchra.love.Data;
import com.bouchra.love.Sync;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * End-to-end test of the app's real Cloud/Sync code against the Firebase emulator
 * (auth on :9099, database on :9000 with firebase/database.rules.json).
 * Simulates three phones: husband (A), wife (B) and a stranger (C).
 */
public class CloudTest {

    // ---------- minimal in-memory Android plumbing ----------
    static class Prefs implements SharedPreferences {
        final Map<String, Object> m = new HashMap<String, Object>();

        public Map<String, ?> getAll() { return m; }
        public String getString(String k, String d) { return m.containsKey(k) ? (String) m.get(k) : d; }
        @SuppressWarnings("unchecked")
        public Set<String> getStringSet(String k, Set<String> d) { return m.containsKey(k) ? (Set<String>) m.get(k) : d; }
        public int getInt(String k, int d) { return m.containsKey(k) ? (Integer) m.get(k) : d; }
        public long getLong(String k, long d) { return m.containsKey(k) ? (Long) m.get(k) : d; }
        public float getFloat(String k, float d) { return m.containsKey(k) ? (Float) m.get(k) : d; }
        public boolean getBoolean(String k, boolean d) { return m.containsKey(k) ? (Boolean) m.get(k) : d; }
        public boolean contains(String k) { return m.containsKey(k); }
        public void registerOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l) { }
        public void unregisterOnSharedPreferenceChangeListener(OnSharedPreferenceChangeListener l) { }

        public Editor edit() {
            final Map<String, Object> pend = new HashMap<String, Object>();
            final List<String> rm = new ArrayList<String>();
            return new Editor() {
                public Editor putString(String k, String v) { pend.put(k, v); return this; }
                public Editor putStringSet(String k, Set<String> v) { pend.put(k, v); return this; }
                public Editor putInt(String k, int v) { pend.put(k, v); return this; }
                public Editor putLong(String k, long v) { pend.put(k, v); return this; }
                public Editor putFloat(String k, float v) { pend.put(k, v); return this; }
                public Editor putBoolean(String k, boolean v) { pend.put(k, v); return this; }
                public Editor remove(String k) { rm.add(k); return this; }
                public Editor clear() { m.clear(); return this; }
                public boolean commit() {
                    synchronized (m) { for (String k : rm) m.remove(k); m.putAll(pend); }
                    return true;
                }
                public void apply() { commit(); }
            };
        }
    }

    static class Phone extends ContextWrapper {
        final Prefs prefs = new Prefs();
        int broadcasts;
        Phone(String role) {
            super(null);
            if (role != null) prefs.edit().putString("role", role).commit();
        }
        @Override public SharedPreferences getSharedPreferences(String n, int mode) { return prefs; }
        @Override public Context getApplicationContext() { return this; }
        @Override public String getPackageName() { return "com.bouchra.love"; }
        @Override public void sendBroadcast(Intent i) { broadcasts++; }
    }

    // ---------- tiny test framework ----------
    static int pass, fail;

    static void check(String name, boolean ok) {
        System.out.println((ok ? "  PASS  " : "  FAIL  ") + name);
        if (ok) pass++; else fail++;
    }

    static boolean denied(Runnable r) {
        try { r.run(); return false; } catch (RuntimeException e) { return true; }
    }

    interface Io { void run() throws Exception; }

    static Runnable io(final Io x) {
        return new Runnable() {
            public void run() {
                try { x.run(); } catch (Exception e) { throw new RuntimeException(e); }
            }
        };
    }

    static boolean waitFor(java.util.concurrent.Callable<Boolean> cond) throws Exception {
        for (int i = 0; i < 100; i++) {
            if (cond.call()) return true;
            Thread.sleep(100);
        }
        return false;
    }

    static JSONArray list(Context c, String k) { return Data.list(c, k); }

    static boolean hasText(Context c, String key, String text) {
        for (JSONObject o : Data.items(list(c, key))) {
            if (text.equals(o.optString("text")) || text.equals(o.optString("title"))) return true;
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        Cloud.class.getDeclaredField("AUTH_BASE").setAccessible(true);
        setStatic("AUTH_BASE", "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:");
        setStatic("TOKEN_BASE", "http://127.0.0.1:9099/securetoken.googleapis.com/v1/token");
        setStatic("EXTRA_QUERY", "&ns=demo-bouchra-default-rtdb");
        String run = String.valueOf(System.currentTimeMillis() % 100000);

        final Phone A = new Phone("husband"), B = new Phone("wife"), C = new Phone("husband");
        Cloud.setConfig(A, "fake-api-key", "http://127.0.0.1:9000/");

        System.out.println("== accounts");
        Cloud.signUp(A, "ahmed" + run + "@test.com", "secret1", "أحمد");
        check("husband signed up", Cloud.signedIn(A));
        check("weak password rejected with Arabic message",
                Cloud.errorText(captured(io(new Io() { public void run() throws Exception {
                    Cloud.setConfig(C, "fake-api-key", "http://127.0.0.1:9000");
                    Cloud.signUp(C, "weak" + System.nanoTime() + "@test.com", "123", "x");
                }}))).contains("6"));

        // husband had local data from phase 1
        JSONArray shop = new JSONArray();
        shop.put(Data.obj("id", 1, "text", "طماطم", "cat", 0, "bought", false));
        Data.saveLocal(A, Data.SHOPPING, shop);
        JSONArray dreams = new JSONArray();
        dreams.put(Data.obj("id", 1, "emoji", "🕋", "title", "عمرة معاً", "target", 5000L, "saved", 0L, "done", false));
        Data.saveLocal(A, Data.DREAMS, dreams);
        Data.p(A).edit().putLong(Data.SINCE, 1500000000000L).commit();

        System.out.println("== invite + join");
        final String invite = Cloud.createInvite(A);
        check("couple created", !Cloud.cid(A).isEmpty());
        check("invite text contains code and payload", invite.contains("BOUCHRA:") && invite.contains("رمز الربط"));
        check("local lists uploaded", Cloud.get(A, "couples/" + Cloud.cid(A) + "/shared/shopping") instanceof JSONObject);

        String code = Cloud.readInvite(B, "some whatsapp header\n" + invite + "\n");
        check("wife parsed invite and got server config", code != null && Cloud.configured(B));
        Cloud.signUp(B, "bouchra" + run + "@test.com", "secret2", "بشرى");
        Cloud.join(B, code);
        check("wife joined same couple", Cloud.cid(B).equals(Cloud.cid(A)));
        check("wife knows husband", Cloud.partnerUid(B).equals(Cloud.uid(A)));
        check("husband finds wife", Cloud.findPartner(A).equals(Cloud.uid(B)));

        System.out.println("== security");
        Cloud.signUp(C, "stranger" + run + "@test.com", "secret3", "غريب");
        final String cid = Cloud.cid(A);
        check("stranger cannot read couple", denied(io(new Io() { public void run() throws Exception {
            Cloud.get(C, "couples/" + cid); }})));
        check("stranger cannot reuse the used invite", denied(io(new Io() { public void run() throws Exception {
            Cloud.join(C, Cloud.readInvite(C, invite)); }})));
        check("stranger cannot add himself directly", denied(io(new Io() { public void run() throws Exception {
            Cloud.put(C, "couples/" + cid + "/members/" + Cloud.uid(C), true); }})));
        check("stranger cannot make a code for our couple", denied(io(new Io() { public void run() throws Exception {
            Cloud.put(C, "codes/999999", Data.obj("couple", cid, "owner", Cloud.uid(C))); }})));
        final String invite2 = Cloud.createInvite(A);
        check("couple is full: even a fresh invite cannot add a third person", denied(io(new Io() { public void run() throws Exception {
            Cloud.join(C, Cloud.readInvite(C, invite2)); }})));
        check("stranger cannot read wife's user record", denied(io(new Io() { public void run() throws Exception {
            Cloud.get(C, "users/" + Cloud.uid(B)); }})));

        System.out.println("== shared lists (live)");
        Cloud.Stream sb = new Cloud.Stream(B, "couples/" + cid + "/shared", null, listener(B)).start();
        Cloud.Stream sa = new Cloud.Stream(A, "couples/" + cid + "/shared", null, listener(A)).start();
        check("wife received husband's existing list", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { return hasText(B, Data.SHOPPING, "طماطم") && hasText(B, Data.DREAMS, "عمرة معاً"); }}));
        check("wedding date synced", Data.p(B).getLong(Data.SINCE, 0) == 1500000000000L);

        JSONArray bl = list(B, Data.SHOPPING);
        bl.put(Data.obj("id", Data.nextId(bl), "text", "خبز", "cat", 4, "bought", false));
        Data.save(B, Data.SHOPPING, bl);
        check("husband sees item the wife added", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { return hasText(A, Data.SHOPPING, "خبز"); }}));

        JSONArray al = list(A, Data.SHOPPING);
        for (JSONObject o : Data.items(al)) if ("خبز".equals(o.optString("text"))) Data.put(o, "bought", true);
        Data.save(A, Data.SHOPPING, al);
        check("wife sees it marked bought", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() {
                for (JSONObject o : Data.items(list(B, Data.SHOPPING)))
                    if ("خبز".equals(o.optString("text")) && o.optBoolean("bought")) return true;
                return false;
            }}));

        JSONArray al2 = list(A, Data.SHOPPING);
        JSONArray kept = new JSONArray();
        for (JSONObject o : Data.items(al2)) if (!"طماطم".equals(o.optString("text"))) kept.put(o);
        Data.save(A, Data.SHOPPING, kept);
        check("deletion reaches the wife", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { return !hasText(B, Data.SHOPPING, "طماطم") && hasText(B, Data.SHOPPING, "خبز"); }}));

        // both add at the same moment, 10 rounds: no item may be lost
        boolean allSurvived = true;
        for (int round = 0; round < 10 && allSurvived; round++) {
            final String ta = "حليب" + round, tb = "بيض" + round;
            JSONArray x = list(A, Data.SHOPPING), y = list(B, Data.SHOPPING);
            x.put(Data.obj("id", Data.nextId(x), "text", ta, "cat", 3, "bought", false));
            y.put(Data.obj("id", Data.nextId(y), "text", tb, "cat", 3, "bought", false));
            Data.save(A, Data.SHOPPING, x);
            Data.save(B, Data.SHOPPING, y);
            allSurvived = waitFor(new java.util.concurrent.Callable<Boolean>() {
                public Boolean call() {
                    return hasText(A, Data.SHOPPING, ta) && hasText(A, Data.SHOPPING, tb)
                            && hasText(B, Data.SHOPPING, ta) && hasText(B, Data.SHOPPING, tb);
                }});
        }
        check("simultaneous adds (10 rounds) all survive on both phones", allSurvived);
        check("UI refresh broadcasts sent", B.broadcasts > 0);

        System.out.println("== inbox notifications + chat");
        final List<String> got = new ArrayList<String>();
        Cloud.Stream ib = new Cloud.Stream(B, "couples/" + cid + "/inbox/" + Cloud.uid(B), null, new Cloud.StreamListener() {
            public void onEvent(String event, String path, Object data) {
                synchronized (got) { got.add(String.valueOf(data)); }
            }}).start();
        Thread.sleep(800);
        Cloud.notifyPartner(A, "miss", "💗 أحمد", "مشتاق لكِ كثيراً 🥺");
        check("wife's phone receives 'miss you' instantly", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { synchronized (got) { return got.toString().contains("مشتاق"); } }}));

        final JSONObject[] chat = {new JSONObject()};
        Cloud.Stream ms = new Cloud.Stream(A, "couples/" + cid + "/messages", "orderBy=%22%24key%22&limitToLast=150",
                new Cloud.StreamListener() {
                    public void onEvent(String e, String p, Object d) {
                        synchronized (chat) { chat[0] = Cloud.apply(chat[0], e, p, d); }
                    }}).start();
        Thread.sleep(800);
        String key = Cloud.post(B, "couples/" + cid + "/messages",
                Data.obj("from", Cloud.uid(B), "text", "أحبك ❤️", "type", "text", "t", Cloud.serverTime(), "read", false));
        check("husband's chat receives wife's message", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { synchronized (chat) { return chat[0].toString().contains("أحبك"); } }}));
        final String k = key;
        check("message has real server time", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { synchronized (chat) {
                JSONObject m = chat[0].optJSONObject(k);
                return m != null && m.optLong("t") > 1700000000000L; } }}));
        Cloud.patch(A, "couples/" + cid + "/messages", Data.obj(key + "/read", true));
        check("read receipt (✓✓) applied", waitFor(new java.util.concurrent.Callable<Boolean>() {
            public Boolean call() { synchronized (chat) {
                JSONObject m = chat[0].optJSONObject(k);
                return m != null && m.optBoolean("read"); } }}));

        System.out.println("== session");
        Cloud.invalidateToken(A);
        check("expired token refreshes automatically", Cloud.get(A, "couples/" + cid + "/members") instanceof JSONObject);
        Phone A2 = new Phone("husband");
        Cloud.setConfig(A2, "fake-api-key", "http://127.0.0.1:9000");
        Cloud.signIn(A2, "ahmed" + run + "@test.com", "secret1");
        check("signing in on a new phone restores the couple", Cloud.cid(A2).equals(cid) && Cloud.partnerUid(A2).equals(Cloud.uid(B)));
        check("wrong password gives Arabic message", Cloud.errorText(captured(io(new Io() { public void run() throws Exception {
            Cloud.signIn(new Phone("husband") {{ Cloud.setConfig(this, "fake-api-key", "http://127.0.0.1:9000"); }},
                    "ahmed" + "x@test.com", "nope123"); }}))).contains("غير صحيحة"));

        sa.close(); sb.close(); ib.close(); ms.close();
        System.out.println("\nRESULT: " + pass + " passed, " + fail + " failed");
        System.exit(fail == 0 ? 0 : 1);
    }

    static Cloud.StreamListener listener(final Context c) {
        return new Cloud.StreamListener() {
            public void onEvent(String event, String path, Object data) { Sync.onEvent(c, event, path, data); }
        };
    }

    static Exception captured(Runnable r) {
        try { r.run(); return new Exception("no error"); }
        catch (RuntimeException e) { return e.getCause() instanceof Exception ? (Exception) e.getCause() : e; }
    }

    static void setStatic(String name, String v) throws Exception {
        java.lang.reflect.Field f = Cloud.class.getDeclaredField(name);
        f.setAccessible(true);
        f.set(null, v);
    }
}
