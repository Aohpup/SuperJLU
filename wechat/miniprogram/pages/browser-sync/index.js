const ui=require('../../utils/ui'),store=require('../../services/store'),sync=require('../../services/phone-sync');
Page({
 data:{agreed:false,error:'',preview:null,imported:false},
 agree(e){this.setData({agreed:e.detail.value.includes('local')});},
 copySchool(){wx.setClipboardData({data:'https://iedu.jlu.edu.cn/jwapp/sys/wdkb/*default/index.do'});},
 copyScript(){wx.setClipboardData({data:require('../../data/phone-bookmark')});},
 paste(){
  this.packet=null;this.setData({error:'',preview:null,imported:false});
  wx.getClipboardData({success:r=>{try{const parsed=sync.parse(r.data);this.packet=parsed.snapshot;this.setData({preview:parsed.preview});}catch(e){this.setData({error:e.message});}},fail:()=>this.setData({error:'未能读取剪贴板，请允许本次粘贴后重试'})});
 },
 apply(){
  if(!this.data.agreed)return this.setData({error:'请先同意仅在本机保存本人教务数据'});
  if(!this.packet)return this.setData({error:'请先粘贴并预览本次结果'});
  if(Date.now()-Date.parse(this.packet.updated)>30*60000)return this.setData({error:'这份结果已超过 30 分钟，请在 Safari 重新读取'});
  const packet=this.packet,p=this.data.preview;
  wx.showModal({title:'导入本次学校数据',content:'课程 '+p.courses+' 条，成绩 '+p.grades+' 条，考试 '+p.exams+' 条。将替换本机原有教务缓存及计算选择；本次失败的模块保持空白。请确认这些数据属于本人。',confirmText:'确认导入',success:r=>{
    if(!r.confirm)return;
    // Replace all modules together, never merge records from different accounts.
    try{
      store.clear();store.write('real',packet);getApp().setMode('real');
      Object.assign(getApp().globalData,{snapshot:packet,schoolLoggedIn:false,offline:false,lastSyncError:''});
      this.packet=null;this.setData({imported:true,error:''});wx.showToast({title:'已导入本次数据',icon:'success'});
    }catch(e){this.setData({error:'本机保存失败，尚未完成导入。请保留 Safari 结果后重试'});}
  }});
 },
 done(){wx.switchTab({url:'/pages/schedule/index'});},
 clearClipboard(){wx.setClipboardData({data:'SuperJLU 手机同步已完成'});},
 onUnload(){this.packet=null;},
 go:ui.go
});
