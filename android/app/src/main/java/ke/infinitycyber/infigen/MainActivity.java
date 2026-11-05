package ke.infinitycyber.infigen;

import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

public final class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        WebView view = new WebView(this);
        view.setWebViewClient(new WebViewClient());
        WebSettings settings = view.getSettings();
        // JavaScript powers only the bundled, local demo interface. No JavaScript
        // bridge is exposed to web content, and file/content access stays disabled.
        settings.setJavaScriptEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setDomStorageEnabled(false);
        view.loadUrl("file:///android_asset/index.html");
        setContentView(view);
    }
}