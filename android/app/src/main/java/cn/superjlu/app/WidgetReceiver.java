package cn.superjlu.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** 闹钟到点、开机、改时间/时区、应用更新后重新刷新小组件并续约闹钟。 */
public class WidgetReceiver extends BroadcastReceiver {
    static final java.util.Set<String> ACTIONS = new java.util.HashSet<>(java.util.Arrays.asList(
            WidgetUpdater.ACTION_TICK, Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED,
            Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED, Intent.ACTION_DATE_CHANGED, Intent.ACTION_LOCALE_CHANGED));

    @Override public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTIONS.contains(intent.getAction())) return;
        try { WidgetUpdater.updateAll(context); } catch (RuntimeException ignored) {}
    }
}
