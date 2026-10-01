# PATCH-M8-4-RECEIVABLES-REGISTER-01

2026-10-01，业主当前连续代码与浏览器点击交付授权内；51项四个关联实例已退出，先登记再修改。

仅将 BUSINESS-193-36 与 RECEIVABLES-MATERIAL-SOURCE-01 已冻结、独立只读审阅的 receivables_business.py 加入 run.py 白名单，scenarios.py 导入 RECEIVABLES_SCENARIOS 并在尾部注册。候选 SHA dfcf2f20d21d9a629bbbc0df7c93340c03aedec54b08b0e51464f9e7e70a844d，文档 e6f5bec5a24ee048bc7b9a82c371f11df7616ed44f4a1fe973e1283b08ce5fa6；登记后52场景/44白名单文件。

三项 HK157/158/159 以全新原表单建立实际物资、整车/关联代办、维修客户正欠额，再核对整店原口径、所有分页、CSV及原单钻取。新增物资1000milli与整车8000分采购均需原UI审批、实收、付款；内部承担不制造客户应收或现金。依赖必须同轮通过及指纹一致。独立审164处助手调用与八类当前全店明细口径未发现静态阻断；动态路径尚未执行，不登记passed/全193验收。

只登记脚本入口；旧结果原样保留，M8.1唯一in_progress、四生产开关及其他真实环境门槛不变。

登记首静态导入发现原候选SCENARIOS为list而统一拼接是tuple（TypeError，应用未启动）。根仅末尾改tuple并头文案Registered，当前SHA51f155f8e4c8cc46d7a5ef71827f5d5bc794839e90a1237f5fa5b693c6caa204；业务主体不变，52入口静态导入/AST通过。
