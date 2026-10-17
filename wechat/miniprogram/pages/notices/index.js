const ui=require('../../utils/ui'),api=require('../../services/api');
Page({
 data:{sources:['软件学院 · 学院通知','计算机学院 · 学院通知','OA · 校内通知'],sourceIndex:0,keyword:'',items:[],busy:false,hint:''},
 onShow(){this.setData({mode:getApp().globalData.mode});this.query();},
 source(e){this.setData({sourceIndex:Number(e.detail.value)});this.query();},
 keyword(e){this.setData({keyword:e.detail.value});},
 async query(){
  if(this.data.busy)return;this.setData({busy:true,items:[],hint:''});
  try{
   let result;
   if(this.data.mode==='demo'){
    const source=this.data.sources[this.data.sourceIndex];
    result={items:[{id:'demo1',title:'关于本学期教学安排的通知（示例）',time:'2026-10-15',dept:source,url:''},{id:'demo2',title:'学术讲座与校园活动预告（示例）',time:'2026-10-14',dept:source,url:''}].filter(i=>!this.data.keyword || i.title.includes(this.data.keyword))};
   }else result=await api.request('/api/notices','POST',{category:['csw-xytz','ccst-xytz','179577'][this.data.sourceIndex],keyword:this.data.keyword});
   this.setData({items:result.items||[],hint:result.hint||''});
  }catch(e){this.setData({hint:e.message});ui.error(e);}finally{this.setData({busy:false});}
 },
 detail(e){const item=this.data.items[Number(e.currentTarget.dataset.i)];wx.showModal({title:item.title,content:item.dept+'\n'+item.time+(item.url?'\n复制原文地址，在浏览器查看通知。':'\n这是一条演示通知。'),confirmText:item.url?'复制原文':'知道了',showCancel:!!item.url,success:r=>{if(r.confirm&&item.url)wx.setClipboardData({data:item.url});}});}
});
