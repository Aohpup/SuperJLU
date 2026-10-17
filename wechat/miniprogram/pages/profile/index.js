const a=require('../../utils/academic'),ui=require('../../utils/ui'),api=require('../../services/api'),store=require('../../services/store'),config=require('../../config');
Page({
 data:{mode:'demo',busy:false},
 onShow(){
  const s=getApp().globalData,d=s.snapshot||{};
  this.setData({browserOnly:config.transport==='browser',browserSync:d.connectionSource==='phone-browser'});
  this.setData({mode:s.mode,bound:s.schoolLoggedIn,syncError:s.lastSyncError||'',wxConnected:api.hasSession(),hybrid:config.transport==='hybrid',direct:['direct','hybrid'].includes(config.transport),monday:a.firstMonday(d,s.mode),ready:['browser','direct','hybrid'].includes(config.transport)||!!config.apiBase,endpoint:config.transport==='browser'?'手机浏览器导入':config.transport==='hybrid'?'云端认证 + 校园网查询':['direct','hybrid'].includes(config.transport)?'校园网直连':config.apiBase||'尚未配置',updated:ui.timestamp(d.updated)});
 },
 go:ui.go,
 connect(){
  if(config.transport==='browser')return wx.navigateTo({url:'/pages/browser-sync/index'});
  if(!['direct','hybrid'].includes(config.transport)&&!config.apiBase)return ui.error(new Error('请按接入指南填写 miniprogram/config.js 的 apiBase'));
  wx.navigateTo({url:'/pages/login/index'});
 },
 monday(e){
   const value=e.detail.value,d=a.date(value);
   if(!d || d.getDay()!==1)return ui.error(new Error('第一周起始日必须是周一'));
   wx.setStorageSync('superjlu.monday.'+this.data.mode,value);this.onShow();
 },
 resetMonday(){wx.removeStorageSync('superjlu.monday.'+this.data.mode);this.onShow();},
 async refresh(){
  if(config.transport==='browser'||this.data.browserSync)return wx.navigateTo({url:'/pages/browser-sync/index'});
  if(this.data.busy)return;
  this.setData({busy:true});
  try{const data=await getApp().load(true);getApp().globalData.lastSyncError='';this.onShow();wx.showToast({title:data.failures&&data.failures.length?'部分模块未同步，已保留缓存':'同步完成',icon:'none'});}catch(e){getApp().globalData.lastSyncError=e.message;this.onShow();ui.error(e);}finally{this.setData({busy:false});}
 },
 demo(){getApp().setMode('demo');this.onShow();},
 async logout(){
  wx.showModal({title:'清除教务数据',content:this.data.browserSync||config.transport==='browser'?'清除此设备保存的教务数据、计算选择和自定义校历。再次使用请重新导入。':config.transport==='hybrid'?'清除云端认证会话，以及此设备的教务会话和缓存。下次使用需要重新绑定。':['direct','hybrid'].includes(config.transport)?'清除此设备的教务会话与缓存，下次使用需要重新绑定。':'清除服务端的教务会话与缓存，以及此设备的教务缓存。下次使用需要重新绑定。',confirmText:'清除',success:async r=>{
    if(!r.confirm)return;
    this.setData({busy:true});
    try{if(!this.data.browserSync)await api.request('/api/logout');store.clear();getApp().setMode('real');this.onShow();wx.showToast({title:'已清除',icon:'success'});}
    catch(e){ui.error(new Error('清除未完成：'+e.message));}
    finally{this.setData({busy:false});}
  }});
 },
 clearLocal(){store.clear();if(this.data.mode==='real')getApp().globalData.snapshot=store.empty();this.onShow();wx.showToast({title:'本地缓存已清除',icon:'none'});}
 ,copyDiagnostic(){const detail=require('../../services/direct').diagnostics();wx.setClipboardData({data:JSON.stringify({transport:config.transport,error:getApp().globalData.lastSyncError||'',query:detail},null,2)});}
});
