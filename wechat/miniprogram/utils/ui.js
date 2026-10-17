function error(e) { wx.showToast({ title: e.message || '操作失败，请重试', icon: 'none', duration: 3000 }); }
function go(e) { wx.navigateTo({ url: '/pages/' + e.currentTarget.dataset.page + '/index' }); }
function copy(e) { const data = e.currentTarget.dataset.url; if (data) wx.setClipboardData({ data }); }
function state() { return getApp().globalData; }
function timestamp(value){const d=new Date(value||'');if(!Number.isFinite(d.getTime()))return '尚未同步';const p=n=>String(n).padStart(2,'0');return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+' '+p(d.getHours())+':'+p(d.getMinutes());}
module.exports = { error, go, copy, state, timestamp };
