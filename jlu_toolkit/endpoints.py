"""已在吉大教务（iedu.jlu.edu.cn，金智 EMAP）上验证可用的接口清单 —— 唯一事实来源。

取数路径优先用这里的已知接口；只有失败或返回为空时才回退到 emap 发现（discover + 元数据）。
params 只记录参数「名」与固定值；XH / PYFADM 等个人值运行时从会话上下文注入，绝不落盘。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

HOST = "https://iedu.jlu.edu.cn"

# 绝不写入任何本地文件/报告的个人字段
PRIVATE_KEYS = frozenset({"XH", "XM", "WID", "PYFADM", "SFZJH", "SJHM", "DZYX"})
MAX_TOTAL = 2000  # 单接口 totalSize 超过即视为未过滤（全校数据），拒绝且绝不翻页


@dataclass(frozen=True)
class Endpoint:
    app: str                  # EMAP 应用名（/jwapp/sys/<app>/）
    path: str                 # 绝对路径
    datas_key: str = ""       # datas.<key>.rows
    fixed: dict = field(default_factory=dict)   # 固定参数
    ctx: tuple = ()           # 需从上下文注入的参数名（如 XH、PYFADM）
    query_setting: tuple = () # 以 querySetting JSON 传入的上下文参数名
    paged: bool = False       # 支持 pageSize/pageNumber
    referer_hash: str = ""    # Referer 的 #/route（部分接口需要）
    note: str = ""

    @property
    def index(self) -> str:
        return f"{HOST}/jwapp/sys/{self.app}/*default/index.do"

    @property
    def referer(self) -> str:
        return self.index + "?EMAP_LANG=zh"  # 浏览器不会发送 #片段；与发现路径一致


def _e(app, rel, key="", **kw) -> Endpoint:
    return Endpoint(app, f"/jwapp/sys/{app}/{rel}", key, **kw)


KNOWN: dict[str, Endpoint] = {
    # —— 课表 / 成绩 / 考试（jwxt.py 一直在用）——
    "current_term": _e("wdkb", "modules/jshkcb/dqxnxq.do", "dqxnxq"),
    "schedule": _e("wdkb", "modules/xskcb/cxxszhxqkb.do", "cxxszhxqkb", ctx=("XNXQDM",)),
    "grades": _e("cjcx", "modules/cjcx/xscjcx.do", "xscjcx", paged=True),
    "exams": _e("studentWdksapApp", "WdksapController/cxxsksap.do", "cxxsksap"),
    "exams_alt": _e("studentWdksapApp", "modules/wdksap/wdksap.do", "wdksap"),
    # —— 校历 / 节次（meta.py）——
    "calendar": _e("wdkb", "modules/xskcb/cxxljc.do", "cxxljc"),
    "periods": _e("wdkb", "modules/jshkcb/jc.do", "jc"),
    # —— 官方 GPA：literal '*'（%2A 为回退，两者在 PC 上均验证过）——
    "official_gpa": _e("cjcx", "modules*cjcx/rxylgpacx/rxylgpacxcx.do", "rxylgpacxcx",
                       fixed={"pageSize": "10", "pageNumber": "1"}, referer_hash=""),
    "official_gpa_enc": _e("cjcx", "modules%2Acjcx/rxylgpacx/rxylgpacxcx.do", "rxylgpacxcx",
                           fixed={"pageSize": "10", "pageNumber": "1"}),
    # —— 空教室 kxjas（前端路由 #/kxjscx）——
    "rooms_query": _e("kxjas", "modules/kxjscx/cxkxjs.do", "cxkxjs", paged=True, referer_hash="kxjscx",
                      note="参数由 kxjscx 元数据检索字段决定（XXXQDM/KXRQ/节次/座位…），见 rooms.py"),
    "rooms_meta": _e("kxjas", "modules/kxjscx.do", note="GET ?*json=1：字段/检索字段/字典 URL"),
    # —— 学业完成 xywccx ——
    "completion": _e("xywccx", "modules/xywccx/cxxsscfa.do", "cxxsscfa", fixed={"SCLBDM": "04", "*order": "-CZSJ"}),
    "completion_groups": _e("xywccx", "modules/xywccx/cxscfakz.do", "cxscfakz",
                            ctx=("XH", "PYFADM", "BYNJDM", "SCLBDM")),
    "student_info": _e("xywccx", "modules/xywccx/cxxsjbxx.do", "cxxsjbxx", fixed={"pageSize": "10", "pageNumber": "1"}),
    "student_plan": _e("xywccx", "modules/xywccx/cxscfa.do", "cxscfa", fixed={"pageSize": "10", "pageNumber": "1"}),
    "plan_courses": _e("xywccx", "modules/xywccx/cxscfakzkc.do", "cxscfakzkc", ctx=("XH", "PYFADM"), paged=True),
    # —— 个人培养方案 xsfacx（前端路由 #/ckgrpyfa）——
    "plan_row": _e("xsfacx", "modules/pyfacxepg/grpyfacx.do", "grpyfacx"),
    "plan_tree": _e("xsfacx", "modules/pyfacxepg/kzcx.do", "kzcx", query_setting=("PYFADM",), paged=True,
                    referer_hash="ckgrpyfa"),
}


def get(name: str) -> Endpoint:
    return KNOWN[name]


def build_form(ep: Endpoint, ctx: Optional[dict] = None, page: Optional[int] = None,
               page_size: int = 200) -> dict:
    """按定义拼参数；缺少必需上下文时返回 None 由调用方回退。"""
    import json
    ctx = ctx or {}
    form = dict(ep.fixed)
    for k in ep.ctx:
        if ctx.get(k):
            form[k] = ctx[k]
        elif k in ("XH", "PYFADM", "XNXQDM"):
            return None  # 必需上下文缺失
    if ep.query_setting:
        conds = [{"name": k, "value": ctx[k], "linkOpt": "AND", "builder": "equal"}
                 for k in ep.query_setting if ctx.get(k)]
        if len(conds) < len(ep.query_setting):
            return None
        form["querySetting"] = json.dumps(conds)
    if ep.paged and page is not None:
        form["pageSize"], form["pageNumber"] = str(page_size), str(page)
    return form


def scrub(obj):
    """递归去掉个人字段（落盘前调用）。"""
    if isinstance(obj, dict):
        return {k: scrub(v) for k, v in obj.items()
                if k not in PRIVATE_KEYS and not (k.endswith("_DISPLAY") and k[:-8] in PRIVATE_KEYS)}
    if isinstance(obj, list):
        return [scrub(x) for x in obj]
    return obj
