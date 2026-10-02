# PATCH-M8-1-VEHICLE-IMPORT-PREPARE-WRITER-01

2026-10-02 继续当前 M8.1，业主授权补齐未完成测试并提交 GitHub。原 CI [36952582341](https://github.com/XintZhang1/HuaKangOS/actions/runs/36952582341) 在 main `6d2368e` 完整53执行49过4失败：旧SSE断线装置失败；HK028的原CSV到货批次POST409；跨店/库存后继因父失败0动作未执行。原artifact/失败报告保留外部 `V/browser-click/ci-old-36952582341/`，不改旧成绩。

原服务 `vehicle_imports_service.run` 统一把 IntegrityError/OperationalError/StaleDataError 返回409。原CI server.log:82 的 receive准备失败时为 INSERT OperationalError SQLite code5，与worker写锁竞争；原日志其它code5/517不能全部归因此单入口。API `prepare` 是写入口却仍在get_user鉴权快照后使用get_db；同文件 `command` 及原 reviewed写入口已采用get_write_db。

精确生产范围仅 `app/vehicle_imports_api.py` 的 `/orders/{case_id}/batches` prepare参数依赖：改为先 `db=Depends(get_write_db)` 再 `user=Depends(get_user)`，沿现有 `app/db.py` 的SQLite鉴权前BEGIN IMMEDIATE，PG原模式不变。Multipart由原框架接收/暂存后进入依赖及endpoint，保留原file.read与MAX_BYTES/解析、来源关系、本人店/岗位、原version、幂等和整批事务/回执守卫，不增加重试或放宽拒绝；不修改服务/数据库schema/worker。

当前main-resume27冻结9项补测尚在运行，所有相关验证进程实际终局后才改生产字节。改后独立代码审阅、静态确认只改依赖顺序，以及全新镜像从原UI建立采购/主档前置到HK019/027/028等原车辆路径复验；随后推送触发同原53入口的GitHub CI，不把本地定向结果写成远端通过。测试目录/证据/凭据仍外置；四新开关生产默认关闭，原Date/PG/Linux/模型/员工/发布门槛保持。
