// Runs only when the user selects their Safari bookmark on the school page.
// No cloud endpoint, document.cookie, credentials collection, or remote code.
module.exports=async function phoneBrowserSync(SchoolData){
  'use strict';
  const ORIGIN='https://iedu.jlu.edu.cn',START=ORIGIN+'/jwapp/sys/wdkb/*default/index.do';
  if(location.origin!==ORIGIN||!location.pathname.startsWith('/jwapp/sys/wdkb/')){
    alert('请先在 Safari 打开学校课表页面并完成学校登录：\n'+START+'\n然后再点“同步到 SuperJLU”书签。');return;
  }
  if(document.getElementById('superjlu-phone-sync')){alert('同步窗口已打开，请先完成或关闭。');return;}
  const panel=document.createElement('section');panel.id='superjlu-phone-sync';
  panel.setAttribute('style','position:fixed;inset:12px;z-index:2147483647;background:#f5f8f7;color:#203a35;padding:24px;border:1px solid #aabfb7;border-radius:18px;overflow:auto;font:16px/1.7 -apple-system,sans-serif;box-sizing:border-box');
  const title=document.createElement('h2');title.textContent='同步到 SuperJLU';panel.appendChild(title);
  const message=document.createElement('p');message.textContent='正在从学校读取本次数据…请保持 Safari 前台。';panel.appendChild(message);
  const note=document.createElement('p');note.textContent='仅查询学校；登录由学校页面完成。结果留在本机，由你复制回小程序。';panel.appendChild(note);
  const close=document.createElement('button');close.textContent='关闭';close.onclick=()=>{cancelled=true;panel.remove();};panel.appendChild(close);document.documentElement.appendChild(panel);
  let cancelled=false;
  const fail=message=>new Error(message);
  const apps=new Set(['wdkb','cjcx','studentWdksapApp','xsfacx','xywccx']);
  const index=app=>ORIGIN+'/jwapp/sys/'+app+'/*default/index.do';
  class BrowserClient{
    constructor(){this.active='wdkb';}
    requireLogin(){if(cancelled)throw Object.assign(fail('已取消同步'),{code:'LOGIN_CANCELLED'});}
    async enter(app){
      this.requireLogin();if(!apps.has(app))throw fail('不支持的学校应用');if(this.active===app)return;
      message.textContent='正在读取学校 '+({cjcx:'成绩',studentWdksapApp:'考试',xsfacx:'培养方案',xywccx:'学业完成',wdkb:'课表'}[app]||app)+'…';
      // Normal same-site SSO in a school-origin frame. Never submit a form.
      const frame=document.createElement('iframe');frame.hidden=true;frame.src=index(app);
      try{
        await new Promise((resolve,reject)=>{
          const timer=setTimeout(()=>reject(fail('学校应用初始化超时')),10000);
          frame.onload=()=>{clearTimeout(timer);resolve();};
          frame.onerror=()=>{clearTimeout(timer);reject(fail('学校应用未能载入'));};
          panel.appendChild(frame);
        });
        this.requireLogin();this.active=app;
      }finally{frame.remove();}
    }
    async query(app,relative,values={},key='',paged=false){
      this.requireLogin();if(!apps.has(app)||!/^[A-Za-z0-9_/*]+\.do$/.test(relative)||relative.includes('..'))throw fail('查询地址异常');
      const rows=[];for(let page=1;page<=20;page++){
        this.requireLogin();const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
        let response,obj;
        try{
          response=await fetch(ORIGIN+'/jwapp/sys/'+app+'/'+relative,{method:'POST',credentials:'same-origin',cache:'no-store',referrer:index(app),signal:controller.signal,
            headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Accept':'application/json, text/javascript, */*; q=0.01'},
            body:new URLSearchParams(paged?{...values,pageSize:'200',pageNumber:String(page)}:values).toString()});
          if(!response.ok)throw fail('学校查询返回 HTTP '+response.status+'（'+app+'）');
          const text=await response.text();if(text.length>2*1024*1024)throw fail('学校返回数据过大');obj=JSON.parse(text);
        }catch(e){throw fail('未取得 '+app+'/'+key+' 数据，请确认 Safari 里的学校登录仍有效。'+(response&&!response.ok?' HTTP '+response.status:''));}
        finally{clearTimeout(timer);}
        const block=obj&&obj.datas&&obj.datas[key];
        if(!block||!Array.isArray(block.rows))throw fail('学校拒绝 '+app+'/'+key+' 查询（code='+String(obj&&obj.code||'未知').slice(0,40)+'）');
        rows.push(...block.rows);if(rows.length>2000)throw fail('学校查询结果过多，已停止');
        const total=Number(block.totalSize);if(!paged||!block.rows.length||block.rows.length<200||total>0&&rows.length>=total)return rows;
        if(page===20)throw fail('学校分页尚未结束');
      }return rows;
    }
  }
  try{
    const reader=new SchoolData(new BrowserClient());
    const data=await reader.refresh({courses:[],grades:[],exams:[],calendar:{},periods:{},completion:null,plan_courses:null,official_gpa:null,updated:null});
    if(cancelled)return;
    if(!data.module_updated.courses)throw fail('本次课表未读到，未生成导入结果；请保持学校课表页已登录。');
    // SchoolData exports selected academic fields; its temporary student-ID
    // context and all browser cookies stay out of this packet.
    const text='SUPERJLU-PHONE-1\n'+JSON.stringify({version:1,origin:ORIGIN,capturedAt:data.updated,data});
    message.textContent='本次读取完成：课程 '+data.courses.length+' 条，成绩 '+data.grades.length+' 条，考试 '+data.exams.length+' 条。'+(data.failures.length?'未读到 '+data.failures.length+' 个模块，可在小程序查看。':'');
    const area=document.createElement('textarea');area.readOnly=true;area.value=text;area.setAttribute('style','width:100%;height:160px;font-size:14px;box-sizing:border-box');area.setAttribute('aria-label','同步结果');panel.appendChild(area);
    const copy=document.createElement('button');copy.textContent='复制本次结果，回小程序导入';copy.setAttribute('style','display:block;background:#167c67;color:white;border:0;border-radius:12px;padding:16px;margin:16px 0');
    copy.onclick=async()=>{
      try{if(navigator.clipboard&&navigator.clipboard.writeText)await navigator.clipboard.writeText(text);else{area.focus();area.select();if(!document.execCommand('copy'))throw fail('copy');}copy.textContent='已复制，请回小程序粘贴预览';}
      catch(e){area.focus();area.select();copy.textContent='请长按结果框，全选并复制';}
    };panel.appendChild(copy);note.textContent='结果包含本人的课表和成绩，请只粘贴到自己的小程序；导入成功后可清空剪贴板。不会发送到云服务器。';
  }catch(e){if(!cancelled)message.textContent='同步未完成：'+e.message+'。没有生成成功结果。';}
};
