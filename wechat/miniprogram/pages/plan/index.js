Page({
 data:{groups:[],courses:[],filters:['全部','已修','在修','未修'],filter:'全部'},
 onShow(){const s=getApp().globalData,d=s.snapshot||{},c=d.completion||{};this.all=(d.plan_courses||{}).courses||[];this.setData({mode:s.mode,plan:c.plan||'学业完成进度',required:c.required===null||c.required===undefined?'—':c.required,earned:c.earned===null||c.earned===undefined?'—':c.earned,progress:c.required && c.earned!==null ? Math.max(0,Math.min(100,Math.round(c.earned/c.required*100))) :0,groups:c.groups||[]});this.render();},
 filter(e){this.setData({filter:e.currentTarget.dataset.filter});this.render();},
 render(){this.setData({courses:this.all.filter(c=>this.data.filter==='全部'||c.status===this.data.filter)});}
});
