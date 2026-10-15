package io.github.runaasahi.jlutoolkit;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

public class MainActivity extends Activity {
    private WebView web;
    private final Handler main = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setContentView(R.layout.activity_main);
        web = findViewById(R.id.web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                return handle(req.getUrl());
            }
            @Override
            public void onPageFinished(WebView v, String url) {
                findViewById(R.id.splash).setVisibility(View.GONE);
                web.setVisibility(View.VISIBLE);
            }
        });
        View banner = findViewById(R.id.banner);
        banner.setOnClickListener(v -> v.setVisibility(View.GONE));

        new Thread(() -> {
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                String url = Python.getInstance().getModule("jlu_android")
                        .callAttr("start", getFilesDir().getAbsolutePath()).toString();
                main.post(() -> web.loadUrl(url));
            } catch (Throwable t) {
                main.post(() -> ((TextView) findViewById(R.id.splash_msg))
                        .setText("启动失败：" + t));
            }
        }, "jlu-start").start();

        new Thread(() -> {
            boolean ok;
            try {
                if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                ok = Python.getInstance().getModule("jlu_android")
                        .callAttr("campus_reachable").toBoolean();
            } catch (Throwable t) { ok = false; }
            if (!ok) main.post(() -> banner.setVisibility(View.VISIBLE));
        }, "jlu-netcheck").start();
    }

    /** 本机地址留在 WebView 内，其余链接交给系统浏览器。 */
    private boolean handle(Uri u) {
        String h = u.getHost();
        if ("127.0.0.1".equals(h) || "localhost".equals(h)) return false;
        try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) {}
        return true;
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
