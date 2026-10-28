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
        /** When true, component-less VIEW intents fail (OEM with a broken system default). */
        static boolean refuseImplicit;
        /** When true, ACTION_CHOOSER intents fail (OEM that swallows the system panel). */
        static boolean refuseChooser;
        ComponentName unavailableComponent;
        @Override public void startActivity(Intent intent) {
            if (missing) throw new ActivityNotFoundException();
            if (denied) throw new SecurityException();
            if (refuseChooser && Intent.ACTION_CHOOSER.equals(intent.getAction())) {
                throw new ActivityNotFoundException();
            }
            if (refuseImplicit && Intent.ACTION_VIEW.equals(intent.getAction())
                    && intent.getComponent() == null && intent.getPackage() == null) {
                throw new ActivityNotFoundException();
            }
            if (unavailableComponent != null) {
                if (unavailableComponent.equals(intent.getComponent())) {
                    throw new ActivityNotFoundException();
                }
                if (intent.getPackage() != null
                        && unavailableComponent.getPackageName().equals(intent.getPackage())) {
                    throw new ActivityNotFoundException();
                }
            }
            opened = intent;
        }
        @Override public void startActivityForResult(Intent intent, int code) {
            fail("Must not open an application picker activity");
        }
    }
    private CaptureActivity activity;
    private BrowserPicker browsers;
    private Map<String, List<ResolveInfo>> matches;
    private List<Intent> queries;
    private List<Integer> queryFlags;
    private BrowserPicker.CandidateQuery candidateQuery;

    @Before public void setup() {
        CaptureActivity.refuseImplicit = false;
        CaptureActivity.refuseChooser = false;
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
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(uri, activity.opened.getData());
        assertTrue(activity.opened.hasCategory(Intent.CATEGORY_BROWSABLE));
        assertNull(activity.opened.getPackage());
        assertNull(activity.opened.getComponent());
        assertNull(activity.opened.getType());
        assertNull(activity.opened.getSelector());
        assertTrue(queries.isEmpty());
        assertEquals("test.old", activity.getSharedPreferences("external-browser", 0)
                .getString("selected", null));
    }

    @Test public void defaultModeFollowsSystemWithoutEnumeratingApps() {
        Uri uri = Uri.parse("https://example.invalid/");
        browsers.open(uri);
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(uri, activity.opened.getData());
        assertNull(activity.opened.getComponent());
        assertNull(activity.opened.getPackage());
        assertNull(activity.opened.getType());
        assertTrue(activity.opened.hasCategory(Intent.CATEGORY_DEFAULT));
        assertTrue(activity.opened.hasCategory(Intent.CATEGORY_BROWSABLE));
        assertTrue(queries.isEmpty());
    }

    @Test public void httpLinksKeepTheirOriginalAddress() {
        Uri uri = Uri.parse("http://example.invalid/path?one=1&two=2#section");
        browsers.open(uri);
        assertEquals(uri, activity.opened.getData());
    }

    @Test public void finishingActivityDoesNotOpenBrowser() {
        activity.finish();
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(queries.isEmpty());
    }

    @Test public void askPreferenceStillOpensSystemChooserHooks() {
        // No browsers discovered: ask mode falls back to the system chooser panel.
        activity.getSharedPreferences("browser-preferences-v1", 0).edit()
                .putString("mode", "ask").commit();
        Uri uri = Uri.parse("https://example.invalid/");
        browsers.open(uri);
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        assertEquals("选择浏览器打开", activity.opened.getStringExtra(Intent.EXTRA_TITLE));
        Intent view = activity.opened.getParcelableExtra(Intent.EXTRA_INTENT);
        assertNotNull(view);
        assertEquals(Intent.ACTION_VIEW, view.getAction());
        assertEquals(uri, view.getData());
        assertEquals("ask", activity.getSharedPreferences("browser-preferences-v1", 0)
                .getString("mode", null));
    }

    @Test public void singleCandidateAutoLaunchIsDisabledOnSupportedAndroidVersions() {
        activity.getSharedPreferences("browser-preferences-v1", 0).edit()
                .putString("mode", "ask").commit();
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            assertTrue(activity.opened.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
            assertFalse(activity.opened.getBooleanExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE, true));
        } else {
            assertFalse(activity.opened.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
        }
        Intent view = activity.opened.getParcelableExtra(Intent.EXTRA_INTENT);
        assertFalse(view.hasExtra(Intent.EXTRA_AUTO_LAUNCH_SINGLE_CHOICE));
    }

    @Test public void settingsShowUsableChoicesWithoutOpeningAnyWebsiteOrGlobalSettings() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertTrue(dialog.isShowing());
        assertTrue(dialog.getListView().isShown());
        assertEquals(3, dialog.getListView().getAdapter().getCount());
        assertEquals("跟随系统默认浏览器", dialog.getListView().getAdapter().getItem(1).toString());
        assertEquals(1, dialog.getListView().getCheckedItemPosition());
        assertNull(activity.opened);
        assertNull(ShadowToast.getTextOfLatestToast());
        assertEquals("每次询问", dialog.getListView().getAdapter().getItem(0).toString());
    }

    @Test public void settingsDiscoveryUsesMimeQueriesAndKeepsNeutralProbeUrl() {
        matches.put(null, Arrays.asList(handler("test.general", "https", null)));
        matches.put("text/html", Arrays.asList(handler("test.html", "https", "text/html")));
        matches.put("application/xhtml+xml", Arrays.asList(handler("test.xhtml", "https", "application/xhtml+xml")));
        browsers.showSettings();
        assertEquals(3, queries.size());
        assertNull(queries.get(0).getType());
        assertEquals("text/html", queries.get(1).getType());
        assertEquals("application/xhtml+xml", queries.get(2).getType());
        Uri probe = Uri.parse("https://example.org/");
        for (int i = 0; i < queries.size(); i++) {
            Intent query = queries.get(i);
            assertEquals(Intent.ACTION_VIEW, query.getAction());
            assertEquals(probe, query.getData());
            assertTrue(query.hasCategory(Intent.CATEGORY_BROWSABLE));
            assertEquals(PackageManager.MATCH_ALL | PackageManager.MATCH_DEFAULT_ONLY
                    | PackageManager.GET_RESOLVED_FILTER, (int) queryFlags.get(i));
        }
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertEquals(5, dialog.getListView().getAdapter().getCount());
        assertNull(activity.opened);
    }

    @Test public void mimeMatchesBecomeExplicitAppChoicesWithTheirOriginalNetworkAddress() {
        matches.put(null, Arrays.asList(handler("test.general", "https", null)));
        matches.put("text/html", Arrays.asList(handler("test.html", "https", "text/html")));
        matches.put("application/xhtml+xml", Arrays.asList(handler("test.xhtml", "https", "application/xhtml+xml")));
        chooseSetting(3, true); // test.html (ask=0, system=1, general=2, html=3)
        Uri uri = Uri.parse("https://example.invalid/path?value=1#part");
        activity.opened = null;
        queries.clear();
        browsers.open(uri);
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(new ComponentName("test.html", "test.html.WebActivity"), activity.opened.getComponent());
        assertEquals(uri, activity.opened.getData());
        assertEquals("text/html", activity.opened.getType());
        assertNull(ShadowToast.getTextOfLatestToast());
    }

    @Test public void moreThanThreeBrowsersAreListedInSettings() {
        List<ResolveInfo> found = new ArrayList<>();
        for (int i = 0; i < 6; i++) found.add(handler("test.browser" + i, "https", null));
        matches.put(null, found);
        browsers.showSettings();
        assertEquals(8, ShadowAlertDialog.getLatestAlertDialog().getListView().getAdapter().getCount());
    }

    @Test public void duplicateBrowserKeepsItsUntypedWebEntryWhenOpeningSavedApp() {
        ResolveInfo general = handler("test.browser", "https", null);
        ResolveInfo html = handler("test.browser", "https", "text/html");
        html.activityInfo.name = "test.browser.HtmlActivity";
        matches.put(null, Arrays.asList(general));
        matches.put("text/html", Arrays.asList(html));
        chooseSetting(2, true);
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals("test.browser.WebActivity", activity.opened.getComponent().getClassName());
        assertNull(activity.opened.getType());
    }

    @Test public void htmlOnlyNetworkEntryPreservesItsMatchedMimeAndAddress() {
        // Settings probes https://example.org/, so the candidate must declare https.
        matches.put("text/html", Arrays.asList(handler("test.html", "https", "text/html")));
        chooseSetting(2, true);
        Uri uri = Uri.parse("https://example.invalid/page?one=1&two=2#part");
        activity.opened = null;
        browsers.open(uri);
        assertEquals("test.html", activity.opened.getComponent().getPackageName());
        assertEquals("text/html", activity.opened.getType());
        assertEquals(uri, activity.opened.getData());
    }

    @Test public void fileViewersDeepLinksAndUnavailableActivitiesAreExcludedFromSettings() {
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
        browsers.showSettings();
        assertEquals(3, ShadowAlertDialog.getLatestAlertDialog().getListView().getAdapter().getCount());
        assertEquals("test.browser", ShadowAlertDialog.getLatestAlertDialog()
                .getListView().getAdapter().getItem(2).toString());
    }

    @Test public void missingMatchedFilterCannotBeAssumedToBeAGenericBrowser() {
        ResolveInfo browser = handler("test.browser", "https", null);
        ResolveInfo unknown = handler("test.unknown", "https", null);
        unknown.filter = null;
        matches.put(null, Arrays.asList(browser, unknown));
        browsers.showSettings();
        assertEquals(3, ShadowAlertDialog.getLatestAlertDialog().getListView().getAdapter().getCount());
        assertEquals("test.browser", ShadowAlertDialog.getLatestAlertDialog()
                .getListView().getAdapter().getItem(2).toString());
    }

    @Test public void queryRestrictionsStillAllowFollowSystemOpen() {
        browsers = new BrowserPicker(activity, (request, flags) -> { throw new SecurityException(); });
        Uri uri = Uri.parse("https://example.invalid/");
        browsers.open(uri);
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(uri, activity.opened.getData());
        assertNull(activity.opened.getComponent());
        assertNull(activity.opened.getType());
    }

    @Test public void browserSettingsEntryIsEnabled() {
        assertTrue(MainActivity.BROWSER_SETTINGS_ENABLED);
    }

    @Test public void openingLinksDoesNotSaveADiscoveredCandidateAsDefault() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.open(Uri.parse("https://example.invalid/"));
        browsers.open(Uri.parse("https://example.invalid/next"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertNull(activity.opened.getComponent());
        browsers.showSettings();
        assertEquals(1, ShadowAlertDialog.getLatestAlertDialog().getListView().getCheckedItemPosition());
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
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals("test.browser.NewActivity", activity.opened.getComponent().getClassName());
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
    }

    @Test public void selectingADifferentDefaultAndCancellingKeepsThePreviousDefault() {
        matches.put(null, Arrays.asList(handler("test.first", "https", null), handler("test.second", "https", null)));
        chooseSetting(2, true);
        chooseSetting(3, false);
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals("test.first", activity.opened.getComponent().getPackageName());
    }

    @Test public void savedDefaultCanBeChangedToAnotherAppOrBackToFollowSystem() {
        matches.put(null, Arrays.asList(handler("test.first", "https", null), handler("test.second", "https", null)));
        chooseSetting(2, true);
        chooseSetting(3, true);
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals("test.second", activity.opened.getComponent().getPackageName());
        chooseSetting(1, true);
        activity.opened = null;
        queries.clear();
        browsers.open(Uri.parse("https://example.invalid/next"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertNull(activity.opened.getComponent());
        assertTrue(queries.isEmpty());
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

    @Test public void unavailableSavedAppResetsToFollowSystem() {
        matches.put(null, Arrays.asList(handler("test.removed", "https", null)));
        chooseSetting(2, true);
        matches.put(null, Arrays.asList(handler("test.other", "https", null)));
        // Package no longer resolves as a browser and cannot be started (uninstalled / disabled).
        activity.unavailableComponent = new ComponentName("test.removed", "test.removed.WebActivity");
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertNull(activity.opened.getComponent());
        assertTrue(ShadowToast.getTextOfLatestToast().contains("已恢复跟随系统"));
        browsers.showSettings();
        assertEquals(1, ShadowAlertDialog.getLatestAlertDialog().getListView().getCheckedItemPosition());
    }

    @Test public void savedAppLaunchFailureFallsBackToFollowSystem() {
        matches.put(null, Arrays.asList(handler("test.failed", "https", null), handler("test.other", "https", null)));
        chooseSetting(2, true);
        activity.unavailableComponent = new ComponentName("test.failed", "test.failed.WebActivity");
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertNull(activity.opened.getComponent());
        assertTrue(ShadowToast.getTextOfLatestToast().contains("已恢复跟随系统"));
    }

    @Test public void settingsDismissalOrActivityCleanupDoesNotSaveAPendingSelection() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        dialog.getListView().performItemClick(null, 1, 1);
        browsers.close();
        assertFalse(dialog.isShowing());
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertNull(activity.opened.getComponent());
    }

    @Test public void askModeWithSeveralBrowsersShowsInAppListAndLaunchesPickedExplicitly() {
        activity.getSharedPreferences("browser-preferences-v1", 0).edit()
                .putString("mode", "ask").commit();
        matches.put(null, Arrays.asList(handler("test.one", "https", null), handler("test.two", "https", null)));
        Uri uri = Uri.parse("https://example.invalid/pick");
        browsers.open(uri);
        assertNull(activity.opened);
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertTrue(dialog.isShowing());
        assertEquals(3, dialog.getListView().getAdapter().getCount());
        Shadows.shadowOf(dialog).clickOnItem(1);
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals("test.two", activity.opened.getComponent().getPackageName());
        assertEquals(uri, activity.opened.getData());
    }

    @Test public void askModeLastRowFallsBackToSystemPanel() {
        activity.getSharedPreferences("browser-preferences-v1", 0).edit()
                .putString("mode", "ask").commit();
        matches.put(null, Arrays.asList(handler("test.one", "https", null), handler("test.two", "https", null)));
        browsers.open(Uri.parse("https://example.invalid/"));
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        Shadows.shadowOf(dialog).clickOnItem(2);
        Shadows.shadowOf(Looper.getMainLooper()).idle();
        assertEquals(Intent.ACTION_CHOOSER, activity.opened.getAction());
    }

    @Test public void settingsOfferAskEveryTimeAndSaveIt() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        chooseSetting(0, true);
        assertEquals("ask", activity.getSharedPreferences("browser-preferences-v1", 0)
                .getString("mode", null));
        browsers.showSettings();
        AlertDialog dialog = ShadowAlertDialog.getLatestAlertDialog();
        assertEquals("每次询问", dialog.getListView().getAdapter().getItem(0).toString());
        assertEquals(0, dialog.getListView().getCheckedItemPosition());
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

    @Test public void systemDefaultFailureFallsBackToExplicitDiscoveredBrowser() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        CaptureActivity.refuseImplicit = true;
        browsers.open(Uri.parse("https://example.invalid/page"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals(new ComponentName("test.browser", "test.browser.WebActivity"),
                activity.opened.getComponent());
        assertEquals(Uri.parse("https://example.invalid/page"), activity.opened.getData());
    }

    @Test public void chooserDenialFallsBackToExplicitBrowser() {
        activity.getSharedPreferences("browser-preferences-v1", 0).edit()
                .putString("mode", "ask").commit();
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        CaptureActivity.refuseChooser = true;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals("test.browser", activity.opened.getComponent().getPackageName());
    }

    @Test public void packageScopedFallbackOpensPreferredAppWhenComponentGone() {
        matches.put(null, Arrays.asList(handler("test.browser", "https", null)));
        chooseSetting(2, true);
        matches.clear();
        activity.opened = null;
        browsers.open(Uri.parse("https://example.invalid/kept"));
        assertEquals(Intent.ACTION_VIEW, activity.opened.getAction());
        assertEquals("test.browser", activity.opened.getPackage());
        assertNull(activity.opened.getComponent());
        assertEquals(Uri.parse("https://example.invalid/kept"), activity.opened.getData());
        assertNull(ShadowToast.getTextOfLatestToast());
    }

    @Test public void unsupportedLinksAreNotSentToOtherApplications() {

        browsers.open(null);
        browsers.open(Uri.parse("file:///data/private/account"));
        browsers.open(Uri.parse("content://private/account"));
        browsers.open(Uri.parse("intent://example.invalid/"));
        assertNull(activity.opened);
    }

    @Test public void missingBrowserReportsFailureWithoutOpeningSettings() {
        activity.missing = true;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(ShadowToast.getTextOfLatestToast().contains("无法打开网页"));
    }

    @Test public void deniedBrowserReportsFailureWithoutOpeningSettings() {
        activity.denied = true;
        browsers.open(Uri.parse("https://example.invalid/"));
        assertNull(activity.opened);
        assertTrue(ShadowToast.getTextOfLatestToast().contains("无法打开网页"));
    }
}
