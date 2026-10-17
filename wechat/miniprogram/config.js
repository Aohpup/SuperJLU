// Default: manually import academic data read in the phone's school browser session.
// No server, cloud environment, WeChat login, or school credentials are required here.
// Other transports are experimental; see README.md before enabling them.
module.exports = {
  transport: 'browser',
  cloudEnv: '',
  cloudService: '',
  apiBase: '',
  requestTimeout: 120000
};
