// Native JS port of the pinned upstream des_tpass.py (MIT). See THIRD_PARTY_NOTICES.md.
// School TPASS requires this legacy wire format in addition to HTTPS.
const T = require('./des-tables');
const permute = (bits, positions) => positions.map(i => bits[i]);
function bits(text) {
  const out = [];
  for (let i=0;i<4;i++) { const c=text.charCodeAt(i)||0; for(let j=15;j>=0;j--)out.push((c>>>j)&1); }
  return out;
}
function schedule(key) {
  let k=permute(bits(key),T.pc1); const result=[];
  for(const shift of T.shifts) {
    const a=k.slice(0,28),b=k.slice(28);
    k=a.slice(shift).concat(a.slice(0,shift),b.slice(shift),b.slice(0,shift));
    result.push(permute(k,T.pc2));
  }
  return result;
}
function encrypt(block, keys) {
  const initial=permute(block,T.ip); let left=initial.slice(0,32),right=initial.slice(32);
  for(const key of keys) {
    const e=permute(right,T.expand).map((b,i)=>b^key[i]),sub=[];
    for(let i=0;i<8;i++) {
      const p=i*6,row=e[p]*2+e[p+5],col=e[p+1]*8+e[p+2]*4+e[p+3]*2+e[p+4];
      const n=T.sboxes[i][row][col];for(let j=3;j>=0;j--)sub.push((n>>>j)&1);
    }
    const next=permute(sub,T.p).map((b,i)=>b^left[i]);left=right;right=next;
  }
  return permute(right.concat(left),T.fp);
}
function strEnc(text, first='1',second='2',third='3') {
  const keys=[];for(const s of [first,second,third])for(let i=0;i<s.length;i+=4)keys.push(schedule(s.slice(i,i+4)));
  let out='';for(let i=0;i<text.length;i+=4) {
    let b=bits(text.slice(i,i+4));for(const key of keys)b=encrypt(b,key);
    for(let j=0;j<64;j+=4)out+=(b[j]*8+b[j+1]*4+b[j+2]*2+b[j+3]).toString(16).toUpperCase();
  }
  return out;
}
module.exports={strEnc};
