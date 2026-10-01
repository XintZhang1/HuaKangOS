# full17 新 v3 采购与仓储报表有限看图

负责人：visual_reports_current；2026-10-02。仅从 root 已实际执行的新原生只读 v3 取4张原PNG实际view_image；未执行浏览器/helper/SQL，未修改代码、runner或原证据。

本次独立来源为 `automatic-business17/evidence/manual-review/native-chrome-readonly-20261001T213042393087/`，不是旧v2。原preview为22只读路径observed、complete=false、provider_final_gate=pending、employee_trial=not_executed；实际浏览器版本154.0.8037.59。生产摘要76862a922e57832b92d6f9e68ec0804e2182a992da0cd3b150297487532a525b，脚本摘要06d17fb81fc97b1d86c753f60602850f9f43dec6359407f8f48affd8323aa5df与本轮原全53一致。terminal_native_gate已核clean=true/automatic_unchanged=true、finish_error=null、pending_capture_jobs0、pageerror/外网/5xx为空、forbidden_write_attempts0；不将preview当provider终局或员工验收。

实际查看4图，全部original保持原尺寸：M05的86-M05-native-390.png（390×3622）、88-M05-native-768.png（768×2593）；M06的115-M06-native-390.png（390×4555）、117-M06-native-768.png（768×2574）。每图有本目录observations唯一原指针，摘要和尺寸写入新exclusive的native-reports-visual-v1.json。没有读取或继承旧v2图片/评分；与原自动10图记录分别计数。

| 范围 | 390实际观察 | 768实际观察 |
| --- | --- | --- |
| M05 物资采购订货统计 | 日期/更新/快捷范围按钮清楚，图表稀疏横轴标签分开。订货履约行转成纵向字段：订2升、累计收2升、退0.5升、净留1.5升；金额20/20/5/15元，来源已核对。三条原账显示+1/+1/−0.5升、+10/+10/−5元，均引用同一采购原单。 | 图表数值和稀疏标签仍可读；表格只显示靠左几列，右侧数量/金额需另核横向读取。本次未实际拖动/横滚。历史差异空表同时显示“暂无记录”和“本表暂无记录”，有重复。 |
| M06 库位期间入出存 | 顶部明确“全期间来源：有未知期初或覆盖缺口”“期末来源：已知并可核对；不代表全期间完整”。2个库位的期初及全期间收发为破折号，期末分别0.5升/5元、1升/10元，合计1.5升/15元，与M05净留存和15元图柱一致。启用桥接基准0与3条原库位流水单列，不写成当期进货。 | 期末15元图柱与未知期间提示仍可见；两期末行、1桥接行、3流水行数量可见，但表格右侧金额/完整来源未呈现于本图；只据390图核有限数值一致。 |

两宽截图未见主要控件或卡片明显重叠；390窄屏的纵向字段保留完整数量金额，但重复门店/单号/来源令页面较长。物资与仓库筛选的窄输入只露出名称开头，完整对象依赖下方明细。本次未打开选择器核长名称，也没有检验实际员工操作效率。

六rubric全部分层：visual给这两宽局部4分，1440未看；simplicity因未本人办理/员工试用pending；conciseness局部3分，报告定义保留必要范围边界但文字与空状态有重复；fact_clarity局部4分，能清楚分开累计履约、实际退货、净留存、期末完整与期间未知；recovery仅见覆盖缺口提示，实际失败/换店/退出/未知结果恢复pending；accessibility仅见一个目录按钮黑色焦点轮廓，键盘顺序、点击区域和实际手机操作pending。

**结果**：4张新v3图/2站有限观察，accepted=false、六项整体通过false、full193_business_acceptance=false。不补看M04/M16，不把root原生操作当本审阅者操作，不改变原provider gate、真实Date、PG/Linux/真实模型/员工/生产条件。
