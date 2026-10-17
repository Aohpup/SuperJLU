const a=require('../../utils/academic'),ui=require('../../utils/ui'),api=require('../../services/api');
const campuses=['前卫校区','南岭校区','新民校区','朝阳校区','南湖校区','和平校区'];
Page({
 data:{campuses,campusIndex:0,date:a.iso(),periods:['1-2','3-4','5-6','7-8','9-10','11'],periodIndex:0,seats:'',buildings:[{code:'',name:'全部教学楼'}],buildingIndex:0,rooms:[],queried:false,busy:false},
 onShow(){this.setData({mode:getApp().globalData.mode});},
 async campus(e){
  const campusIndex=Number(e.detail.value);this.setData({campusIndex,buildings:[{code:'',name:'全部教学楼'}],buildingIndex:0,rooms:[],queried:false});
  if(this.data.mode==='real'){
   try{const r=await api.request('/api/rooms/buildings','POST',{campus:String(campusIndex+1).padStart(2,'0')});if(this.data.campusIndex===campusIndex)this.setData({buildings:[{code:'',name:'全部教学楼'},...(r.buildings||[])]});}catch(err){ui.error(err);}
  }
 },
 date(e){this.setData({date:e.detail.value,queried:false});},
 period(e){this.setData({periodIndex:Number(e.detail.value),queried:false});},
 seats(e){this.setData({seats:e.detail.value,queried:false});},
 building(e){this.setData({buildingIndex:Number(e.detail.value),queried:false});},
 async query(){
  if(this.data.busy)return;
  const minimum=Number(this.data.seats||0);if(!Number.isInteger(minimum)||minimum<0||minimum>2000)return ui.error(new Error('座位数应为 0–2000 的整数'));
  this.setData({busy:true,rooms:[],queried:false});
  try{
   const d=this.data;
   const body={campus:String(d.campusIndex+1).padStart(2,'0'),date:d.date,periods:d.periods[d.periodIndex],seat_min:minimum,building:d.buildings[d.buildingIndex].code};
   let rooms;
   if(d.mode==='demo'){
    rooms=[{name:'A101',building:'逸夫楼',seats:96},{name:'B203',building:'经信楼',seats:120},{name:'C305',building:'公教楼',seats:60}].filter(r=>r.seats>=minimum).map(r=>({...r,campus:campuses[d.campusIndex],free_periods:body.periods}));
   }else rooms=(await api.request('/api/rooms','POST',body)).rooms||[];
   this.setData({rooms,queried:true});
  }catch(e){ui.error(e);}finally{this.setData({busy:false});}
 }
});
