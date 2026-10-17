const a = require('../../utils/academic');
const ui = require('../../utils/ui');
Page({
  data: { loading: true, mode: 'demo', courses: [], nextExam: null },
  async onShow() {
    const app = getApp();
    if(app.globalData.snapshot&&app.globalData.snapshot.connectionSource==='phone-browser')this.setData({network:''});
    else if(['direct','hybrid'].includes(require('../../config').transport)) {
      this.setData({network:app.globalData.directNetwork?app.globalData.directNetwork.message:'正在检查校园网连接…'});
      if(app.globalData.directNetworkCheck)app.globalData.directNetworkCheck.then(result=>this.setData({network:(app.globalData.directNetwork||result).message}));
    }
    try {
      const data = await app.load();
      const mode = app.globalData.mode;
      const monday = a.firstMonday(data, mode), now = new Date();
      const week = a.currentWeek(monday), weekday = now.getDay() || 7;
      const courses = a.coursesOn(data, week, weekday).map((c,i) => ({ ...c, id:i, time:a.periodLabel(c,data.periods || {}) }));
      const nextExam = a.examList(data.exams).find(e => !e.past) || null;
      this.setData({ mode, browserOnly:require('../../config').transport==='browser',browserSync:data.connectionSource==='phone-browser',direct:['direct','hybrid'].includes(require('../../config').transport),offline: app.globalData.offline, week, inTerm: !!monday && week >= 1 && week <= ((data.calendar || {}).total_weeks || 20),
        date: a.iso(now).replace(/-/g,'.'), weekday: ['','星期一','星期二','星期三','星期四','星期五','星期六','星期日'][weekday],
        courses, nextExam, bound:app.globalData.schoolLoggedIn, updated:ui.timestamp(data.updated),loading:false });
    } catch(e) { this.setData({ loading:false }); ui.error(e); }
  },
  go: ui.go,
  async refresh() {
    if(require('../../config').transport==='browser'||(getApp().globalData.snapshot||{}).connectionSource==='phone-browser'){wx.stopPullDownRefresh();return wx.navigateTo({url:'/pages/browser-sync/index'});}
    if (this.data.syncing) return;
    this.setData({ syncing: true });
    try {
      const data = await getApp().load(true); await this.onShow();
      wx.showToast({ title: data.failures && data.failures.length ? '部分模块未同步，已保留缓存' : '同步完成', icon:'none' });
    } catch(e) { ui.error(e); }
    finally { this.setData({ syncing:false }); wx.stopPullDownRefresh(); }
  },
  onPullDownRefresh() { return this.refresh(); },
  schedule() { wx.switchTab({ url:'/pages/schedule/index' }); }
});
