package com.infinity.moneytransfer

import android.annotation.SuppressLint
import android.app.Activity
import android.os.Bundle
import android.content.Intent
import android.net.Uri
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.webkit.WebResourceRequest

class MainActivity : Activity() {
    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.allowFileAccess = false
        web.settings.allowContentAccess = false
        web.webChromeClient = WebChromeClient()
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val uri: Uri = request.url
                if (uri.scheme == "https" && (uri.host == "www.skrill.com" || uri.host == "skrill.com")) {
                    startActivity(Intent(Intent.ACTION_VIEW, uri))
                    return true
                }
                return uri.scheme != "file" && uri.scheme != "https"
            }
        }
        web.loadUrl("file:///android_asset/index.html")
        setContentView(web)
    }
}
