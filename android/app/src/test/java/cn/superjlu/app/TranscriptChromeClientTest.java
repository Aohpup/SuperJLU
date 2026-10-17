package cn.superjlu.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import org.robolectric.shadows.ShadowToast;

import java.util.ArrayList;

import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class)
@Config(sdk = {28, 35})
public class TranscriptChromeClientTest {
    private PickerActivity activity;
    private TranscriptChromeClient client;
    private final Uri document = Uri.parse("content://test.documents/document/grades.xlsx");

    public static class PickerActivity extends Activity {
        Intent launched;
        int request;
        boolean missingDocuments, missingAll, denied;

        @Override public void startActivityForResult(Intent intent, int requestCode) {
            if (denied) throw new SecurityException("picker denied");
            if (missingAll || (missingDocuments && Intent.ACTION_OPEN_DOCUMENT.equals(intent.getAction()))) {
                throw new ActivityNotFoundException("picker missing");
            }
            launched = intent;
            request = requestCode;
        }
    }

    private static class Receiver implements ValueCallback<Uri[]> {
        final ArrayList<Uri[]> values = new ArrayList<>();
        @Override public void onReceiveValue(Uri[] value) { values.add(value); }
    }

    private static WebChromeClient.FileChooserParams params(int mode) {
        return new WebChromeClient.FileChooserParams() {
            @Override public int getMode() { return mode; }
            @Override public String[] getAcceptTypes() { return new String[]{".xlsx", ".xls", ".csv"}; }
            @Override public boolean isCaptureEnabled() { return false; }
            @Override public CharSequence getTitle() { return null; }
            @Override public String getFilenameHint() { return null; }
            @Override public Intent createIntent() { return new Intent(Intent.ACTION_GET_CONTENT); }
        };
    }

    private Receiver open(int mode) {
        Receiver receiver = new Receiver();
        assertTrue(client.onShowFileChooser(null, receiver, params(mode)));
        return receiver;
    }

    @Before public void setup() {
        activity = Robolectric.buildActivity(PickerActivity.class).setup().get();
        client = new TranscriptChromeClient(activity);
    }

    @Test public void opensSystemPickerWithoutRelyingOnExportMimeType() {
        Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertEquals(Intent.ACTION_OPEN_DOCUMENT, activity.launched.getAction());
        assertEquals("*/*", activity.launched.getType());
        assertTrue(activity.launched.hasCategory(Intent.CATEGORY_OPENABLE));
        assertFalse(activity.launched.getBooleanExtra(Intent.EXTRA_ALLOW_MULTIPLE, true));
        assertEquals(TranscriptChromeClient.FILE_REQUEST, activity.request);
        assertTrue(receiver.values.isEmpty());
    }

    @Test public void returnsChosenContentUriExactlyOnce() {
        Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertTrue(client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(document)));
        assertArrayEquals(new Uri[]{document}, receiver.values.get(0));
        client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(document));
        assertEquals(1, receiver.values.size());
    }

    @Test public void cancelAllowsAnotherUpload() {
        Receiver cancelled = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        client.onActivityResult(activity.request, Activity.RESULT_CANCELED, null);
        assertEquals(1, cancelled.values.size());
        assertNull(cancelled.values.get(0));
        Receiver next = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(document));
        assertArrayEquals(new Uri[]{document}, next.values.get(0));
    }

    @Test public void replacementAndActivityDestructionCancelPendingCallbacks() {
        Receiver first = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        Receiver next = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertEquals(1, first.values.size());
        assertNull(first.values.get(0));
        assertTrue(next.values.isEmpty());
        client.cancel();
        client.cancel();
        assertEquals(1, next.values.size());
        assertNull(next.values.get(0));
    }

    @Test public void clipDataWorksForSingleAndMultipleModes() {
        Uri other = Uri.parse("content://test.documents/document/other.csv");
        ClipData clips = ClipData.newRawUri("synthetic", document);
        clips.addItem(new ClipData.Item(other));
        Intent result = new Intent();
        result.setClipData(clips);
        Receiver single = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        client.onActivityResult(activity.request, Activity.RESULT_OK, result);
        assertArrayEquals(new Uri[]{document}, single.values.get(0));
        Receiver multiple = open(WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE);
        assertTrue(activity.launched.getBooleanExtra(Intent.EXTRA_ALLOW_MULTIPLE, false));
        client.onActivityResult(activity.request, Activity.RESULT_OK, result.setData(document));
        assertArrayEquals(new Uri[]{document, other}, multiple.values.get(0));
    }

    @Test public void fallsBackWhenDocumentsPickerIsUnavailable() {
        activity.missingDocuments = true;
        Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertEquals(Intent.ACTION_GET_CONTENT, activity.launched.getAction());
        client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(document));
        assertArrayEquals(new Uri[]{document}, receiver.values.get(0));
    }

    @Test public void missingOrDeniedPickerCancelsWithAnExplanation() {
        activity.missingAll = true;
        Receiver missing = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertNull(missing.values.get(0));
        assertTrue(ShadowToast.getTextOfLatestToast().contains("无法打开文件选择器"));
        activity.missingAll = false;
        activity.denied = true;
        Receiver denied = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertNull(denied.values.get(0));
    }

    @Test public void rejectsNonDocumentUrisAndExplainsEmptyResults() {
        for (String path : new String[]{"https://example.invalid/grades.xlsx", "file:///data/private/file.xlsx"}) {
            Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
            client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(Uri.parse(path)));
            assertNull(receiver.values.get(0));
            assertTrue(ShadowToast.getTextOfLatestToast().contains("无法读取所选文件"));
        }
        Receiver empty = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        client.onActivityResult(activity.request, Activity.RESULT_OK, null);
        assertNull(empty.values.get(0));
    }

    @Test public void unrelatedResultsDoNotConsumePendingSelection() {
        Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertFalse(client.onActivityResult(9999, Activity.RESULT_CANCELED, null));
        assertTrue(receiver.values.isEmpty());
        client.onActivityResult(activity.request, Activity.RESULT_OK, new Intent().setData(document));
        assertArrayEquals(new Uri[]{document}, receiver.values.get(0));
    }

    @Test public void doesNotOpenPickerWhenActivityIsClosing() {
        activity.finish();
        Receiver receiver = open(WebChromeClient.FileChooserParams.MODE_OPEN);
        assertNull(activity.launched);
        assertNull(receiver.values.get(0));
    }
}
