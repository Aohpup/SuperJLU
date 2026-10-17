const a=require('../../utils/academic');
Page({
 data:{items:[],showPast:false},
 onShow(){this.render();},
 render(){const s=getApp().globalData,all=a.examList((s.snapshot||{}).exams);this.setData({mode:s.mode,items:all.filter(e=>this.data.showPast||!e.past)});},
 past(){this.setData({showPast:!this.data.showPast});this.render();}
});
