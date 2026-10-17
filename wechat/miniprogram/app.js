const api = require('./services/api');
const store = require('./services/store');
App({
  globalData: { mode: 'real', snapshot: null, offline: false, schoolLoggedIn: false },
  onLaunch() {
    const mode = wx.getStorageSync('superjlu.mode') || 'real';
    this.globalData.mode = mode === 'real' ? 'real' : 'demo';
    this.globalData.snapshot = store.read(this.globalData.mode);
    if(this.globalData.snapshot.connectionSource!=='phone-browser'&&['direct','hybrid'].includes(require('./config').transport)) {
      api.reset();
      // Anonymous reachability check only; never submit credentials at startup.
      this.checkSchoolNetwork();
    }
  },
  checkSchoolNetwork() {
    if(require('./config').transport==='hybrid'&&!wx.getStorageSync('superjlu.hybridConsent')) {
      const result={ok:false,message:'请先在绑定页面同意云端认证隐私说明，再检测校园网连接'};
      this.globalData.directNetwork=result;return Promise.resolve(result);
    }
    const task=require('./services/direct').probe().then(result=>result,error=>({ok:false,message:error.message,code:error.code})).then(result=>{
      if(this.globalData.directNetworkCheck===task)this.globalData.directNetwork=result;
      return result;
    });
    this.globalData.directNetworkCheck=task;
    return task;
  },
  setMode(mode) {
    api.reset();
    this.globalData = { mode, snapshot: store.read(mode), offline: false, schoolLoggedIn: false };
    wx.setStorageSync('superjlu.mode', mode);
  },
  async load(refresh = false) {
    if (this.globalData.mode === 'demo') {
      this.globalData.snapshot = store.demo();
      return this.globalData.snapshot;
    }
    if((this.globalData.snapshot||{}).connectionSource==='phone-browser'){
      if(refresh){const e=new Error('请在手机 Safari 重新读取学校数据后导入');e.code='PHONE_BROWSER_REQUIRED';throw e;}
      this.globalData.schoolLoggedIn=false;this.globalData.offline=false;return this.globalData.snapshot;
    }
    try {
      const data = refresh ? await api.sync() : await api.request('/api/data', 'GET');
      const session = await api.request('/api/session', 'GET');
      this.globalData.schoolLoggedIn = !!session.logged_in;
      this.globalData.snapshot = data;
      this.globalData.offline = false;
      store.write('real', data);
      return data;
    } catch (error) {
      this.globalData.offline = !!(this.globalData.snapshot && this.globalData.snapshot.updated);
      if (eIsSchoolExpiry(error)) this.globalData.schoolLoggedIn = false;
      if (!refresh && this.globalData.snapshot) return this.globalData.snapshot;
      throw error;
    }
  }
});
function eIsSchoolExpiry(error) { return error.code === 'SCHOOL_SESSION_EXPIRED'; }
