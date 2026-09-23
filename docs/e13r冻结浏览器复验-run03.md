# e13r 冻结源码浏览器复验（2026-09-23）

本次使用最终全量 run #3 同份冻结源码，重新运行五个既有真实 Chrome 脚本。五组全部通过，共 **21 步、18 张截图、0 JavaScript 错误**，脚本累计运行 139.06 秒。机器可读记录见 [browser-frozen-final.json](verification/u13h-original-branches/browser-frozen-final.json)。该结果仅证明列明的合成浏览器场景；不等同于全树 pytest 通过、193 项公司业务验收或正式部署验收。

| 脚本 | 步骤 | 截图 | 结果 |
|---|---:|---:|---|
| `tests/browser_local_preview.py` | 4 | 4 | 通过 |
| `tests/browser_questionnaire_exports.py` | 4 | 3 | 通过 |
| `tests/browser_dossier_grants.py` | 4 | 4 | 通过 |
| `tests/browser_master_completion.py` | 4 | 3 | 通过 |
| `tests/browser_store_switch.py` | 5 | 4 | 通过 |

所有脚本均以本机真实 Google Chrome、实际 HTTP 网络运行，没有使用 bridge；视口为 390×844。除脚本自身创建的独立新合成库、临时浏览器和随机端口外，没有使用公司数据或私有附件目录。显式设置 `FILE_STORAGE_MODE=blob`、空 `PRIVATE_FILE_ROOT`、`PYTHONDONTWRITEBYTECODE=1`。未修改冻结的 app、web、migrations、tests、scripts，也未停止、迁移或写入用户 8000 预览。

运行前后逐项比较 app、web、migrations、tests、scripts 共 **660 个文件**，全部一致。预览标准源码指纹为：

`59e6f73cbedf3f976dd15abf62316ce9af03262d74adad246792dc9a6dd9e70a`

`web/app.js` 为 `1f0ad421e7849d1c9b5ed06070ad876b8a858a8e2f8fa7a15e8e11ea9ba74cdc`。完整前后清单、选定文件及截图 SHA-256 均由机器记录引用。独立启动器测试库实际读取到 `e13r_member_fee_corrections`，仅有该测试建立的一个管理员、零业务单；它只结束自身测试服务。

本次保留 `browser_master_completion.py` 换店后立即导航的原路径，没有为通过而增加等待或修改脚本。换店专项另覆盖延迟身份读取、连续换店、旧响应迟到、目标403拒绝、原店恢复503失败及重试，并使用员工在三店分别承担店长、服务顾问、财务岗位的账号。

已人工查看其中 **12 张关键截图**：首次管理员设置、过期链接中文拒绝、空工作台；问卷数字0与未回答及缺少筛选条件的中文拒绝；档案接收与撤销后内容清除；物资品牌目录；换店等待、回到原店、恢复失败及明确重试。关键提示和操作可见，未见旧店业务残留或关键内容遮挡。较宽明细表继续使用横向滚动，不据此宣称整站所有页面均完成视觉验收。

原始证据保存在仓库之外：

- 首次设置：[acceptance.json](C:/Users/tiefu/AppData/Local/Temp/huakangos-preview-browser-evidence-7j4rbg8w/acceptance.json)。
- 问卷：[acceptance.json](C:/Users/tiefu/AppData/Local/Temp/huakangos-browser-e13r-final-0c6e2dd4306043ba8749d7760ad98677/questionnaire_exports/acceptance.json)。
- 档案：[acceptance.json](C:/Users/tiefu/AppData/Local/Temp/huakangos-browser-e13r-final-0c6e2dd4306043ba8749d7760ad98677/dossier_grants/acceptance.json)。
- 基础资料：[acceptance.json](C:/Users/tiefu/AppData/Local/Temp/huakangos-browser-e13r-final-0c6e2dd4306043ba8749d7760ad98677/master_completion/acceptance.json)。
- 换店：[acceptance.json](C:/Users/tiefu/AppData/Local/Temp/huakangos-browser-e13r-final-0c6e2dd4306043ba8749d7760ad98677/store_switch/acceptance.json)。

同一外部根目录保存五组日志、运行时间和前后源码清单。先前换店修复的[历史说明](换店异步与冻结浏览器复核.md)、最初失败、只读诊断及早期通过证据均保留；它们没有计入本次21步。续会费专项的四张浏览器图另见 [e13r 领域证据](verification/e13r-member-fee-corrections.json)，也没有重复计入本次18张。全树结果由 root 的 run #3 独立记录。
