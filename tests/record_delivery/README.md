# 盖章赠品单与发票交车定向验证

```sh
python tests/record_pricing/run_isolated.py --suite delivery --output /tmp/huakangos-delivery-new
```

复用价格检查的源码白名单镜像、网络阻断及全新合成数据库。仅在仓库外加载应用，使用真实登录、CSRF、销售填单、独立经理审批、发票上传核实、赠品单上传及交车 API。文件由 Pillow 现场生成；不读取客户附件、生产配置或真实模型。

检查上传/下载字节与摘要、合同绑定及详情回显、更正原件追加留档、交车冻结附件、缺件或未核实拒绝、非法文件、旧版本与幂等、财务上传权限、授权岗位下载、跨合同/门店隔离、未批合同和隔离文件拒绝。结果与源码指纹保存在外部 `evidence/`，不替代浏览器、生产或迁移验收。

本地原生浏览器验证使用同一独立 Python 环境及已安装的 Chromium；额外依赖 `playwright==1.56.0`：

```sh
python tests/record_delivery/browser_check.py --browser /usr/bin/chromium --output /tmp/huakangos-delivery-browser-new
```

脚本先建立白名单源码镜像、全新迁移数据库和随机账号，以真实 API 准备新版批准合同，历史合同仅作为明确的合成前置。浏览器实际登录财务账号，经财务列表进入交车材料卡，上传并人工核实合成发票，上传 PNG/PDF 赠品单、查看失败反馈、刷新及下载原件、确认交车；另检查未批/历史工作流、销售和跨店财务权限。两项迟到响应检查仅暂停后原样继续真实请求，不替换 HTTP 响应。API 准备、辅助断言与浏览器检查分别列于报告，不冒称原生审批验证。

每次输出保留 `source-manifest.json`、`scripts/`、`evidence/report.json`、桌面与 390px 截图、服务和出网记录；配置、随机凭据及合成数据库只留在外部 `runtime/`，不提交。真实模型保持禁用，识别失败后人工核实的结果不算模型识别成功。未读取成功的用户截图不用于推断真实合同状态。
