# PATCH-M8-1-WINDOWS-NATIVE-PATH-01

2026-10-03；M8.1 正式外部执行器修复。允许范围仅 `V/tests/baseline/overlay/tests/m81_browser_entry.py` 中 Windows 原生浏览器实例输出路径、`V/baseline-restoration.json` 对该精确脚本的字节/hash登记和对应不可变 binding-history 记录；若实际登记文件名不同，先核对当前原件再维护同一登记项。仓库生产源码、上传 helper、OS/浏览器策略与原数据不改。

正式 run `20261003T064631Z-7769222357` 的原采购合成合同路径长265字符。原输入已选择文件、原 POST 有同源 Cookie/CSRF，但服务无返回，导致采购前置及依赖场景失败。独立 `windows-upload-path-probe-20261003T082351Z-24f77c5d0f` 使用同 Chrome154/PW1.56、同filename/328bytes/SHA，长路径 requestfailed、服务收件0；160字符路径原生 FormData POST200且收到完全相同328字节。长路径实际Chrome/CDP错误为 `net::ERR_ALPN_NEGOTIATION_FAILED`，保留原文；明文loopback probe不支持将其解释成业务TLS/ALPN故障。

最小修复：Windows实例放到同一个已标记且本次独占的 `run/native`，仍经 `inside(..., run)`；非Windows保留原 `result_dir/native-browser-instance`。必须先独立核对全部上传后缀及新绝对路径长度、现有root/command/source/evidence/provenance守卫，不改变命令、身份、私有配置、真实文件路径选择、确认次数或错误接纳标准。不引入内存文件替代、跨run staging、重试或允许任意文件读取。旧run/native不存在才可创建；旧失败实例及原报告保留。

独立长短探测自然退出0且自有browser/server正常关闭；仅证明此环境的文件路径因果。正式原采购链和全80场仍须用新输出布局执行，不能把独立probe写成业务验收通过。
