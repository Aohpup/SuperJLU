package cn.superjlu.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebView;
import android.widget.Toast;

import java.util.ArrayList;

/** WebView 的文件输入需要原生层打开选择器，并把选择结果交还给网页。 */
final class TranscriptChromeClient extends WebChromeClient {
    static final int FILE_REQUEST = 1001;
    private final Activity activity;
    private ValueCallback<Uri[]> pending;
    private boolean multiple;

    TranscriptChromeClient(Activity activity) {
        this.activity = activity;
    }

    @Override
    public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                     FileChooserParams params) {
        cancel();
        pending = callback;
        multiple = params != null && params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE;
        if (activity.isFinishing() || activity.isDestroyed()) {
            cancel();
            return true;
        }
        try {
            launch(Intent.ACTION_OPEN_DOCUMENT);
        } catch (ActivityNotFoundException missingDocuments) {
            try {
                launch(Intent.ACTION_GET_CONTENT);
            } catch (ActivityNotFoundException | SecurityException unavailable) {
                pickerFailed();
            }
        } catch (SecurityException denied) {
            pickerFailed();
        }
        return true;
    }

    @SuppressWarnings("deprecation")
    private void launch(String action) {
        // 部分教务导出的 MIME 类型不准确；由网页和后端继续校验扩展名及 5 MB 上限。
        Intent intent = new Intent(action).addCategory(Intent.CATEGORY_OPENABLE)
                .setType("*/*").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, multiple);
        activity.startActivityForResult(intent, FILE_REQUEST);
    }

    boolean onActivityResult(int request, int result, Intent data) {
        if (request != FILE_REQUEST) return false;
        if (pending == null) return true;
        ArrayList<Uri> uris = new ArrayList<>();
        if (result == Activity.RESULT_OK && data != null) {
            addDocument(uris, data.getData());
            ClipData clips = data.getClipData();
            if (clips != null) {
                for (int i = 0; i < clips.getItemCount(); i++) {
                    addDocument(uris, clips.getItemAt(i).getUri());
                }
            }
        }
        if (result == Activity.RESULT_OK && uris.isEmpty()) {
            Toast.makeText(activity, "无法读取所选文件，请从系统文件选择器重新选择", Toast.LENGTH_LONG).show();
        }
        complete(uris.isEmpty() ? null : uris.toArray(new Uri[0]));
        return true;
    }

    private void addDocument(ArrayList<Uri> uris, Uri uri) {
        // 系统文档选择器返回带授权的 content URI，不接受网页地址或应用私有文件路径。
        if (uri != null && "content".equals(uri.getScheme()) && !uris.contains(uri)
                && (multiple || uris.isEmpty())) {
            uris.add(uri);
        }
    }

    void cancel() {
        complete(null);
    }

    private void complete(Uri[] uris) {
        ValueCallback<Uri[]> callback = pending;
        pending = null;
        multiple = false;
        if (callback != null) callback.onReceiveValue(uris);
    }

    private void pickerFailed() {
        cancel();
        Toast.makeText(activity, "无法打开文件选择器，请确认手机已启用系统文件应用", Toast.LENGTH_LONG).show();
    }
}
