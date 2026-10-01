# PATCH-M8-4-VEHICLE-CSV-OBSERVATION-01：原CSV文件上传的可观察字节

2026-10-01，仅tests/browser_click/vehicle_operations_business.py的原file控件观察和multipart文件内容对照；生产、API、CSV合同、幂等、角色/Task/CAS、trial回滚、独立review及确认不变。登记时其他关联实例仍活跃，注册文件冻结，全部关联验证退出后才实施。

business-vehicle-operations-20261001-01已正常退出1，所选3场景为2passed/1failed；HK019首次上传201、正确原单/批次GET200，原batch source_case_version=4/source_digest与员工外置93字节CSV完全一致。原file持久化字节/hash也核对成功，Guard未放宽；但Playwright response.request.post_data_buffer的multipart文件片段只保留文件名、内容长度0/hash空，导致旧“浏览器封包/CAS/所选字节”联断言失败。这是已观察的请求观察限制，不能将其写成上传空文件的产品缺陷，也不自动把原失败记passed。

最小修正在员工点击上传前，只读读取已选择的原input.files File对象名/类型/长度，并在原浏览器内对File.arrayBuffer做SHA256，返回元数据而不持久化原字节。其名/长度/hash必须严格等于员工外置本批输入；真实POST仍只由原上传控件及员工单次点击产生。请求中原source_reference/kind/version/request_id/文件字段/文件名仍严格解析。若请求观察实际给出内容字节，仍要求长度/hash一致；零片段明确记录multipart_file_content_observed=false，不能声称拿到了原封包完整文件内容。原服务器冻结File、Batch、源CSV、逐行解析均必须与浏览器所选元信息/外置字节独立一致；没有这个三方对应不通过。不是fetch/Cookie桥接、不造输入对象、不写业务SQL、不重放未知提交。

根静态/独立短审后全新采购、主档与车辆六项原UI场景复验；完整后继和所有失败/未知路径、193人工与原外部环境门槛保持。原失败证据外置保留，不继承为六项成绩。
