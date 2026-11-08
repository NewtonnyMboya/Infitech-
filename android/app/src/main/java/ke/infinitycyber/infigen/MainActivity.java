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

import java.util.ArrayList;
import java.util.List;

public final class MainActivity extends Activity {
    private WebView webView;
    private boolean backRequestPending = false;
    // Keep print WebViews alive while Android's print spooler consumes their adapters.
    private final List<WebView> printViews = new ArrayList<>();

    private final class AndroidPrintBridge {
        @JavascriptInterface
        public void printDocument(String title, String html) {
            if (title == null || html == null || html.length() > 1_000_000) return;
            runOnUiThread(() -> startPrintJob(title, html));
        }
    }

    private void startPrintJob(String title, String html) {
        if (isFinishing() || isDestroyed()) return;
        WebView printView = new WebView(this);
        WebSettings printSettings = printView.getSettings();
        printSettings.setJavaScriptEnabled(false);
        printSettings.setAllowFileAccess(false);
        printSettings.setAllowContentAccess(false);
        printViews.add(printView);
        printView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                PrintManager manager = (PrintManager) getSystemService(Context.PRINT_SERVICE);
                if (manager == null) return;
                String jobName = title.trim().isEmpty() ? "InfiGen document" : title;
                manager.print(jobName, view.createPrintDocumentAdapter(jobName),
                    new PrintAttributes.Builder().build());
            }
        });
        printView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        webView.setWebViewClient(new WebViewClient());
        WebSettings settings = webView.getSettings();

        // The app UI is bundled locally. The bridge only opens Android's print UI.
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
