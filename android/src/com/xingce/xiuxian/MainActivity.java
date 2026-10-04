package com.xingce.xiuxian;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.Window;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/**
 * 行测修仙传 · 平板 App。
 * 电脑上的修仙传开了局域网模式后，这个 App 在同一个 Wi-Fi 里找到它（或手动输地址），全屏打开——没有浏览器的地址栏、工具栏。
 * 记住上次的地址，下次直接进；连不上就回到「寻找洞府」页。数据仍然只在电脑上。
 */
public class MainActivity extends Activity {
    static final int[] PORTS = {8765, 8766, 8767, 8768};
    static final String CONNECT = "file:///android_asset/connect.html";
    static final int PICK = 7;

    WebView web;
    SharedPreferences prefs;
    ValueCallback<Uri[]> pending;
    long lastBack;
    volatile boolean scanning;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("xiuxian", MODE_PRIVATE);
        Window w = getWindow();
        w.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);       // 做题时不息屏
        w.setStatusBarColor(Color.parseColor("#0e1412"));
        w.setNavigationBarColor(Color.parseColor("#0e1412"));
        if (Build.VERSION.SDK_INT >= 28) {
            w.getAttributes().layoutInDisplayCutoutMode = WindowManager.LayoutParams.LAYOUT_IN_DISPLAY_CUTOUT_MODE_SHORT_EDGES;
        }

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0e1412"));
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);       // 背景音乐、音效
        s.setAllowFileAccess(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setTextZoom(100);                                  // 不跟系统字体缩放走样
        s.setUserAgentString(s.getUserAgentString() + " XingceApp/" + BuildInfo.VERSION);
        CookieManager.getInstance().setAcceptCookie(true);
        web.addJavascriptInterface(new Bridge(), "XC");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                Uri u = r.getUrl();
                String home = prefs.getString("url", "");
                if ("file".equals(u.getScheme()) || (!home.isEmpty() && u.toString().startsWith(home))) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception e) { /* 没有能打开的应用 */ }
                return true;                                  // 外部链接（GitHub 等）交给系统浏览器
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest r, WebResourceError e) {
                if (r.isForMainFrame() && !r.getUrl().toString().startsWith("file:")) {
                    showConnect("连不上 " + r.getUrl().getHost() + "：电脑开着吗？修仙传在运行吗？");
                }
            }

            @Override
            public void onPageFinished(WebView v, String url) {
                CookieManager.getInstance().flush();          // 口令 cookie 立刻存下，下次不用再输
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> cb, FileChooserParams p) {
                if (pending != null) pending.onReceiveValue(null);
                pending = cb;
                try {
                    startActivityForResult(p.createIntent(), PICK);   // 导入截图、成绩单
                } catch (Exception e) {
                    pending = null;
                    return false;
                }
                return true;
            }
        });

        String url = prefs.getString("url", "");
        if (state != null) web.restoreState(state);
        else if (url.isEmpty()) showConnect("");
        else web.loadUrl(url);
    }

    void showConnect(String msg) {
        web.loadUrl(CONNECT + "#" + Uri.encode(msg));
    }

    @Override
    protected void onActivityResult(int req, int res, Intent data) {
        if (req == PICK && pending != null) {
            pending.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(res, data));
            pending = null;
        }
        super.onActivityResult(req, res, data);
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (focus) immersive();
    }

    @SuppressWarnings("deprecation")
    void immersive() {                                        // 隐藏状态栏、导航栏，从边缘滑一下临时出现
        if (Build.VERSION.SDK_INT >= 30) {
            WindowInsetsController c = getWindow().getInsetsController();
            if (c != null) {
                c.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                c.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
        } else {
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                    | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                    | View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                    | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    public boolean onKeyDown(int code, KeyEvent e) {
        if (code != KeyEvent.KEYCODE_BACK) return super.onKeyDown(code, e);
        // 返回键：先让网页处理（关弹窗、回洞府）；网页说没得退了，再按一次退出
        web.evaluateJavascript("(function(){try{return !!(window.xcBack&&xcBack())}catch(e){return false}})()", r -> {
            if ("true".equals(r)) return;
            if (web.getUrl() != null && web.getUrl().startsWith("file:") && web.canGoBack()) { web.goBack(); return; }
            long now = System.currentTimeMillis();
            if (now - lastBack < 2000) finish();
            else { lastBack = now; Toast.makeText(this, "再按一次退出修仙传", Toast.LENGTH_SHORT).show(); }
        });
        return true;
    }

    // ------------------------------------------------------------ 给网页用的接口（window.XC）
    class Bridge {
        @JavascriptInterface
        public String version() { return BuildInfo.VERSION; }

        @JavascriptInterface
        public String saved() { return prefs.getString("url", ""); }

        /** 打开一个地址（会记住）：192.168.1.5、192.168.1.5:8765、http://… 都行 */
        @JavascriptInterface
        public void open(String raw) {
            String u = normalize(raw);
            if (u.isEmpty()) return;
            prefs.edit().putString("url", u).apply();
            runOnUiThread(() -> web.loadUrl(u));
        }

        /** 换一台电脑：忘掉地址，回到寻找页 */
        @JavascriptInterface
        public void reset() {
            prefs.edit().remove("url").apply();
            runOnUiThread(() -> showConnect(""));
        }

        /** 在这个 Wi-Fi 里找开着局域网模式的修仙传：找到一个就调网页的 xcFound(url, 名字)，找完调 xcScanDone() */
        @JavascriptInterface
        public void scan() {
            if (scanning) return;
            scanning = true;
            new Thread(() -> {
                try { doScan(); } finally {
                    scanning = false;
                    runOnUiThread(() -> web.evaluateJavascript("window.xcScanDone&&xcScanDone()", null));
                }
            }).start();
        }
    }

    static String normalize(String raw) {
        String u = raw == null ? "" : raw.trim();
        if (u.isEmpty()) return "";
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://" + u;
        try {
            URL p = new URL(u);
            int port = p.getPort() > 0 ? p.getPort() : (u.startsWith("https") ? 443 : 8765);
            return p.getProtocol() + "://" + p.getHost() + ":" + port + "/";
        } catch (Exception e) {
            return "";
        }
    }

    void doScan() {
        List<String> prefixes = new ArrayList<>();
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (a instanceof Inet4Address && a.isSiteLocalAddress()) {
                        String ip = a.getHostAddress();
                        String pre = ip.substring(0, ip.lastIndexOf('.') + 1);
                        if (!prefixes.contains(pre)) prefixes.add(pre);
                    }
                }
            }
        } catch (Exception e) { /* 没网卡信息就只能手动输 */ }
        ExecutorService pool = Executors.newFixedThreadPool(48);
        for (String pre : prefixes) {
            for (int i = 1; i < 255; i++) {
                for (int port : PORTS) {
                    final String base = "http://" + pre + i + ":" + port + "/";
                    pool.execute(() -> probe(base));
                }
            }
        }
        pool.shutdown();
        try { pool.awaitTermination(40, TimeUnit.SECONDS); } catch (InterruptedException e) { /* 算了 */ }
    }

    void probe(String base) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + "lan/ping").openConnection();
            c.setConnectTimeout(350);
            c.setReadTimeout(1200);
            if (c.getResponseCode() != 200) return;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] b = new byte[2048];
            int n;
            while ((n = in.read(b)) > 0 && buf.size() < 8192) buf.write(b, 0, n);
            JSONObject j = new JSONObject(buf.toString("UTF-8"));
            if (!"xingce-rpg".equals(j.optString("app"))) return;
            String js = "window.xcFound&&xcFound(" + JSONObject.quote(base) + "," + JSONObject.quote(j.optString("name")) + ")";
            runOnUiThread(() -> web.evaluateJavascript(js, null));
        } catch (Exception e) {
            // 这个地址没有修仙传
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
