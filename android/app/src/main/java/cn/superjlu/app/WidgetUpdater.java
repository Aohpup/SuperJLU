package cn.superjlu.app;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.widget.RemoteViews;

import java.util.Calendar;
import java.util.List;

/** 写入快照、刷新所有小组件和锁屏通知，并预约下一次刷新（AlarmManager，进程被杀/重启后由 WidgetReceiver 恢复）。 */
final class WidgetUpdater {
    static final String PREFS = "superjlu_widget";
    static final String KEY_DATA = "schedule_json";
    static final String KEY_NOTIFY = "lock_notify";
    static final String ACTION_TICK = "cn.superjlu.app.WIDGET_TICK";
    static final String CHANNEL = "next_class";
    static final int NOTIFY_ID = 4201;
    private static final int[] ROWS = {R.id.w_row1, R.id.w_row2, R.id.w_row3, R.id.w_row4, R.id.w_row5, R.id.w_row6};

    private WidgetUpdater() {}

    static SharedPreferences prefs(Context c) { return c.getSharedPreferences(PREFS, Context.MODE_PRIVATE); }

    static void save(Context c, String json) {
        if (json == null || json.length() > 1_000_000) return;
        // 内容相同也要刷新：重新打开 App 时借此补发被系统清掉的通知
        if (!json.equals(prefs(c).getString(KEY_DATA, null))) prefs(c).edit().putString(KEY_DATA, json).apply();
        updateAll(c);
    }

    static void updateAll(Context ctx) {
        Context c = ctx.getApplicationContext();
        WidgetSchedule s = new WidgetSchedule(prefs(c).getString(KEY_DATA, null));
        Calendar now = Calendar.getInstance();
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int n = 0;
        if (m != null) {
            for (int id : m.getAppWidgetIds(new ComponentName(c, TodayWidget.class))) { m.updateAppWidget(id, sized(c, m, id, s, now, KIND_TODAY)); n++; }
            for (int id : m.getAppWidgetIds(new ComponentName(c, WeekWidget.class))) { m.updateAppWidget(id, sized(c, m, id, s, now, KIND_WEEK)); n++; }
            for (int id : m.getAppWidgetIds(new ComponentName(c, NextWidget.class))) { m.updateAppWidget(id, sized(c, m, id, s, now, KIND_NEXT)); n++; }
        }
        boolean notify = prefs(c).getBoolean(KEY_NOTIFY, false);
        updateNotification(c, s, now, notify);
        if (n > 0 || notify) schedule(c, s.valid ? s.nextBoundary(now) : now.getTimeInMillis() + 6 * 3_600_000L);
        else cancel(c);
    }

    static final int KIND_TODAY = 0, KIND_WEEK = 1, KIND_NEXT = 2;

    /** 按尺寸选布局：宽或高太小用单行紧凑版（1×1 / 2×1 / 被 OEM 桌面压扁时）。 */
    static boolean compact(int kind, int wDp, int hDp) {
        if (kind == KIND_NEXT) return true;
        if (wDp <= 0 || hDp <= 0) return false;
        return kind == KIND_TODAY ? (hDp < 90 || wDp < 90) : (hDp < 70 || wDp < 150);
    }

    /** 列表小组件按高度显示几行（每行约 20dp，标题约 30dp）。 */
    static int rowsFor(int hDp) {
        if (hDp <= 0) return ROWS.length;
        return Math.max(1, Math.min(ROWS.length, (hDp - 34) / 20));
    }

    static RemoteViews build(Context c, WidgetSchedule s, Calendar now, int kind, int wDp, int hDp) {
        if (compact(kind, wDp, hDp)) return compactViews(c, s, now);
        return kind == KIND_WEEK ? listViews(c, s, now, rowsFor(hDp)) : todayViews(c, s, now);
    }

    private static RemoteViews sized(Context c, AppWidgetManager m, int id, WidgetSchedule s, Calendar now, int kind) {
        android.os.Bundle o = m.getAppWidgetOptions(id);
        if (Build.VERSION.SDK_INT >= 31) {
            // Android 12+：交给桌面按实际尺寸挑（响应式布局）
            java.util.Map<android.util.SizeF, RemoteViews> map = new java.util.HashMap<>();
            map.put(new android.util.SizeF(57f, 40f), build(c, s, now, kind, 57, 40));
            map.put(new android.util.SizeF(110f, 110f), build(c, s, now, kind, 110, 110));
            if (kind == KIND_WEEK) {
                map.put(new android.util.SizeF(180f, 80f), build(c, s, now, kind, 180, 80));
                map.put(new android.util.SizeF(250f, 180f), build(c, s, now, kind, 250, 180));
            }
            try { return new RemoteViews(map); } catch (RuntimeException ignored) {}
        }
        int w = o == null ? 0 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH);
        int h = o == null ? 0 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT);
        return build(c, s, now, kind, w, h);
    }

    static RemoteViews compactViews(Context c, WidgetSchedule s, Calendar now) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_next);
        v.setOnClickPendingIntent(R.id.w_root, openApp(c));
        String[] t = s.valid ? s.notifyText(now) : null;
        v.setTextViewText(R.id.w_name, !s.valid ? "点我同步课表" : t == null ? "近期没有课" : t[0]);
        v.setTextViewText(R.id.w_sub, t == null ? "" : t[1]);
        return v;
    }

    /** 按 SDK 选 PendingIntent 标志：23+ 一律 IMMUTABLE（31+ 强制要求）。 */
    static int piFlags(int sdk) {
        return PendingIntent.FLAG_UPDATE_CURRENT | (sdk >= 23 ? PendingIntent.FLAG_IMMUTABLE : 0);
    }

    static PendingIntent openApp(Context c) {
        Intent i = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        return PendingIntent.getActivity(c, 1, i, piFlags(Build.VERSION.SDK_INT));
    }

    static String nowWeekText(WidgetSchedule s, Calendar now) {
        if (!s.valid) return "";
        int w = s.weekOf(now);
        return (w >= 1 ? "第" + w + "周 · " : "未开学 · ") + "周" + "一二三四五六日".charAt(WidgetSchedule.weekday(now) - 1);
    }

    static RemoteViews todayViews(Context c, WidgetSchedule s, Calendar now) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_today);
        v.setOnClickPendingIntent(R.id.w_root, openApp(c));
        String[] t = s.valid ? s.notifyText(now) : null;
        v.setTextViewText(R.id.w_name, !s.valid ? "点我同步课表" : t == null ? "近期没有课" : t[0]);
        v.setTextViewText(R.id.w_sub, t == null ? "" : t[1]);
        return v;
    }

    static RemoteViews listViews(Context c, WidgetSchedule s, Calendar now, int maxRows) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.widget_week);
        v.setOnClickPendingIntent(R.id.w_root, openApp(c));
        v.setTextViewText(R.id.w_title, s.valid && s.weekOf(now) >= 1 ? "第" + s.weekOf(now) + "周" : "课表");
        int r = 0;
        if (s.valid) {
            Calendar d = (Calendar) now.clone();
            for (int day = 0; day < 7 && r < maxRows; day++) {
                if (day > 0 && WidgetSchedule.weekday(d) == 1) break; // 只到本周日
                List<WidgetSchedule.Item> items = day == 0 ? s.remainingToday(d) : s.on(d);
                for (WidgetSchedule.Item i : items) {
                    if (r >= maxRows) break;
                    v.setTextViewText(ROWS[r], WidgetSchedule.dayTag(day, now) + " " + i.hm(false) + "  " + i.name + (i.location.isEmpty() ? "" : " · " + i.location));
                    v.setViewVisibility(ROWS[r], android.view.View.VISIBLE);
                    r++;
                }
                d.add(Calendar.DAY_OF_MONTH, 1);
            }
        }
        if (r == 0) {
            v.setTextViewText(ROWS[0], s.valid ? "本周没课了" : "点我同步课表");
            v.setViewVisibility(ROWS[0], android.view.View.VISIBLE);
            r = 1;
        }
        for (; r < ROWS.length; r++) v.setViewVisibility(ROWS[r], android.view.View.GONE);
        return v;
    }

    static void updateNotification(Context c, WidgetSchedule s, Calendar now, boolean enabled) {
        NotificationManager nm = (NotificationManager) c.getSystemService(Context.NOTIFICATION_SERVICE);
        if (nm == null) return;
        String[] t = enabled && s.valid ? s.notifyText(now) : null;
        if (t == null) { nm.cancel(NOTIFY_ID); return; }
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= 26) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "下一节课", NotificationManager.IMPORTANCE_LOW);
            ch.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
            b = new Notification.Builder(c, CHANNEL);
        } else {
            b = new Notification.Builder(c).setPriority(Notification.PRIORITY_LOW);
        }
        b.setSmallIcon(R.drawable.ic_launcher_foreground)
                .setContentTitle(t[0]).setContentText(t[1])
                .setOngoing(true).setShowWhen(false).setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setContentIntent(openApp(c));
        try { nm.notify(NOTIFY_ID, b.build()); } catch (SecurityException ignored) {}
    }

    private static PendingIntent tick(Context c) {
        Intent i = new Intent(c, WidgetReceiver.class).setAction(ACTION_TICK);
        return PendingIntent.getBroadcast(c, 2, i, piFlags(Build.VERSION.SDK_INT));
    }

    /** 不申请精确闹钟权限：setAndAllowWhileIdle 在打盹时也会触发（可能晚几分钟）。 */
    static void schedule(Context c, long at) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am == null) return;
        try {
            am.setAndAllowWhileIdle(AlarmManager.RTC, at, tick(c));
        } catch (RuntimeException e) {
            am.setWindow(AlarmManager.RTC, at, 10 * 60_000L, tick(c));
        }
    }

    /** 让用户从 App 里直接把小组件钉到桌面（OPPO/ColorOS 等选择器不列出时的兜底）。 */
    static boolean canPin(Context c) {
        if (Build.VERSION.SDK_INT < 26) return false;
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        return m != null && m.isRequestPinAppWidgetSupported();
    }

    static boolean pin(Context c, int kind) {
        if (Build.VERSION.SDK_INT < 26 || !canPin(c)) return false;
        Class<?> cls = kind == KIND_WEEK ? WeekWidget.class : kind == KIND_NEXT ? NextWidget.class : TodayWidget.class;
        try {
            return AppWidgetManager.getInstance(c).requestPinAppWidget(new ComponentName(c, cls), null, null);
        } catch (RuntimeException e) {
            return false;
        }
    }

    static void cancel(Context c) {
        AlarmManager am = (AlarmManager) c.getSystemService(Context.ALARM_SERVICE);
        if (am != null) am.cancel(tick(c));
    }
}
