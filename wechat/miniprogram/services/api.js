const config = require('../config');
let token = '', expires = 0, pending, cloudInitialized = false;
const localSchool=()=>['direct','hybrid'].includes(config.transport);
function browserRequired() {
  const error = new Error('请在手机浏览器读取学校数据后，通过「手机浏览器同步」导入');
  error.code = 'PHONE_BROWSER_REQUIRED';
  return error;
}
function reset() { token = ''; expires = 0; pending = null; if(localSchool())require('./direct').reset(); }
function base() {
  const local = /^http:\/\/127\.0\.0\.1:\d+$/.test(config.apiBase);
  const devtools = typeof wx.getDeviceInfo === 'function' && wx.getDeviceInfo().platform === 'devtools';
  if (!/^https:\/\/[^/]+/.test(config.apiBase) && !(local && devtools)) throw new Error('手机运行需要在 config.js 配置 HTTPS 服务地址；本机 HTTP 仅支持开发者工具');
  return config.apiBase.replace(/\/$/, '');
}
function send(path, method, data, authorization) {
  if (['cloudrun','hybrid'].includes(config.transport)) {
    if (!wx.cloud || typeof wx.cloud.callContainer !== 'function') return Promise.reject(new Error('当前微信版本不支持云托管，请更新微信或开发者工具'));
    if (!cloudInitialized) { wx.cloud.init({ env: config.cloudEnv, traceUser: false }); cloudInitialized = true; }
    return wx.cloud.callContainer({ config: { env: config.cloudEnv }, path, method, data,
      timeout: config.requestTimeout,
      header: { 'X-WX-SERVICE': config.cloudService, 'Content-Type': 'application/json', Authorization: authorization ? 'Bearer ' + authorization : '' }
    }).then(res => {
      const body = res.data || {};
      if (res.statusCode >= 200 && res.statusCode < 300 && body.ok !== false) return body;
      const e = new Error(body.error || '云托管服务暂时不可用'); e.code = body.code; throw e;
    }, () => { throw new Error('无法连接微信云托管，请检查环境与服务配置'); });
  }
  return new Promise((resolve, reject) => wx.request({
    url: base() + path, method, data,
    timeout: config.requestTimeout,
    header: { 'Content-Type': 'application/json', Authorization: authorization ? 'Bearer ' + authorization : '' },
    success(res) {
      const body = res.data || {};
      if (res.statusCode >= 200 && res.statusCode < 300 && body.ok !== false) resolve(body);
      else {
        const e = new Error(body.error || '服务暂时不可用');
        e.code = body.code; reject(e);
      }
    },
    fail() { reject(new Error('网络连接失败，请检查网络和服务地址')); }
  }));
}
async function login() {
  if (config.transport === 'browser') throw browserRequired();
  if (!wx.getStorageSync('superjlu.consent')) throw new Error('请在绑定教务页面阅读并同意隐私说明');
  if (config.transport==='hybrid'&&!wx.getStorageSync('superjlu.hybridConsent')) throw new Error('请在绑定页面同意云端认证隐私说明后再检测连接');
  if (token && expires > Date.now() + 30000) return token;
  if (!pending) pending = (async () => {
    if (['cloudrun','hybrid'].includes(config.transport)) {
      const result = await send('/api/wechat/cloud-login', 'POST', {});
      token = result.token; expires = Date.now() + result.expires_in * 1000;
      return token;
    }
    const code = await new Promise((resolve, reject) => wx.login({
      success(res) { res.code ? resolve(res.code) : reject(new Error('微信登录失败')); },
      fail() { reject(new Error('微信登录失败')); }
    }));
    const result = await send('/api/wechat/login', 'POST', { code });
    token = result.token; expires = Date.now() + result.expires_in * 1000;
    return token;
  })().finally(() => { pending = null; });
  return pending;
}
async function request(path, method = 'POST', data = {}) {
  if (config.transport === 'browser') {
    const store = require('./store');
    if (path === '/api/data' && method === 'GET') return store.read('real');
    if (path === '/api/session' && method === 'GET') return { logged_in: false };
    if (path === '/api/logout') { reset(); store.clear(); return { ok: true }; }
    throw browserRequired();
  }
  if(localSchool())return require('./direct').request(path,method,data);
  return cloudRequest(path,method,data);
}
async function cloudRequest(path,method='POST',data={}) {
  const t = await login();
  try { return await send(path, method, data, t); }
  catch (e) {
    // Only an expired WeChat token is retried. A CAS expiry needs a new school login.
    if (e.code === 'TOKEN_EXPIRED') { reset(); return send(path, method, data, await login()); }
    throw e;
  }
}
async function sync() {
  if (config.transport === 'browser') throw browserRequired();
  if(localSchool())return require('./direct').sync();
  const job = await request('/api/refresh');
  const end = Date.now() + 8 * 60 * 1000;
  while (Date.now() < end) {
    const status = await request('/api/refresh/status', 'GET');
    if (status.job_id !== job.job_id) throw new Error('同步任务已改变，请重新同步');
    if (status.status === 'done') return status.data;
    if (status.status === 'error') { const e=new Error(status.error);e.code=status.code;throw e; }
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
  throw new Error('同步仍在服务器进行中，请稍后重新加载');
}
module.exports = { request, sync, reset, cloudRequest, hasSession: () => localSchool()?require('./direct').hasSession():!!token && expires > Date.now() };
