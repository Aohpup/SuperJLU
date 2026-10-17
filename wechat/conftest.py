"""Keep the optional backend's vendored package bindings out of upstream pytest.

Run that suite in its own interpreter with:
python -m unittest discover -s wechat/server -p 'test_*.py'
The WeChat CI job runs this command separately from the desktop suite.
"""
collect_ignore = ["server/test_app.py"]
