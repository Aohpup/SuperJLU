const ui=require('../../utils/ui');
Page({
 data:{links:require('../../data/links')},
 onShow(){this.setData({mode:getApp().globalData.mode});},
 go:ui.go, copy:ui.copy,
 openLink(e){
   const link=this.data.links[Number(e.currentTarget.dataset.i)];
   wx.showModal({title:link.name,content:link.purpose+'\n'+(link.campus_only?'部分网络需要校园网或学校 VPN。\n':'')+'复制地址后，在浏览器中访问并完成学校登录。',confirmText:'复制地址',success:r=>{if(r.confirm)wx.setClipboardData({data:link.url});}});
 }
});
