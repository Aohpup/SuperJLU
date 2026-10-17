const sample = require('../data/demo');
const empty = () => ({ courses: [], grades: [], exams: [], calendar: {}, periods: {}, completion: null, updated: null });
const demo = () => JSON.parse(JSON.stringify(sample));
function read(mode) { return mode === 'demo' ? demo() : wx.getStorageSync('superjlu.cache.real') || empty(); }
function write(mode, value) { wx.setStorageSync('superjlu.cache.' + mode, value); }
function clear() {
  ['superjlu.cache.real', 'superjlu.monday.real', 'superjlu.selection.real', 'superjlu.schemes.real', 'superjlu.import.real'].forEach(k => wx.removeStorageSync(k));
}
module.exports = { demo, read, write, clear, empty };
