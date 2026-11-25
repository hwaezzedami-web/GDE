package com.bouchra.love;

import android.content.Context;
import android.util.Base64;

import org.json.JSONObject;

import java.math.BigInteger;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.KeyFactory;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.ECParameterSpec;
import java.security.spec.ECPrivateKeySpec;

/**
 * Wakes the partner's iPhone web app (Apple Web Push) without any server of our own.
 * The web app stores its push subscription and its VAPID key pair at
 * couples/{cid}/push/{uid}; we sign a VAPID token with that key and send an empty push.
 * The web app's service worker then reads the waiting notifications from the inbox.
 */
public class WebPush {

    /** "sub" claim required by push services: who sends these pushes. */
    static final String SUBJECT = "https://hwaezzedami-web.github.io/GDE/";

    private static ECParameterSpec p256;

    static synchronized ECParameterSpec p256() throws Exception {
        if (p256 == null) {
            KeyPairGenerator g = KeyPairGenerator.getInstance("EC");
            g.initialize(new ECGenParameterSpec("secp256r1"));
            p256 = ((ECPublicKey) g.generateKeyPair().getPublic()).getParams();
        }
        return p256;
    }

    static String b64u(byte[] b) {
        return Base64.encodeToString(b, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    static byte[] unb64u(String s) {
        return Base64.decode(s, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    }

    /** ES256 JWT for the push service at {@code audience}, signed with the raw private key {@code d}. */
    public static String vapidJwt(String audience, String d, long nowSeconds) throws Exception {
        String header = b64u("{\"typ\":\"JWT\",\"alg\":\"ES256\"}".getBytes("UTF-8"));
        JSONObject claims = Data.obj("aud", audience, "exp", nowSeconds + 12 * 3600, "sub", SUBJECT);
        String body = b64u(claims.toString().getBytes("UTF-8"));
        String signingInput = header + "." + body;

        PrivateKey key = KeyFactory.getInstance("EC").generatePrivate(
                new ECPrivateKeySpec(new BigInteger(1, unb64u(d)), p256()));
        Signature s = Signature.getInstance("SHA256withECDSA");
        s.initSign(key);
        s.update(signingInput.getBytes("UTF-8"));
        return signingInput + "." + b64u(derToRaw(s.sign()));
    }

    /** ECDSA signatures come DER-encoded; JWT wants r||s, 32 bytes each. */
    static byte[] derToRaw(byte[] der) {
        int i = 2;
        if ((der[1] & 0x80) != 0) i += der[1] & 0x7f;
        byte[] out = new byte[64];
        for (int part = 0; part < 2; part++) {
            i++; // 0x02 INTEGER
            int len = der[i++];
            int start = i;
            while (len > 32 && der[start] == 0) {
                start++;
                len--;
            }
            System.arraycopy(der, start, out, part * 32 + (32 - len), len);
            i = start + len;
        }
        return out;
    }

    /** Blocking. Sends one wake-up push to the partner if they use the web app. */
    public static void wake(Context c, String partnerUid) {
        try {
            Object o = Cloud.get(c, "couples/" + Cloud.cid(c) + "/push/" + partnerUid);
            if (!(o instanceof JSONObject)) return;
            JSONObject sub = (JSONObject) o;
            JSONObject vapid = sub.optJSONObject("vapid");
            String endpoint = sub.optString("endpoint");
            if (vapid == null || endpoint.isEmpty() || !endpoint.startsWith("https://")) return;
            URL u = new URL(endpoint);
            String jwt = vapidJwt(u.getProtocol() + "://" + u.getHost(), vapid.optString("d"),
                    System.currentTimeMillis() / 1000L);
            HttpURLConnection con = (HttpURLConnection) u.openConnection();
            try {
                con.setConnectTimeout(15000);
                con.setReadTimeout(15000);
                con.setRequestMethod("POST");
                con.setRequestProperty("Authorization", "vapid t=" + jwt + ", k=" + vapid.optString("pub"));
                con.setRequestProperty("TTL", "86400");
                con.setRequestProperty("Urgency", "high");
                con.setDoOutput(true);
                con.setFixedLengthStreamingMode(0);
                con.getOutputStream().close();
                int code = con.getResponseCode();
                if (code == 404 || code == 410) { // subscription expired: forget it
                    Cloud.delete(c, "couples/" + Cloud.cid(c) + "/push/" + partnerUid);
                }
            } finally {
                con.disconnect();
            }
        } catch (Exception ignored) {
        }
    }
}
