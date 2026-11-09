package ke.infinitycyber.infigen;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.os.Bundle;
import android.print.PrintAttributes;
import android.print.PrintManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

public final class MainActivity extends Activity {
    private WebView webView;
    private boolean backRequestPending = false;
    // Retain print WebViews until the Android print spooler has consumed their adapters.
    private final List<WebView> printViews = new ArrayList<>();

    private final class AndroidPrintBridge {
        @JavascriptInterface
        public boolean isAvailable() {
            return true;
        }

        @JavascriptInterface
        public void printDocument(String title, String html) {
            if (title == null || html == null || html.length() > 1_000_000) {
                notifyPrintStatus("Print request rejected: invalid or oversized document.");
                return;
            }
            runOnUiThread(() -> startPrintJob(title, html));
        }
    }

    private void notifyPrintStatus(String message) {
        runOnUiThread(() -> {
            if (webView != null && !isFinishing() && !isDestroyed()) {
                String safe = message.replace("\\", "\\\\").replace("'", "\\'");
                webView.evaluateJavascript(
                    "if(typeof window.onNativePrintStatus==='function'){window.onNativePrintStatus('" + safe + "');}",
                    null
                );
            }
        });
    }

    private void startPrintJob(String title, String html) {
        if (isFinishing() || isDestroyed()) {
            notifyPrintStatus("Print unavailable: InfiGen is closing.");
            return;
        }
        try {
            PrintManager manager = (PrintManager) getSystemService(Context.PRINT_SERVICE);
            if (manager == null) {
                notifyPrintStatus("Android print service is unavailable on this device.");
                Toast.makeText(this, "Android print service unavailable", Toast.LENGTH_LONG).show();
                return;
            }

            WebView printView = new WebView(this);
            WebSettings printSettings = printView.getSettings();
            printSettings.setJavaScriptEnabled(false);
            printSettings.setAllowFileAccess(false);
            printSettings.setAllowContentAccess(false);
            printViews.add(printView);
            final boolean[] submitted = {false};
            printView.setWebViewClient(new WebViewClient() {
                @Override
                public void onPageFinished(WebView view, String url) {
                    if (submitted[0]) return;
                    submitted[0] = true;
                    try {
                        String jobName = title.trim().isEmpty() ? "InfiGen document" : title;
                        manager.print(jobName, view.createPrintDocumentAdapter(jobName),
                            new PrintAttributes.Builder().build());
                        notifyPrintStatus("Android print interface requested. Select a printer or Save as PDF.");
                    } catch (RuntimeException ex) {
                        notifyPrintStatus("Could not start Android printing: " + ex.getClass().getSimpleName());
                        Toast.makeText(MainActivity.this, "Could not start Android printing", Toast.LENGTH_LONG).show();
                    }
                }
            });
            printView.loadDataWithBaseURL("https://infigen.local/", html, "text/html", "UTF-8", null);
            notifyPrintStatus("Preparing document for Android printing…");
        } catch (RuntimeException ex) {
            notifyPrintStatus("Android printing failed: " + ex.getClass().getSimpleName());
            Toast.makeText(this, "Android printing failed", Toast.LENGTH_LONG).show();
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        webView.setWebViewClient(new WebViewClient());
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setDatabaseEnabled(false);
        webView.addJavascriptInterface(new AndroidPrintBridge(), "AndroidPrint");
        setContentView(webView);
        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl("file:///android_asset/index.html");
        }
    }

    @Override
    public void onBackPressed() {
        if (webView == null || backRequestPending) return;
        backRequestPending = true;
        webView.evaluateJavascript(
            "(function(){return typeof window.handleAndroidBack==='function' && window.handleAndroidBack();})()",
            result -> {
                backRequestPending = false;
                if (isFinishing() || isDestroyed()) return;
                if ("true".equals(result)) return;
                if (webView.canGoBack()) webView.goBack();
                else showExitConfirmation();
            }
        );
    }

    private void showExitConfirmation() {
        new AlertDialog.Builder(this)
            .setTitle("Exit InfiGen?")
            .setMessage("Your demo session is saved on this device. You can return to it when you reopen the app.")
            .setNegativeButton("Stay", (dialog, which) -> dialog.dismiss())
            .setPositiveButton("Exit", (dialog, which) -> finish())
            .show();
    }

    @Override
    protected void onPause() {
        if (webView != null) webView.onPause();
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) webView.onResume();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) webView.saveState(outState);
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.stopLoading();
            webView.destroy();
            webView = null;
        }
        for (WebView view : printViews) {
            view.stopLoading();
            view.destroy();
        }
        printViews.clear();
        super.onDestroy();
    }
}
