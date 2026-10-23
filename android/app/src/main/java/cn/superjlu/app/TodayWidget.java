package cn.superjlu.app;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.os.Bundle;

public class TodayWidget extends AppWidgetProvider {
    @Override public void onUpdate(Context c, AppWidgetManager m, int[] ids) { WidgetUpdater.updateAll(c); }
    @Override public void onEnabled(Context c) { WidgetUpdater.updateAll(c); }
    @Override public void onDisabled(Context c) { WidgetUpdater.updateAll(c); }
    /** 用户调整大小（各家桌面格子尺寸不同）时按新尺寸重排。 */
    @Override public void onAppWidgetOptionsChanged(Context c, AppWidgetManager m, int id, Bundle o) { WidgetUpdater.updateAll(c); }
}
