package cn.superjlu.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.widget.Toast;

/** External links retain normal system routing; browser selection is disabled. */
final class BrowserPicker {
    private final Activity activity;

    BrowserPicker(Activity activity) { this.activity = activity; }

    void open(Uri uri) {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        if (uri == null || !("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))) {
            Toast.makeText(activity, R.string.browser_unsupported, Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            activity.startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException | SecurityException error) {
            Toast.makeText(activity, R.string.browser_open_failed, Toast.LENGTH_LONG).show();
        }
    }

    /**
     * TODO: Implement reliable browser-only selection and explicit opt-in memory.
     * Keep superjlu://browser-settings as a reserved interface while UI is disabled.
     * Failure reports, scope and acceptance criteria: docs/TODO-browser-selection.md.
     */
    void showSettings() {
        if (!activity.isFinishing() && !activity.isDestroyed()) {
            Toast.makeText(activity, R.string.browser_disabled, Toast.LENGTH_SHORT).show();
        }
    }
}
