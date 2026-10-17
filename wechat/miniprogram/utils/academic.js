const DAY = 86400000;
const pad = x => String(x).padStart(2, '0');
function iso(d = new Date()) { return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function date(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || '');
  if (!m) return null;
  const d = new Date(+m[1], +m[2] - 1, +m[3], 12);
  return iso(d) === m[0] ? d : null;
}
function firstMonday(snapshot, mode) { return wx.getStorageSync('superjlu.monday.' + mode) || snapshot.first_monday || (snapshot.calendar || {}).first_monday || ''; }
function currentWeek(monday, now = new Date()) {
  const start = date(monday);
  if (!start) return 1;
  const today = date(iso(now));
  return Math.floor((today - start) / (DAY * 7)) + 1;
}
function coursesOn(data, week, weekday) {
  return (data.courses || []).filter(c => c.weekday === weekday && c.weeks.includes(week)).sort((a,b) => a.start - b.start);
}
function periodLabel(course, periods) {
  const a = periods[String(course.start)], b = periods[String(course.end)];
  return a && b ? a[0] + ' – ' + b[1] : '第 ' + course.start + '–' + course.end + ' 节';
}
function score(value) {
  const s = String(value).trim();
  const levels = { '优秀': 95, '良好': 85, '中等': 75, '及格': 65, '不及格': 55 };
  if (Object.prototype.hasOwnProperty.call(levels, s)) return levels[s];
  if (!/^(?:\d+(?:\.\d+)?|\.\d+)分?$/.test(s)) return null;
  const n = Number(s.replace('分', '')); return n >= 0 && n <= 100 ? n : null;
}
function point(value) { const n = score(value); return n === null ? null : n < 60 ? 0 : Math.min(4, 1 + (n - 60) / 10); }
function selectedBy(g, template) {
  if (g.builtin && typeof g.builtin[template] === 'boolean') return g.builtin[template];
  if (g.credit <= 0) return false;
  if (template === 'comprehensive') return true;
  if (template === 'scholarship') return /必修/.test(g.nature || '') && !/英语|体育|军事训练/.test(g.name);
  return !/选修|限选/.test(g.nature || '') && !/通用学术英语|体育|军事理论|军事训练/.test(g.name);
}
function weighted(grades, selected) {
  const included = grades.filter(g => selected[g.key] && g.credit > 0 && score(g.score) !== null);
  const credits = included.reduce((v,g) => v + +g.credit, 0);
  // Only failing grades receive the 55 rule; passing grades keep their actual score.
  const adjusted = included.reduce((v,g) => v + (score(g.score) < 60 ? 55 : score(g.score)) * +g.credit, 0);
  const missing = included.some(g => g.point === null || g.point === undefined);
  const sum = included.reduce((v,g) => v + (g.point || 0) * +g.credit, 0);
  return { count: included.length, credits: +credits.toFixed(2), average: credits ? (adjusted / credits).toFixed(2) : '—',
    gpa: credits && !missing ? (sum / credits).toFixed(3) : '—', missing,
    estimated: included.some(g => g.point_source === 'estimated') };
}
function examTime(s) {
  // School times are Asia/Shanghai even when the user's phone is elsewhere.
  return s ? new Date(s.length === 16 ? s + ':00+08:00' : /(?:Z|[+-]\d\d:\d\d)$/.test(s) ? s : s + '+08:00').getTime() : NaN;
}
function examList(exams, now = Date.now()) {
  return (exams || []).map(e => {
    const start = examTime(e.start), end = examTime(e.end || e.start);
    const days = Math.ceil((start - now) / DAY);
    return { ...e, days, past: Number.isFinite(end) && end < now, unknown: !Number.isFinite(start), urgent: Number.isFinite(start) && end >= now && days <= 3,
      countdown: !Number.isFinite(start) ? '时间待定' : end < now ? '已结束' : start < now ? '进行中' : days <= 1 ? '即将开始' : '还有 ' + days + ' 天',
      dateLabel: (e.start || '').replace('T', '  '), sort: Number.isFinite(start) ? start : Infinity };
  }).sort((a,b) => a.sort - b.sort);
}
function weekDays(monday, week) {
  const start = date(monday);
  return Array.from({length:7}, (_,i) => {
    const d = start ? new Date(start.getTime() + ((week-1)*7+i)*DAY) : null;
    return { day: i+1, label: ['一','二','三','四','五','六','日'][i], date: d ? (d.getMonth()+1) + '/' + d.getDate() : '' };
  });
}
module.exports = { iso, date, firstMonday, currentWeek, coursesOn, periodLabel, score, point, selectedBy, weighted, examList, weekDays };
