import com.bouchra.love.Cloud;
import com.bouchra.love.Data;
import com.bouchra.love.WebPush;

import org.json.JSONObject;

import java.io.File;
import java.nio.file.Files;
import java.util.Iterator;
import java.util.Map;

/**
 * Plays the husband's Android phone (real Cloud code) for the web app test.
 * State is kept in a JSON file between calls.
 *   setup            sign up, create an invite, print INVITE (full text) and CODE
 *   send TEXT        chat message + inbox notification to the wife
 *   addshop TEXT     add a shopping item (Android data format)
 *   dump             print messages, shopping, profiles, push subscription
 *   jwt AUD D        print a VAPID JWT (for the signature test)
 */
public class HusbandCli {
    static File stateFile;

    public static void main(String[] a) throws Exception {
        if (a[0].equals("jwt")) {
            System.out.println(WebPush.vapidJwt(a[1], a[2], System.currentTimeMillis() / 1000L));
            return;
        }
        stateFile = new File(a[1]);
        setStatic("AUTH_BASE", "http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/accounts:");
        setStatic("TOKEN_BASE", "http://127.0.0.1:9099/securetoken.googleapis.com/v1/token");
        setStatic("EXTRA_QUERY", "&ns=demo-bouchra-default-rtdb");
        CloudTest.Phone p = new CloudTest.Phone("husband");
        load(p);
        Cloud.setConfig(p, "fake-api-key", "http://127.0.0.1:9000");
        String cid;
        switch (a[0]) {
            case "setup":
                Cloud.signUp(p, "husband" + System.nanoTime() + "@test.com", "secret1", "أحمد");
                Data.p(p).edit().putLong(Data.SINCE, 1600000000000L).commit();
                org.json.JSONArray shop = new org.json.JSONArray();
                shop.put(Data.obj("id", 1L, "text", "طماطم", "cat", 0, "bought", false));
                Data.saveLocal(p, Data.SHOPPING, shop);
                org.json.JSONArray coupons = new org.json.JSONArray();
                coupons.put(Data.obj("id", 1L, "emoji", "💆‍♀️", "title", "مساج 30 دقيقة", "used", false, "usedDate", 0L));
                Data.saveLocal(p, Data.COUPONS, coupons);
                String invite = Cloud.createInvite(p);
                System.out.println("INVITE=" + invite.replace("\n", "\\n"));
                System.out.println("CODE=" + Data.p(p).getString("my_invite_code", ""));
                break;
            case "send":
                cid = Cloud.cid(p);
                Cloud.post(p, "couples/" + cid + "/messages", Data.obj("from", Cloud.uid(p), "text", a[2], "type", "text",
                        "t", Cloud.serverTime(), "read", false));
                Cloud.sendInbox(p, "msg", "💬 أحمد", a[2]);
                break;
            case "addshop":
                cid = Cloud.cid(p);
                long id = System.currentTimeMillis() * 1000L + 7;
                Cloud.patch(p, "couples/" + cid + "/shared/shopping",
                        Data.obj("i" + id, Data.obj("id", id, "text", a[2], "cat", 4, "bought", false)));
                break;
            case "dump":
                cid = Cloud.cid(p);
                Cloud.partnerUid(p);
                System.out.println("PARTNER=" + Cloud.findPartner(p));
                System.out.println("MESSAGES=" + Cloud.get(p, "couples/" + cid + "/messages"));
                System.out.println("SHOPPING=" + Cloud.get(p, "couples/" + cid + "/shared/shopping"));
                System.out.println("COUPONS=" + Cloud.get(p, "couples/" + cid + "/shared/coupons"));
                System.out.println("PROFILES=" + Cloud.get(p, "couples/" + cid + "/profiles"));
                System.out.println("INBOX=" + Cloud.get(p, "couples/" + cid + "/inbox/" + Cloud.uid(p)));
                break;
        }
        save(p);
        Cloud.EX.shutdown();
        Cloud.EX.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS);
    }

    static void load(CloudTest.Phone p) throws Exception {
        if (!stateFile.exists()) return;
        JSONObject o = new JSONObject(new String(Files.readAllBytes(stateFile.toPath()), "UTF-8"));
        Iterator<String> it = o.keys();
        while (it.hasNext()) {
            String k = it.next();
            JSONObject e = o.getJSONObject(k);
            String t = e.getString("t");
            Object v = t.equals("l") ? (Object) e.getLong("v") : t.equals("i") ? (Object) e.getInt("v")
                    : t.equals("b") ? (Object) e.getBoolean("v") : e.getString("v");
            p.prefs.m.put(k, v);
        }
    }

    static void save(CloudTest.Phone p) throws Exception {
        JSONObject o = new JSONObject();
        for (Map.Entry<String, Object> e : p.prefs.m.entrySet()) {
            Object v = e.getValue();
            String t = v instanceof Long ? "l" : v instanceof Integer ? "i" : v instanceof Boolean ? "b" : "s";
            o.put(e.getKey(), Data.obj("t", t, "v", v));
        }
        Files.write(stateFile.toPath(), o.toString().getBytes("UTF-8"));
    }

    static void setStatic(String name, String v) throws Exception {
        java.lang.reflect.Field f = Cloud.class.getDeclaredField(name);
        f.setAccessible(true);
        f.set(null, v);
    }
}
