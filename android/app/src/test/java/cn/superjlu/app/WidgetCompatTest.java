package cn.superjlu.app;

import static org.junit.Assert.*;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetProviderInfo;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;

import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.RuntimeEnvironment;
import org.robolectric.Shadows;

@RunWith(RobolectricTestRunner.class)
public class WidgetCompatTest {
    Context c = RuntimeEnvironment.getApplication();

    @Test public void layoutSelectionBySize() {
        assertTrue(WidgetUpdater.compact(WidgetUpdater.KIND_NEXT, 300, 300));
        assertTrue(WidgetUpdater.compact(WidgetUpdater.KIND_TODAY, 110, 50));   // 2×1
        assertTrue(WidgetUpdater.compact(WidgetUpdater.KIND_TODAY, 57, 110));   // 1×2
        assertFalse(WidgetUpdater.compact(WidgetUpdater.KIND_TODAY, 110, 110));
        assertFalse(WidgetUpdater.compact(WidgetUpdater.KIND_TODAY, 0, 0));     // 旧桌面不给尺寸 → 默认布局
        assertTrue(WidgetUpdater.compact(WidgetUpdater.KIND_WEEK, 250, 50));
        assertFalse(WidgetUpdater.compact(WidgetUpdater.KIND_WEEK, 250, 110));
        assertEquals(6, WidgetUpdater.rowsFor(0));
        assertEquals(3, WidgetUpdater.rowsFor(100));
        assertEquals(1, WidgetUpdater.rowsFor(40));
        assertEquals(6, WidgetUpdater.rowsFor(400));
    }

    @Test public void pendingIntentFlags() {
        assertTrue((WidgetUpdater.piFlags(31) & PendingIntent.FLAG_IMMUTABLE) != 0);
        assertTrue((WidgetUpdater.piFlags(24) & PendingIntent.FLAG_IMMUTABLE) != 0);
        assertEquals(0, WidgetUpdater.piFlags(22) & PendingIntent.FLAG_IMMUTABLE);
    }

    @Test public void receiversExportedAndEnabled() throws Exception {
        PackageManager pm = c.getPackageManager();
        for (Class<?> k : new Class<?>[]{TodayWidget.class, WeekWidget.class, NextWidget.class}) {
            ActivityInfo ai = pm.getReceiverInfo(new ComponentName(c, k), PackageManager.GET_META_DATA);
            assertTrue(k.getSimpleName(), ai.exported);
            assertTrue(ai.enabled);
            assertTrue(ai.metaData != null && ai.metaData.containsKey("android.appwidget.provider"));
            assertNotEquals(0, ai.labelRes);
        }
    }

    @Test public void schedulesAlarmWhenWidgetOrNotifyActive() {
        WidgetUpdater.prefs(c).edit().putBoolean(WidgetUpdater.KEY_NOTIFY, true).putString(WidgetUpdater.KEY_DATA, WidgetScheduleTest.J).commit();
        WidgetUpdater.updateAll(c);
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        assertNotNull(Shadows.shadowOf(am).getNextScheduledAlarm());
        WidgetUpdater.prefs(c).edit().putBoolean(WidgetUpdater.KEY_NOTIFY, false).commit();
        WidgetUpdater.updateAll(c);
        assertNull(Shadows.shadowOf(am).getNextScheduledAlarm());
    }

    @Test public void compactViewsBuildWithoutData() {
        assertNotNull(WidgetUpdater.build(c, new WidgetSchedule(null), java.util.Calendar.getInstance(), WidgetUpdater.KIND_TODAY, 110, 40));
        assertNotNull(WidgetUpdater.build(c, new WidgetSchedule(WidgetScheduleTest.J), java.util.Calendar.getInstance(), WidgetUpdater.KIND_WEEK, 250, 180));
    }
}
