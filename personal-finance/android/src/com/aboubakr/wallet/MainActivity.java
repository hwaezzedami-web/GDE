package com.aboubakr.wallet;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.Configuration;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Family wallet: the whole interface is assets/index.html in a WebView.
 * Data is a single JSON file in the app's private storage (wallet.json), written
 * through the AndroidWallet bridge, with the previous version kept as wallet.prev.json.
 * The bridge also schedules reminders, feeds the home-screen widget and stores receipt photos.
 */
public class MainActivity extends Activity {
    private static final int REQ_SAVE = 1;
    private static final int REQ_OPEN = 2;
    private static final int REQ_NOTIFY = 3;
    private static final String DATA = "wallet.json";
    private static final String PREV = "wallet.prev.json";
    private static final String NOTIFY_PERMISSION = "android.permission.POST_NOTIFICATIONS";

    private WebView web;
    private byte[] pendingBytes;
    private ValueCallback<Uri[]> fileCallback;
    private boolean cameraOffered;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 21) {
            getWindow().setStatusBarColor(Color.parseColor("#0B3D2E"));
            getWindow().setNavigationBarColor(isDark() ? Color.parseColor("#151E1A") : Color.parseColor("#0B3D2E"));
        }
        web = new WebView(this);
        web.setBackgroundColor(isDark() ? Color.parseColor("#0D1311") : Color.parseColor("#F2F5F3"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(true);
        web.addJavascriptInterface(new Bridge(), "AndroidWallet");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if (url.startsWith("file:///android_asset/")) return false;
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                } catch (Exception ignored) {
                    // no app can open this link
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                String[] types = params.getAcceptTypes();
                boolean image = types != null && types.length > 0 && types[0] != null && types[0].startsWith("image");
                try {
                    startActivityForResult(image ? photoChooser() : documentPicker(), REQ_OPEN);
                } catch (Exception e) {
                    fileCallback = null;
                    callback.onReceiveValue(null);
                }
                return true;
            }
        });
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
        ReminderReceiver.schedule(this);
    }

    private Intent documentPicker() {
        cameraOffered = false;
        Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.setType("*/*");
        return i;
    }

    /** Gallery / files, plus the camera writing straight into PhotoProvider's capture file. */
    private Intent photoChooser() {
        Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
        pick.addCategory(Intent.CATEGORY_OPENABLE);
        pick.setType("image/*");
        Intent chooser = Intent.createChooser(pick, null);
        File capture = PhotoProvider.captureFile(this);
        capture.delete();
        Intent cam = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        cam.putExtra(MediaStore.EXTRA_OUTPUT, PhotoProvider.CAPTURE_URI);
        cam.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
        cam.setClipData(ClipData.newRawUri("", PhotoProvider.CAPTURE_URI));
        chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{cam});
        cameraOffered = true;
        return chooser;
    }

    private boolean isDark() {
        int mode = getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK;
        return mode == Configuration.UI_MODE_NIGHT_YES;
    }

    @Override
    public void onConfigurationChanged(Configuration config) {
        super.onConfigurationChanged(config);
        callJs("window.walletTheme && window.walletTheme(" + isDark() + ")");
    }

    @Override
    protected void onPause() {
        super.onPause();
        callJs("window.walletPause && window.walletPause()");
    }

    @Override
    protected void onResume() {
        super.onResume();
        callJs("window.walletResume && window.walletResume()");
    }

    @Override
    public void onBackPressed() {
        web.evaluateJavascript("(window.walletBack && window.walletBack()) ? 'y' : 'n'", new ValueCallback<String>() {
            @Override
            public void onReceiveValue(String value) {
                if (!"\"y\"".equals(value)) MainActivity.super.onBackPressed();
            }
        });
    }

    private void callJs(final String js) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                if (web != null) web.evaluateJavascript(js, null);
            }
        });
    }

    static String readFile(File f) throws Exception {
        return new String(readBytes(f), StandardCharsets.UTF_8);
    }

    static byte[] readBytes(File f) throws Exception {
        InputStream in = new FileInputStream(f);
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        } finally {
            in.close();
        }
    }

    private static boolean safeId(String id) {
        return id != null && id.matches("[A-Za-z0-9_-]{1,64}");
    }

    private File photoFile(String id) {
        File dir = new File(getFilesDir(), "photos");
        dir.mkdirs();
        return new File(dir, id + ".jpg");
    }

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        if (request == REQ_OPEN) {
            if (fileCallback != null) {
                Uri[] picked = WebChromeClient.FileChooserParams.parseResult(result, data);
                File capture = PhotoProvider.captureFile(this);
                if (result == RESULT_OK && (picked == null || picked.length == 0) && cameraOffered && capture.length() > 0) {
                    picked = new Uri[]{PhotoProvider.CAPTURE_URI};
                }
                fileCallback.onReceiveValue(picked);
                fileCallback = null;
            }
        } else if (request == REQ_SAVE) {
            boolean ok = false;
            if (result == RESULT_OK && data != null && data.getData() != null && pendingBytes != null) {
                try {
                    OutputStream out = getContentResolver().openOutputStream(data.getData());
                    try {
                        out.write(pendingBytes);
                        ok = true;
                    } finally {
                        out.close();
                    }
                } catch (Exception e) {
                    ok = false;
                }
            }
            pendingBytes = null;
            callJs("window.walletSaved && window.walletSaved(" + ok + ")");
        } else {
            super.onActivityResult(request, result, data);
        }
    }

    /** Methods the page calls as window.AndroidWallet.*  */
    public class Bridge {
        @JavascriptInterface
        public String load() {
            File main = new File(getFilesDir(), DATA);
            File prev = new File(getFilesDir(), PREV);
            try {
                if (main.exists()) return readFile(main);
                if (prev.exists()) return readFile(prev);
            } catch (Exception e) {
                try {
                    if (prev.exists()) return readFile(prev);
                } catch (Exception ignored) {
                    // fall through to empty data
                }
            }
            return "";
        }

        @JavascriptInterface
        public synchronized boolean save(String json) {
            File dir = getFilesDir();
            File tmp = new File(dir, DATA + ".tmp");
            File main = new File(dir, DATA);
            File prev = new File(dir, PREV);
            try {
                FileOutputStream out = new FileOutputStream(tmp);
                try {
                    out.write(json.getBytes(StandardCharsets.UTF_8));
                    out.getFD().sync();
                } finally {
                    out.close();
                }
                if (main.exists()) {
                    if (prev.exists()) prev.delete();
                    main.renameTo(prev);
                }
                return tmp.renameTo(main);
            } catch (Exception e) {
                return false;
            }
        }

        @JavascriptInterface
        public boolean isDark() {
            return MainActivity.this.isDark();
        }

        @JavascriptInterface
        public void saveFile(final String name, final String base64, final String mime) {
            try {
                pendingBytes = Base64.decode(base64, Base64.DEFAULT);
            } catch (Exception e) {
                pendingBytes = null;
                callJs("window.walletSaved && window.walletSaved(false)");
                return;
            }
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    i.addCategory(Intent.CATEGORY_OPENABLE);
                    i.setType(mime);
                    i.putExtra(Intent.EXTRA_TITLE, name);
                    try {
                        startActivityForResult(i, REQ_SAVE);
                    } catch (Exception e) {
                        pendingBytes = null;
                        callJs("window.walletSaved && window.walletSaved(false)");
                    }
                }
            });
        }

        @JavascriptInterface
        public void setReminders(String json) {
            SharedPreferences prefs = ReminderReceiver.prefs(MainActivity.this);
            prefs.edit().putString("plan", json).apply();
            ReminderReceiver.schedule(MainActivity.this);
            boolean on = json != null && json.contains("\"on\":true");
            if (on && Build.VERSION.SDK_INT >= 33 && !prefs.getBoolean("askedNotify", false)
                    && checkSelfPermission(NOTIFY_PERMISSION) != PackageManager.PERMISSION_GRANTED) {
                prefs.edit().putBoolean("askedNotify", true).apply();
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() {
                        requestPermissions(new String[]{NOTIFY_PERMISSION}, REQ_NOTIFY);
                    }
                });
            }
        }

        @JavascriptInterface
        public void updateWidget(String json) {
            ReminderReceiver.prefs(MainActivity.this).edit().putString("widget", json).apply();
            WalletWidget.refresh(MainActivity.this);
        }

        @JavascriptInterface
        public boolean savePhoto(String id, String base64) {
            if (!safeId(id)) return false;
            try {
                FileOutputStream out = new FileOutputStream(photoFile(id));
                try {
                    out.write(Base64.decode(base64, Base64.DEFAULT));
                } finally {
                    out.close();
                }
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        @JavascriptInterface
        public String loadPhoto(String id) {
            if (!safeId(id)) return "";
            File f = photoFile(id);
            if (!f.exists()) return "";
            try {
                return "data:image/jpeg;base64," + Base64.encodeToString(readBytes(f), Base64.NO_WRAP);
            } catch (Exception e) {
                return "";
            }
        }

        @JavascriptInterface
        public void deletePhoto(String id) {
            if (safeId(id)) photoFile(id).delete();
        }
    }
}
