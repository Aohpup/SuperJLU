const a = require('../../utils/academic');
const ui = require('../../utils/ui');
Page({
  data: { week:1, layout:'week', days:[], courses:[], periods:[], conflicts:[] },
  onShow() {
    const s = getApp().globalData;
    this.snapshot = s.snapshot || {};
    const monday = a.firstMonday(this.snapshot, s.mode);
    this.monday = monday;
    const current = a.currentWeek(monday);
    this.setData({ mode:s.mode, current, maxWeeks:(this.snapshot.calendar || {}).total_weeks || 20,
      week:Math.max(1,Math.min(current,(this.snapshot.calendar || {}).total_weeks || 20)), hasMonday:!!monday });
    this.render();
  },
  render() {
    const d = this.snapshot, week=this.data.week;
    const courses=(d.courses || []).filter(c => c.weeks.includes(week)).map((c,i)=>({
      ...c, id:i, time:a.periodLabel(c,d.periods || {}), weekdayLabel:'周'+['','一','二','三','四','五','六','日'][c.weekday],
      style:'grid-column:'+(c.weekday+1)+';grid-row:'+c.start+'/span '+(c.end-c.start+1)+';',
      color:'tone'+(i%5)
    }));
    const conflicts=courses.filter((c,i)=>courses.some((b,j)=>i!==j && c.weekday===b.weekday && c.start<=b.end && b.start<=c.end)).map(c=>c.name);
    this.setData({ days:a.weekDays(this.monday,week), courses,
      periods:Array.from({length:Math.max(11,...courses.map(c=>c.end))},(_,i)=>({n:i+1,time:(d.periods || {})[i+1] ? d.periods[i+1][0] : ''})),
      conflicts:[...new Set(conflicts)], empty:!courses.length });
  },
  changeWeek(e) {
    const week=this.data.week+Number(e.currentTarget.dataset.delta);
    if(week>=1 && week<=this.data.maxWeeks) { this.setData({week});this.render(); }
  },
  thisWeek() { this.setData({week:Math.max(1,Math.min(this.data.current,this.data.maxWeeks))});this.render(); },
  layout(e) { this.setData({ layout:e.currentTarget.dataset.layout }); },
  detail(e) {
    const c=this.data.courses[Number(e.currentTarget.dataset.id)];
    wx.showModal({ title:c.name, content:c.weekdayLabel+' · '+c.time+'\n'+c.location+'\n教师：'+c.teacher+'\n周次：'+c.weeks.join('、'), showCancel:false });
  },
  go:ui.go
});
