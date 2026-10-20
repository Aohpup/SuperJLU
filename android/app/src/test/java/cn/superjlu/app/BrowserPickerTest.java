package cn.superjlu.app;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.ActivityInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Looper;
import org.junit.Before;
import org.junit.After;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.Shadows;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowToast;
import org.robolectric.shadows.ShadowAlertDialog;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {28, 35})
public class BrowserPickerTest {
    public static class CaptureActivity extends Activity {
        Intent opened;
        boolean missing;
        boolean denied;
        ComponentName unavailableComponent;
        @Override public void startActivity(Intent intent) {
            if (missing) throw new ActivityNotFoundException();
            if (denied) throw new SecurityException();
            if (unavailableComponent != null && unavailableComponent.equals(intent.getComponent())) {
                throw new ActivityNotFoundException();
            }
            opened = intent;
        }
        @Override public void startActivityForResult(Intent intent, int code) {
            fail("Disabled feature must not open an application picker");
        }
    }
    private CaptureActivity activity;
    private BrowserPicker browsers;
    private Map<String, List<ResolveInfo>> matches;
    private List<Intent> queries;
    private List<Integer> queryFlags;
    private BrowserPicker.CandidateQuery candidateQuery;

    @Before public void setup() {
        activity = Robolectric.buildActivity(CaptureActivity.class).setup().get();
        matches = new HashMap<>();
        queries = new ArrayList<>();
        queryFlags = new ArrayList<>();
        candidateQuery = (request, flags) -> {
            queries.add(new Intent(request));
            queryFlags.add(flags);
            return matches.getOrDefault(request.getType(), Collections.emptyList());
        };
        browsers = new BrowserPicker(activity, candidateQuery);
    }

    @After public void cleanup() { browsers.close(); }

    @Test public void externalLinksIgnoreAllExperimentalSavedBrowserPreferences() {
        activity.getSharedPreferences("external-browser", 0).edit()
                .putString("selected", "test.old").putString("selected_component", "test.old/.Browser")
                .putString("selected_package", "test.old").commit();
        Uri uri = Uri.parse("https://example.invalid/page?value=1");
        browsers.open(uri);
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals("选择浏览器打开", activity.opened.getStringExtra(Intent.EXTRA_TITLE));
        Intent view = activity.opened.getParcelableExtra(Intent.EXTRA_INTENT);
        assertNotNull(view);
        assertEquals(Intent.ACTION_VIEW, view.getAction());
        assertEquals(uri, view.getData());
        assertTrue(view.hasCategory(Intent.CATEGORY_BROWSABLE));
        assertNull(view.getPackage());
        assertNull(view.getComponent());
        assertNull(view.getType());
        assertNull(view.getSelector());
        assertNull(activity.opened.getPackage());
        assertNull(activity.opened.getComponent());
        assertNull(activity.opened.getType());
        assertNull(activity.opened.getData());
        // No callback or preselected apps: merely starting an app must never save a preference.
        assertFalse(activity.opened.hasExtra(Intent.EXTRA_CHOSEN_COMPONENT_INTENT_SENDER));
        assertFalse(activity.opened.hasExtra(Intent.EXTRA_INITIAL_INTENTS));
        assertEquals("test.old", activity.getSharedPreferences("external-browser", 0)
                .getString("selected", null));
    }

    @Test public void singleCandidateAutoLaunchIsDisabledOnSupportedAndroidVersions() {
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            assertTrue(activity.opened.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
            assertFalse(activity.opened.getBooleanExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE, true));
        } else {
            assertFalse(activity.opened.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
        }
        Intent view = activity.opened.getParcelableExtra(Intent.EXTRA_INTENT);
        assertFalse(view.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
    }

    @Test public void httpLinksKeepTheirOriginalAddress() {
        Uri uri = Uri.parse("http://example.invalid/path?one=1&two=2#section");
        browsers.open(uri);
        Intent view = activity.opened.getParcelableExtra(Intent.EXTRA_INTENT);
        assertEquals(uri, view.getData());
    }

    @Test public void finishingActivityDoesNotOpenChooser() {
        activity.finish();
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(queries.isEmpty());
    }

    @Test public void webQueriesIncludeMimeTypesAndAllMatchesWithoutLosingTheAddress() {
        Uri uri = Uri.parse("https://example.invalid/path?one=1&two=2#section");
        browsers.open(uri);
        assertEquals(3, queries.size());
        assertNull(queries.get(0).getType());
        assertEquals("text/html", queries.get(1).getType());
        assertEquals("application/xhtml+xml", queries.get(2).getType());
        for (int i = 0; i < queries.size(); i++) {
            Intent query = queries.get(i);
            assertEquals(Intent.ACTION_VIEW, query.getAction());
            assertEquals(uri, query.getData());
            assertTrue(query.hasCategory(Intent.CATEGORY_BROWSABLE));
            assertNull(query.getPackage());
            assertNull(query.getComponent());
            assertEquals(PackageManager.MATCH_ALL | PackageManager.MATCH_DEFAULT_ONLY
                    | PackageManager.GET_RESOLVED_FILTER, (int) queryFlags.get(i));
            assertEquals(0, query.getFlags());
        }
    }

    @Test public void mimeMatchesBecomeExplicitChoicesWithTheirOriginalNetworkAddress() {
        matches.put(null, Arrays.asList(handler("test.general", "https", null)));
        matches.put("text/html", Arrays.asList(handler("test.html", "https", "text/html")));
        matches.put("application/xhtml+xml", Arrays.asList(handler("test.xhtml", "https", "application/xhtml+xml")));
        Uri uri = Uri.parse("https://example.invalid/path?value=1#part");
        browsers.open(uri);
        List<Intent> targets = targets();
        assertEquals(3, targets.size());
        assertEquals(new ComponentName("test.general", "test.general.WebActivity"), targets.get(0).getComponent());
        assertNull(targets.get(0).getType());
        assertEquals(new ComponentName("test.html", "test.html.WebActivity"), targets.get(1).getComponent());
        assertEquals("text/html", targets.get(1).getType());
        assertEquals("application/xhtml+xml", targets.get(2).getType());
        for (Intent target : targets) {
            assertEquals(uri, target.getData());
            assertEquals(Intent.ACTION_VIEW, target.getAction());
            assertTrue(target.hasCategory(Intent.CATEGORY_BROWSABLE));
            assertEquals(0, target.getFlags());
        }
        assertFalse(activity.opened.hasExtra(Intent.EXTRA_INITIAL_INTENTS));
        assertNull(ShadowToast.getTextOfLatestToast());
    }

    @Test public void moreThanThreeBrowsersAreNotTruncatedToTheInitialIntentLimit() {
        List<ResolveInfo> browsers = new ArrayList<>();
        for (int i = 0; i < 6; i++) browsers.add(handler("test.browser" + i, "https", null));
        matches.put(null, browsers);
        this.browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(6, targets().size());
        assertEquals(5, activity.opened.getParcelableArrayExtra(Intent.EXTRA_ALTERNATE_INTENTS).length);
        assertFalse(activity.opened.hasExtra(Intent.EXTRA_INITIAL_INTENTS));
    }

    @Test public void duplicateBrowserKeepsItsUntypedWebEntry() {
        ResolveInfo general = handler("test.browser", "https", null);
        ResolveInfo html = handler("test.browser", "https", "text/html");
        html.activityInfo.name = "test.browser.HtmlActivity";
        matches.put(null, Arrays.asList(general));
        matches.put("text/html", Arrays.asList(html));
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(1, targets().size());
        assertEquals("test.browser.WebActivity", targets().get(0).getComponent().getClassName());
        assertNull(targets().get(0).getType());
    }

    @Test public void htmlOnlyNetworkEntryPreservesItsMatchedMimeAndAddress() {
        matches.put("text/html", Arrays.asList(handler("test.html", "http", "text/html")));
        Uri uri = Uri.parse("http://example.invalid/page?one=1&two=2#part");
        browsers.open(uri);
        Intent target = targets().get(0);
        assertEquals("test.html", target.getComponent().getPackageName());
        assertEquals("text/html", target.getType());
        assertEquals(uri, target.getData());
    }

    @Test public void fileViewersDeepLinksAndUnavailableActivitiesAreExcluded() {
        ResolveInfo good = handler("test.browser", "https", "text/html");
        ResolveInfo file = handler("test.fileviewer", "content", "text/html");
        ResolveInfo domain = handler("test.siteapp", "https", "text/html");
        domain.filter.addDataAuthority("example.invalid", null);
        ResolveInfo path = handler("test.pathapp", "https", "text/html");
        path.filter.addDataPath("/special", android.os.PatternMatcher.PATTERN_PREFIX);
        ResolveInfo disabled = handler("test.disabled", "https", "text/html");
        disabled.activityInfo.enabled = false;
        ResolveInfo hidden = handler("test.internal", "https", "text/html");
        hidden.activityInfo.exported = false;
        ResolveInfo suspended = handler("test.suspended", "https", "text/html");
        suspended.activityInfo.applicationInfo.flags |= ApplicationInfo.FLAG_SUSPENDED;
        ResolveInfo protectedApp = handler("test.protected", "https", "text/html");
        protectedApp.activityInfo.permission = "test.permission.CANNOT_OPEN";
        ResolveInfo self = handler(activity.getPackageName(), "https", "text/html");
        matches.put("text/html", Arrays.asList(file, domain, path, disabled, hidden, suspended, protectedApp, self, good));
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(1, targets().size());
        assertEquals("test.browser", targets().get(0).getComponent().getPackageName());
    }

    @Test public void missingMatchedFilterCannotBeAssumedToBeAGenericBrowser() {
        ResolveInfo browser = handler("test.browser", "https", null);
        ResolveInfo unknown = handler("test.unknown", "https", null);
        unknown.filter = null;
        matches.put(null, Arrays.asList(browser, unknown));
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(1, targets().size());
        assertEquals("test.browser", targets().get(0).getComponent().getPackageName());
    }

    @Test public void queryRestrictionsStillAllowTheImplicitSystemChooserFallback() {
        browsers = new BrowserPicker(activity, (request, flags) -> { throw new SecurityException(); });
        Uri uri = Uri.parse("https://example.invalid/");
        browsers.open(uri);
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals(uri, targets().get(0).getData());
        assertNull(targets().get(0).getComponent());
        assertNull(targets().get(0).getType());
        assertFalse(activity.opened.hasExtra(Intent.EXTRA_CHOSEN_COMPONENT_INTENT_SENDER));
    }

    private List<Intent> targets() {
        List<Intent> result = new ArrayList<>();
        result.add(activity.opened.getParcelableExtra(Intent.EXTRA_INTENT));
        android.os.Parcelable[] alternates = activity.opened.getParcelableArrayExtra(Intent.EXTRA_ALTERNATE_INTENTS);
        if (alternates != null) for (android.os.Parcelable alternate : alternates) result.add((Intent) alternate);
        return result;
    }

    private static ResolveInfo handler(String packageName, String scheme, String mime) {
        ResolveInfo result = new ResolveInfo();
        result.activityInfo = new ActivityInfo();
        result.activityInfo.packageName = packageName;
        result.activityInfo.name = packageName + ".WebActivity";
        result.activityInfo.exported = true;
        result.activityInfo.enabled = true;
        result.activityInfo.applicationInfo = new ApplicationInfo();
        result.activityInfo.applicationInfo.enabled = true;
        result.activityInfo.applicationInfo.packageName = packageName;
        result.filter = new IntentFilter(Intent.ACTION_VIEW);
        result.filter.addCategory(Intent.CATEGORY_DEFAULT);
        result.filter.addCategory(Intent.CATEGORY_BROWSABLE);
        result.filter.addDataScheme(scheme);
        if (mime != null) {
            try { result.filter.addDataType(mime); }
            catch (IntentFilter.MalformedMimeTypeException invalid) { throw new AssertionError(invalid); }
        }
        return result;
    }

    @Test public void settingsShowUsableChoicesWithoutOpeningAnyWebsiteOrGlobalSettings() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertTrue(dialog.isShowing());
        assertTrue(dialog.getListView().isShown());
        assertEquals(3, dialog.getListView().getAdapter().getCount());
        assertEquals("每次询问", dialog.getListView().getAdapter().getItem(0).toString());
        assertEquals("跟随系统默认浏览器", dialog.getListView().getAdapter().getItem(1).toString());
        assertEquals(0, dialog.getListView().getCheckedItemPosition());
        assertNull(activity.opened);
        assertNull(ShadowToast.getTextOfLatestToast());
    }

    @Test public void browserSettingsEntryIsEnabled() {
        assertTrue(MainActivity.BROWSER_SETTINGS_ENABLED);
    }

    @Test public void normalChooserDoesNotSaveTheAutomaticallyResolvedFirstCandidate() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.open(Uri.parse("https://example.invalid/"));
        browsers.open(Uri.parse("https://example.invalid/next"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        browsers.showSettings();
        assertEquals(0, ShadowAlertDialog.getLatestAlertDialog().getListView().getCheckedItemPosition());
    }

    @Test public void savedAppDefaultSurvivesPickerRecreationAndUsesTheCurrentUrlAndMime() {
        matches.put("text/html", Arrays.asList(handler("test.html", "https", "text/html")));
        chooseSetting(2, true);
        assertNull(activity.opened);
        assertNull(ShadowToast.getTextOfLatestToast());
        browsers = new BrowserPicker(activity, candidateQuery);
        Uri uri = Uri.parse("https://example.invalid/new?one=1&two=2#part");
        browsers.open(uri);
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(new ComponentName("test.html", "test.html.WebActivity"), activity.opened.getComponent());
        assertEquals(uri, activity.opened.getData());
        assertEquals("text/html", activity.opened.getType());
        browsers.showSettings();
        assertEquals(2, ShadowAlertDialog.getLatestAlertDialog().getListView().getCheckedItemPosition());
    }

    @Test public void savedPackageUsesItsUpdatedActivityInsteadOfAnObsoleteComponent() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        chooseSetting(2, true);
        ResolveInfo changed = handler("test.browser", "https", null);
        changed.activityInfo.name = "test.browser.NewActivity";
        matches.put(null, Arrays.asList(changed));
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals("test.browser.NewActivity", activity.opened.getComponent().getClassName());
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
    }

    @Test public void selectingADifferentDefaultAndCancellingKeepsThePreviousDefault() {
        matches.put(null, Arrays.asList(handler("test.first", "https", null), handler("test.second", "https", null)));
        chooseSetting(2, true);
        chooseSetting(3, false);
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals("test.first", activity.opened.getComponent().getPackageName());
    }

    @Test public void savedDefaultCanBeChangedToAnotherAppOrBackToAlwaysAsk() {
        matches.put(null, Arrays.asList(handler("test.first", "https", null), handler("test.second", "https", null)));
        chooseSetting(2, true);
        chooseSetting(3, true);
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals("test.second", activity.opened.getComponent().getPackageName());
        chooseSetting(0, true);
        browsers.open(Uri.parse("https://example.invalid/next"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals(2, targets().size());
    }

    @Test public void followSystemDefaultUsesAnUntypedWebIntentAndNoAppEnumeration() {
        chooseSetting(1, true);
        queries.clear();
        Uri uri = Uri.parse("https://example.invalid/path?value=1");
        browsers.open(uri);
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(uri, activity.opened.getData());
        assertNull(activity.opened.getComponent());
        assertNull(activity.opened.getPackage());
        assertNull(activity.opened.getType());
        assertTrue(queries.isEmpty());
        assertNull(ShadowToast.getTextOfLatestToast());
    }

    @Test public void unavailableSavedAppResetsToAlwaysAskAndKeepsOtherCandidates() {
        matches.put(null, Arrays.asList(handler("test.removed", "https", null)));
        chooseSetting(2, true);
        matches.put(null, Arrays.asList(handler("test.other", "https", null)));
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals("test.other", targets().get(0).getComponent().getPackageName());
        assertTrue(ShadowToast.getTextOfLatestToast().contains("已恢复每次询问"));
        browsers.showSettings();
        assertEquals(0, ShadowAlertDialog.getLatestAlertDialog().getListView().getCheckedItemPosition());
    }

    @Test public void savedAppLaunchFailureReopensTheChooserWithoutTheFailedCandidate() {
        matches.put(null, Arrays.asList(handler("test.failed", "https", null), handler("test.other", "https", null)));
        chooseSetting(2, true);
        activity.unavailableComponent = new ComponentName("test.failed", "test.failed.WebActivity");
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals(1, targets().size());
        assertEquals("test.other", targets().get(0).getComponent().getPackageName());
        assertTrue(ShadowToast.getTextOfLatestToast().contains("已恢复每次询问"));
    }

    @Test public void settingsDismissalOrActivityCleanupDoesNotSaveAPendingSelection() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        dialog.getListView().performItemClick(null, 2, 2);
        browsers.close();
        assertFalse(dialog.isShowing());
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
    }

    private void chooseSetting(int index, boolean save) {
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertTrue(dialog.getListView().isShown());
        dialog.getListView().performItemClick(null, index, index);
        dialog.getButton(save ? DialogInterface.BUTTON_POSITIVE : DialogInterface.BUTTON_NEGATIVE).performClick();
        // AlertDialog delivers button listeners through its main-thread Handler.
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertFalse(dialog.isShowing());
    }

    @Test public void unsupportedLinksAreNotSentToOtherApplications() {
        browsers.open(null);
        browsers.open(Uri.parse("file:///data/private/account"));
        browsers.open(Uri.parse("content://private/account"));
        browsers.open(Uri.parse("intent://example.invalid/"));
        assertNull(activity.opened);
    }

    @Test public void missingChooserReportsFailureWithoutFallingBackToDefaultBrowser() {
        activity.missing = true;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(ShadowToast.getTextOfLatestToast().contains("无法打开网页"));
    }

    @Test public void deniedChooserReportsFailureWithoutOpeningSettings() {
        activity.denied = true;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(ShadowToast.getTextOfLatestToast().contains("无法打开网页"));
    }
}
