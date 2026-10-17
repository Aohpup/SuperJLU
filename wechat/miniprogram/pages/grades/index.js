const a = require('../../utils/academic');
const ui = require('../../utils/ui');
Page({
  data: { search:'', terms:['全部学期'], termIndex:0, template:'comprehensive', source:'school', schemes:[], visible:[], summary:{} },
  onShow() {
    this.mode=getApp().globalData.mode;
    this.schoolGrades=(getApp().globalData.snapshot || {}).grades || [];
    this.grades=this.schoolGrades;
    this.selected=wx.getStorageSync('superjlu.selection.'+this.mode) || {};
    const schemes=wx.getStorageSync('superjlu.schemes.'+this.mode) || [];
    this.setData({ mode:this.mode, source:'school', schemes, search:'', termIndex:0, importedAvailable:!!wx.getStorageSync('superjlu.import.'+this.mode) });
    this.setTerms();
    this.grades.forEach(g=>{if(typeof this.selected[g.key]!=='boolean')this.selected[g.key]=a.selectedBy(g,'comprehensive');});
    this.render();
  },
  setTerms(){this.setData({ terms:['全部学期',...new Set(this.grades.map(g=>g.term).filter(Boolean))],termIndex:0 });},
  render() {
    const query=this.data.search.toLowerCase(), term=this.data.terms[this.data.termIndex];
    const visible=this.grades.filter(g=>(!query || g.name.toLowerCase().includes(query)) && (!this.data.termIndex || g.term===term))
      .map(g=>({...g,checked:!!this.selected[g.key],failed:a.score(g.score)!==null && a.score(g.score)<60,
        pointLabel:g.point===null || g.point===undefined ? '—' : Number(g.point).toFixed(1),
        counted:a.score(g.score)!==null, creditLabel:g.credit+' 学分'}));
    this.setData({ visible, summary:a.weighted(this.grades,this.selected) });
    if(this.data.source==='school')wx.setStorageSync('superjlu.selection.'+this.mode,this.selected);
  },
  search(e){this.setData({search:e.detail.value});this.render();},
  term(e){this.setData({termIndex:Number(e.detail.value)});this.render();},
  template(e){
    const template=e.currentTarget.dataset.template;this.selected={};
    this.grades.forEach(g=>{this.selected[g.key]=a.selectedBy(g,template);});
    this.setData({template});this.render();
  },
  toggle(e){const k=e.currentTarget.dataset.key;this.selected[k]=!this.selected[k];this.setData({template:'custom'});this.render();},
  save(){
    wx.showModal({title:'保存计算方案',editable:true,placeholderText:'例如：大二奖学金',
      success:res=>{
        if(!res.confirm || !res.content || !res.content.trim())return;
        const scheme={name:res.content.trim().slice(0,30),keys:this.grades.filter(g=>this.selected[g.key]).map(g=>g.key)};
        const schemes=[...this.data.schemes.filter(s=>s.name!==scheme.name),scheme].slice(-20);
        wx.setStorageSync('superjlu.schemes.'+this.mode,schemes);this.setData({schemes});
        wx.showToast({title:'已保存',icon:'success'});
      }
    });
  },
  useScheme(e){
    const scheme=this.data.schemes[Number(e.currentTarget.dataset.i)];
    this.selected={};this.grades.forEach(g=>{this.selected[g.key]=scheme.keys.includes(g.key);});
    this.setData({template:'custom'});this.render();
  },
  async importFile() {
    wx.chooseMessageFile({count:1,type:'file',extension:['csv'],success:res=>{
      const f=res.tempFiles[0];
      if(f.size>5*1024*1024)return ui.error(new Error('成绩单不能超过 5 MB'));
      wx.getFileSystemManager().readFile({filePath:f.path,encoding:'utf8',success:r=>{
        try{
          const grades=require('../../utils/csv').parseGrades(r.data);
          wx.setStorageSync('superjlu.import.'+this.mode,grades);this.showImport();
        }catch(e){ui.error(e);}
      },fail(){ui.error(new Error('读取文件失败'));}});
    },fail(){}});
  },
  showImport(){
    this.grades=wx.getStorageSync('superjlu.import.'+this.mode) || [];
    this.selected={};this.grades.forEach(g=>{this.selected[g.key]=true;});
    this.setData({source:'import',importedAvailable:true,template:'comprehensive',search:''});this.setTerms();this.render();
  },
  school(){
    this.grades=this.schoolGrades;this.selected=wx.getStorageSync('superjlu.selection.'+this.mode)||{};
    this.setData({source:'school',template:'custom',search:''});this.setTerms();this.render();
  }
});
