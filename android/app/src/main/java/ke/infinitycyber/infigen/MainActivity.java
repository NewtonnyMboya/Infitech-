package ke.infinitycyber.infigen;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public final class MainActivity extends Activity {
    private WebView webView;
    private boolean backRequestPending = false;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        webView = new WebView(this);
        webView.setWebViewClient(new WebViewClient());
        WebSettings settings = webView.getSettings();

        // JavaScript and DOM storage are enabled only for the bundled local app.
        // No JavaScript bridge is exposed; file/content access remains disabled.
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setDatabaseEnabled(false);

        setContentView(webView);
        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl("file:///android_asset/index.html");
        }
    }

    @Override
    public void onBackPressed() {
        if (webView == null || backRequestPending) return;
        backRequestPending = true;
        // First let the local app close its menu or return from the current section.
        webView.evaluateJavascript(
            "(function(){return typeof window.handleAndroidBack==='function' && window.handleAndroidBack();})()",
            result -> {
                backRequestPending = false;
                if (isFinishing() || isDestroyed()) return;
                if ("true".equals(result)) return;
                if (webView.canGoBack()) {
                    webView.goBack();
                } else {
                    showExitConfirmation();
                }
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
        super.onDestroy();
    }
}
