package com.bouchra.love;

import android.content.Context;
import android.content.Intent;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

/**
 * Keeps the shared lists the same on both phones.
 * Local edits are diffed per item and sent as one PATCH (queued while offline);
 * server changes arrive through LoveService's live stream.
 */
public class Sync {

    public static final String ACTION_SHARED = "com.bouchra.love.SHARED";
    static final String[] KEYS = {Data.SHOPPING, Data.DREAMS, Data.COUPONS, Data.OCCASIONS};

    public static boolean isShared(String key) {
        for (String k : KEYS) if (k.equals(key)) return true;
        return false;
    }

    static String base(Context c) {
        return "couples/" + Cloud.cid(c) + "/shared";
    }

    static JSONObject obj(Context c, String pref) {
        try {
            return new JSONObject(Data.p(c).getString(pref, "{}"));
        } catch (Exception e) {
            return new JSONObject();
        }
    }

    static JSONObject pending(Context c) {
        return obj(c, "pending");
    }

    static void savePending(Context c, JSONObject p) {
        Data.p(c).edit().putString("pending", p.toString()).commit();
    }

    // ---------------- local -> server ----------------

    static Map<String, String> byId(JSONArray a) {
        Map<String, String> m = new HashMap<String, String>();
        for (JSONObject o : Data.items(a)) m.put("i" + o.optLong("id"), o.toString());
        return m;
    }

    /** Called by Data.save for shared lists while linked. */
    static synchronized void localChange(Context c, String key, JSONArray oldA, JSONArray newA) {
        Map<String, String> before = byId(oldA);
        Map<String, String> after = byId(newA);
        JSONObject pend = pending(c);
        JSONObject kp = pend.optJSONObject(key);
        if (kp == null) kp = new JSONObject();
        boolean changed = false;
        for (Map.Entry<String, String> e : after.entrySet()) {
            if (!e.getValue().equals(before.get(e.getKey()))) {
                try {
                    Data.put(kp, e.getKey(), new JSONObject(e.getValue()));
                    changed = true;
                } catch (Exception ignored) {
                }
            }
        }
        for (String k : before.keySet()) {
            if (!after.containsKey(k)) {
                Data.put(kp, k, JSONObject.NULL);
                changed = true;
            }
        }
        if (!changed) return;
        Data.put(pend, key, kp);
        savePending(c, pend);
        flushAsync(c);
    }

    public static void setSince(Context c, long v) {
        Data.p(c).edit().putLong(Data.SINCE, v).commit();
        if (!Cloud.linked(c)) return;
        JSONObject pend = pending(c);
        Data.put(pend, "since", v);
        savePending(c, pend);
        flushAsync(c);
    }

    public static void flushAsync(Context ctx) {
        final Context c = ctx.getApplicationContext();
        Cloud.EX.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    flush(c);
                } catch (Exception ignored) {
                }
            }
        });
    }

    /** Sends queued changes. Blocking; safe to call often. */
    public static void flush(Context c) throws Exception {
        if (!Cloud.linked(c)) return;
        JSONObject sent = pending(c);
        Iterator<String> it = sent.keys();
        List<String> keys = new ArrayList<String>();
        while (it.hasNext()) keys.add(it.next());
        for (String key : keys) {
            Object v = sent.opt(key);
            if ("since".equals(key)) Cloud.put(c, base(c) + "/since", v);
            else if (v instanceof JSONObject) Cloud.patch(c, base(c) + "/" + key, (JSONObject) v);
            // drop what was sent, keeping anything edited meanwhile
            synchronized (Sync.class) {
                JSONObject now = pending(c);
                Object cur = now.opt(key);
                if ("since".equals(key)) {
                    if (cur != null && String.valueOf(cur).equals(String.valueOf(v))) now.remove(key);
                } else if (cur instanceof JSONObject && v instanceof JSONObject) {
                    JSONObject cp = (JSONObject) cur;
                    JSONObject sp = (JSONObject) v;
                    Iterator<String> ik = sp.keys();
                    while (ik.hasNext()) {
                        String id = ik.next();
                        if (String.valueOf(cp.opt(id)).equals(String.valueOf(sp.opt(id)))) cp.remove(id);
                    }
                    if (cp.length() == 0) now.remove(key);
                }
                savePending(c, now);
            }
        }
    }

    /** First member: upload everything we have locally. Blocking. */
    static void uploadAll(Context c) throws java.io.IOException {
        JSONObject shared = new JSONObject();
        for (String key : KEYS) {
            JSONObject m = new JSONObject();
            for (JSONObject o : Data.items(Data.list(c, key))) Data.put(m, "i" + o.optLong("id"), o);
            Data.put(shared, key, m);
        }
        long since = Data.p(c).getLong(Data.SINCE, 0);
        if (since > 0) Data.put(shared, "since", since);
        Cloud.put(c, base(c), shared);
        Data.p(c).edit().remove("pending").putString("shared_cache", shared.toString()).commit();
    }

    /** Joining member: the server copy wins; local lists are replaced when the stream connects. */
    static void resetLocal(Context c) {
        Data.p(c).edit().remove("pending").putString("shared_cache", "{}").commit();
    }

    // ---------------- server -> local ----------------

    public static synchronized void onEvent(Context c, String event, String path, Object data) {
        JSONObject cache = Cloud.apply(obj(c, "shared_cache"), event, path, data);
        Data.p(c).edit().putString("shared_cache", cache.toString()).commit();
        applyCache(c, cache);
        c.sendBroadcast(new Intent(ACTION_SHARED).setPackage(c.getPackageName()));
    }

    static void applyCache(Context c, JSONObject cache) {
        JSONObject pend = pending(c);
        for (String key : KEYS) {
            Map<String, JSONObject> m = new HashMap<String, JSONObject>();
            JSONObject server = cache.optJSONObject(key);
            if (server != null) {
                Iterator<String> it = server.keys();
                while (it.hasNext()) {
                    String k = it.next();
                    JSONObject o = server.optJSONObject(k);
                    if (o != null) m.put(k, o);
                }
            }
            JSONObject kp = pend.optJSONObject(key); // our unsent edits win
            if (kp != null) {
                Iterator<String> it = kp.keys();
                while (it.hasNext()) {
                    String k = it.next();
                    JSONObject o = kp.optJSONObject(k);
                    if (o == null) m.remove(k);
                    else m.put(k, o);
                }
            }
            List<JSONObject> items = new ArrayList<JSONObject>(m.values());
            Collections.sort(items, new Comparator<JSONObject>() {
                @Override
                public int compare(JSONObject x, JSONObject y) {
                    return Long.compare(x.optLong("id"), y.optLong("id"));
                }
            });
            JSONArray arr = new JSONArray();
            for (JSONObject o : items) arr.put(o);
            Data.saveLocal(c, key, arr);
        }
        if (!pend.has("since") && cache.has("since")) {
            Data.p(c).edit().putLong(Data.SINCE, cache.optLong("since")).commit();
        }
    }
}
