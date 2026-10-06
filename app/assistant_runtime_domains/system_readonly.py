"""系统只读面（system_readonly）适配器：原管理读取的受控只读投影。

**适配器注册与核心查询分开**：
- 本适配器只注册 `GET /api/stores` 与 `GET /api/parameters/catalog`，不注册用户/审计事实；
- 核心 read_data 的查询目录由 gateway 按开放领域和原 GET 路由生成，包含用户与审计读取；
  它们能否查询由本人当前门店岗位及原接口决定，不因本适配器未注册就视为全局关闭；
- 原 `MANAGEMENT_READERS` 岗位校验仍是权威，不得借用管理员身份。

**`fact_keys=()`**：按计划不注册任何事实键——**查询权限配置不产生授权生效、密码变更或员工创建完成事实**。
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import ValidationError

from ..assistant_runtime_schemas import (AvailableAction, BusinessObjectRef, BusinessObjectSnapshot,
                                         EvidenceRef, FactSnapshot, ReceiptLookup, SubmissionSnapshot)
from .flow_case import FlowCaseAdapter, _positive_id

SYS_OBJECT_TYPE = 'report_query'
SYS_STORES = 'GET /api/stores'
SYS_PARAMETERS = 'GET /api/parameters/catalog'
SYS_UNREGISTERED = ('GET /api/users', 'GET /api/audit')
SYS_RESULT_OPERATIONS = frozenset()
SYS_RECEIPT_OPERATIONS = frozenset()
SYS_FACTS = ()
QUERY_FROM_CORE = ('系统只读查询由核心运行时按员工本人的查询对象提供；适配器不读助手自己的对象表，'
                   '也不猜参数，请由核心传入查询意图或回到原管理页面查看。')
NO_REVIEWED_READ = ('本适配器不注册用户与审计读取或事实；核心查询目录另按本人当前门店岗位和原接口提供只读能力，'
                    '不能从适配器未注册推断查询全局关闭，也不得借用管理员身份绕过岗位校验。')
NO_SIDE_EFFECTS = ('查询权限配置不产生授权生效、密码变更或员工创建完成事实：'
                   '只读结果不代表任何授权、凭据或人员变更已完成')


def _now():
    return datetime.now(timezone.utc)


def _invalid():
    raise HTTPException(502, '原业务返回的管理数据不完整，请稍后重新核对') from None


class SystemReadonlyAdapter(FlowCaseAdapter):
    """系统适配器仅注册两条只读；核心查询另走 gateway。无写、无事实、无回执族。"""

    name = 'system_readonly'
    object_types = (SYS_OBJECT_TYPE,)
    fact_keys = ()

    def _query_ref(self, ref):
        values = ref.model_dump() if isinstance(ref, BusinessObjectRef) else ref
        if (type(values) is not dict or values.get('type') != SYS_OBJECT_TYPE
                or not _positive_id(values.get('id'))):
            raise HTTPException(422, '请选择有效的查询对象')
        return values

    async def _read(self, principal, operation_id):
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        try:
            response = await self._native_reader(operation_id, path_args={}, query={}, body=None)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                raise HTTPException(404, '原业务不存在或当前岗位不可查看') from None
            raise
        if type(response) is not dict or type(response.get('status')) is not int:
            _invalid()
        status = response['status']
        if status in {401, 403, 404}:
            raise HTTPException(404, '原业务不存在或当前岗位不可查看')
        if 400 <= status < 500:
            raise HTTPException(status, '原业务暂不能读取，请到原管理页面核对')
        if not 200 <= status < 300:
            raise HTTPException(503, '原业务查询暂时不可用，请稍后重试')
        data = response.get('data')
        if type(data) is not dict or data.get('truncated') or response.get('truncated'):
            _invalid()
        return data

    async def read_stores(self, principal):
        """已评审只读：原门店列表（岗位由原接口判定）。"""
        return await self._read(principal, SYS_STORES)

    async def read_parameter_catalog(self, principal):
        """已评审只读：原参数目录（仅目录，不含改参）。"""
        return await self._read(principal, SYS_PARAMETERS)

    async def read_snapshot(self, principal, ref):
        self._query_ref(ref)
        store_id = getattr(principal, 'store_id', None)
        if not _positive_id(store_id):
            raise HTTPException(403, '请使用已核验的当前门店身份读取原业务')
        raise HTTPException(503, QUERY_FROM_CORE)

    async def fact_snapshot(self, principal, ref, fact_key):
        self._query_ref(ref)
        try:
            return FactSnapshot(fact_key=fact_key, satisfied=None, evidence_refs=[],
                                reason='系统只读面不注册任何事实键（' + NO_SIDE_EFFECTS + '）；'
                                       + NO_REVIEWED_READ)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '事实标识不正确') from None

    def extract_result(self, operation_id, response):
        # 本领域没有写 operation：任何响应都不绑定业务结果。
        return []

    async def read_receipt(self, principal, submission):
        try:
            SubmissionSnapshot.model_validate(
                submission.model_dump() if isinstance(submission, SubmissionSnapshot) else submission)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(422, '提交快照格式不正确') from None
        return ReceiptLookup(status='unsupported', checked_at=_now(), object_refs=[], evidence_refs=[],
                             reason_code='read_only_surface')


__all__ = ['NO_REVIEWED_READ', 'NO_SIDE_EFFECTS', 'QUERY_FROM_CORE', 'SYS_FACTS', 'SYS_OBJECT_TYPE',
           'SYS_PARAMETERS', 'SYS_RECEIPT_OPERATIONS', 'SYS_RESULT_OPERATIONS', 'SYS_STORES',
           'SYS_UNREGISTERED', 'SystemReadonlyAdapter']
