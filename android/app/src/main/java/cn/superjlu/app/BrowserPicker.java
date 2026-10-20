package cn.superjlu.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.graphics.drawable.Drawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;

/** System web chooser with a separately configured, app-local default. */
final class BrowserPicker {
    interface CandidateQuery {
        List<ResolveInfo> query(Intent intent, int flags);
    }

    static final int QUERY_FLAGS = PackageManager.MATCH_ALL | PackageManager.MATCH_DEFAULT_ONLY
            | PackageManager.GET_RESOLVED_FILTER;
    private static final String[] WEB_TYPES = {null, "text/html", "application/xhtml+xml"};
    private static final String MODE_ASK = "ask";
    private static final String MODE_SYSTEM = "system";
    private static final String MODE_APP = "app";
    private final Activity activity;
    private final CandidateQuery query;
    private final SharedPreferences preferences;
    private AlertDialog settingsDialog;

    BrowserPicker(Activity activity) {
        this(activity, (intent, flags) -> activity.getPackageManager().queryIntentActivities(intent, flags));
    }

    BrowserPicker(Activity activity, CandidateQuery query) {
        this.activity = activity;
        this.query = query;
        // Separate from all old experimental preference formats; no URL, MIME or ticket is saved.
        this.preferences = activity.getSharedPreferences("browser-preferences-v1", Activity.MODE_PRIVATE);
    }

    void open(Uri uri) {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        if (uri == null || !("https".equals(uri.getScheme()) || "http".equals(uri.getScheme()))) {
            Toast.makeText(activity, R.string.browser_unsupported, Toast.LENGTH_SHORT).show();
            return;
        }
        try {
            String mode = preferences.getString("mode", MODE_ASK);
            if (MODE_SYSTEM.equals(mode)) {
                try {
                    activity.startActivity(webIntent(uri, null));
                    return;
                } catch (ActivityNotFoundException | SecurityException unavailable) {
                    resetUnavailableDefault();
                }
            }
            List<Intent> targets = findTargets(uri);
            if (MODE_APP.equals(mode)) {
                String preferred = preferences.getString("package", null);
                Intent target = null;
                for (Intent candidate : targets) {
                    if (candidate.getComponent().getPackageName().equals(preferred)) {
                        target = candidate;
                        break;
                    }
                }
                if (target != null) {
                    try {
                        activity.startActivity(target);
                        return;
                    } catch (ActivityNotFoundException | SecurityException unavailable) {
                        // An app may disappear or become unavailable after discovery.
                        targets.remove(target);
                    }
                }
                resetUnavailableDefault();
            }
            Intent view = targets.isEmpty() ? webIntent(uri, null) : targets.get(0);
            Intent chooser = Intent.createChooser(view, activity.getString(R.string.browser_chooser_title));
            if (targets.size() > 1) {
                // INITIAL_INTENTS is limited to two additions on Android 10+. Alternate payloads
                // retain the exact component, URL and MIME that matched each browser.
                chooser.putExtra(Intent.EXTRA_ALTERNATE_INTENTS,
                        targets.subList(1, targets.size()).toArray(new Intent[0]));
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                // This belongs on ACTION_CHOOSER, not its nested ACTION_VIEW.
                // Keep the panel visible even if the system finds only one candidate.
                chooser.putExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE, false);
            }
            activity.startActivity(chooser);
        } catch (ActivityNotFoundException | SecurityException error) {
            Toast.makeText(activity, R.string.browser_open_failed, Toast.LENGTH_LONG).show();
        }
    }

    private void resetUnavailableDefault() {
        preferences.edit().putString("mode", MODE_ASK).remove("package").apply();
        Toast.makeText(activity, R.string.browser_default_unavailable, Toast.LENGTH_LONG).show();
    }

    private List<Intent> findTargets(Uri uri) {
        LinkedHashMap<String, Intent> targets = new LinkedHashMap<>();
        for (String type : WEB_TYPES) {
            Intent request = webIntent(uri, type);
            List<ResolveInfo> matches;
            try {
                matches = query.query(request, QUERY_FLAGS);
            } catch (SecurityException denied) {
                // Query restrictions must not prevent the system chooser fallback.
                continue;
            }
            if (matches == null) continue;
            for (ResolveInfo match : matches) {
                if (!isGenericWebHandler(match, uri.getScheme())) continue;
                ActivityInfo info = match.activityInfo;
                if (activity.getPackageName().equals(info.packageName)) continue;
                if (info.permission != null && !info.permission.isEmpty()
                        && activity.checkSelfPermission(info.permission) != PackageManager.PERMISSION_GRANTED) continue;
                // Prefer an untyped web entry over an HTML-only entry from the same app.
                targets.putIfAbsent(info.packageName, new Intent(request)
                        .setComponent(new ComponentName(info.packageName, info.name)));
            }
        }
        return new ArrayList<>(targets.values());
    }

    private static Intent webIntent(Uri uri, String type) {
        // setType() alone would erase the URL; keep both fields together.
        return new Intent(Intent.ACTION_VIEW).setDataAndType(uri, type)
                .addCategory(Intent.CATEGORY_BROWSABLE);
    }

    private static boolean isGenericWebHandler(ResolveInfo match, String scheme) {
        if (match == null || match.activityInfo == null) return false;
        ActivityInfo info = match.activityInfo;
        if (!info.exported || !info.enabled || info.packageName == null || info.packageName.isEmpty()
                || info.name == null || info.name.isEmpty()) return false;
        ApplicationInfo app = info.applicationInfo;
        if (app == null || !app.enabled || (app.flags & ApplicationInfo.FLAG_SUSPENDED) != 0) return false;
        // An HTML file viewer or a domain-specific deep link is not a generic web browser.
        // Inspect the matched network filter rather than trusting a MIME match alone.
        IntentFilter filter = match.filter;
        if (filter != null) {
            return filter.hasAction(Intent.ACTION_VIEW) && filter.hasCategory(Intent.CATEGORY_BROWSABLE)
                    && filter.hasDataScheme(scheme) && filter.countDataAuthorities() == 0
                    && filter.countDataPaths() == 0 && filter.countDataSchemeSpecificParts() == 0;
        }
        // Without a public matched filter we cannot establish generic network-page support.
        return false;
    }

    void showSettings() {
        if (activity.isFinishing() || activity.isDestroyed()) return;
        close();
        PackageManager pm = activity.getPackageManager();
        List<BrowserChoice> choices = new ArrayList<>();
        choices.add(new BrowserChoice(MODE_ASK, null, activity.getString(R.string.browser_always_ask),
                activity.getDrawable(android.R.drawable.ic_menu_help)));
        choices.add(new BrowserChoice(MODE_SYSTEM, null, activity.getString(R.string.browser_follow_system),
                activity.getDrawable(android.R.drawable.ic_menu_view)));
        // A neutral network URL only queries local capability declarations; it is never opened.
        for (Intent target : findTargets(Uri.parse("https://example.org/"))) {
            String packageName = target.getComponent().getPackageName();
            CharSequence label = packageName;
            Drawable icon = pm.getDefaultActivityIcon();
            try {
                ApplicationInfo info = pm.getApplicationInfo(packageName, 0);
                label = info.loadLabel(pm);
                icon = info.loadIcon(pm);
            } catch (PackageManager.NameNotFoundException | SecurityException unavailable) {
                // Keep the discovered candidate identifiable if its label cannot be read.
            }
            choices.add(new BrowserChoice(MODE_APP, packageName, label, icon));
        }
        String mode = preferences.getString("mode", MODE_ASK);
        String packageName = preferences.getString("package", null);
        final int[] selection = {0};
        boolean currentFound = false;
        for (int i = 0; i < choices.size(); i++) {
            BrowserChoice choice = choices.get(i);
            if (choice.mode.equals(mode) && (!MODE_APP.equals(mode) || choice.packageName.equals(packageName))) {
                selection[0] = i;
                currentFound = true;
                break;
            }
        }
        String message = activity.getString(R.string.browser_settings_hint);
        if (MODE_APP.equals(mode) && !currentFound) message = activity.getString(R.string.browser_saved_missing) + "\n\n" + message;
        int iconSize = Math.round(32 * activity.getResources().getDisplayMetrics().density);
        ArrayAdapter<BrowserChoice> adapter = new ArrayAdapter<BrowserChoice>(activity,
                android.R.layout.simple_list_item_single_choice, choices) {
            @Override public View getView(int position, View recycled, ViewGroup parent) {
                TextView row = (TextView) super.getView(position, recycled, parent);
                Drawable icon = getItem(position).icon;
                icon.setBounds(0, 0, iconSize, iconSize);
                row.setCompoundDrawablesRelative(icon, null, null, null);
                row.setCompoundDrawablePadding(iconSize / 3);
                return row;
            }
        };
        // AlertDialog's setMessage hides its choice list on Android. Keep explanatory text
        // in the title area so the radio list remains visible and fully scrollable.
        LinearLayout heading = new LinearLayout(activity);
        heading.setOrientation(LinearLayout.VERTICAL);
        int padding = Math.round(24 * activity.getResources().getDisplayMetrics().density);
        heading.setPadding(padding, padding, padding, padding / 2);
        TextView title = new TextView(activity);
        title.setTextAppearance(android.R.style.TextAppearance_Material_Title);
        title.setText(R.string.browser_settings_title);
        heading.addView(title);
        TextView explanation = new TextView(activity);
        explanation.setTextAppearance(android.R.style.TextAppearance_Material_Body1);
        explanation.setPadding(0, padding / 3, 0, 0);
        explanation.setText(message);
        heading.addView(explanation);
        AlertDialog dialog = new AlertDialog.Builder(activity)
                .setCustomTitle(heading)
                .setSingleChoiceItems(adapter, selection[0], (d, which) -> selection[0] = which)
                .setPositiveButton(R.string.browser_save_default, (d, which) -> {
                    BrowserChoice choice = choices.get(selection[0]);
                    SharedPreferences.Editor edit = preferences.edit().putString("mode", choice.mode);
                    if (MODE_APP.equals(choice.mode)) edit.putString("package", choice.packageName);
                    else edit.remove("package");
                    edit.apply();
                })
                .setNegativeButton(android.R.string.cancel, null)
                .create();
        dialog.setOnDismissListener(d -> { if (settingsDialog == dialog) settingsDialog = null; });
        settingsDialog = dialog;
        dialog.show();
    }

    void close() {
        if (settingsDialog != null) settingsDialog.dismiss();
        settingsDialog = null;
    }

    private static final class BrowserChoice {
        final String mode;
        final String packageName;
        final CharSequence label;
        final Drawable icon;

        BrowserChoice(String mode, String packageName, CharSequence label, Drawable icon) {
            this.mode = mode;
            this.packageName = packageName;
            this.label = label;
            this.icon = icon;
        }

        @Override public String toString() { return label.toString(); }
    }
}
