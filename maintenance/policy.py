"""Untrusted model output is data, never a shell command or unrestricted patch.
The allowlist deliberately excludes auth, money calculations, dependencies,
migrations, tests and every controller/deployment file.
"""
from pathlib import Path, PurePosixPath
from typing import Literal
import re
from pydantic import BaseModel, Field, ConfigDict
from .config import GateError

EDITABLE = frozenset({'web/app.js','web/style.css','web/index.html','docs/USER_GUIDE.md'})
CONTEXT = tuple(sorted(EDITABLE | {'docs/AI_CONTEXT.md'}))
MAX_FILE_BYTES = 256_000
MAX_CONTEXT_CHARS = 180_000
MAX_CHANGED_LINES = 500


class Edit(BaseModel):
    model_config=ConfigDict(extra='forbid')
    path: str = Field(min_length=1,max_length=150)
    old: str = Field(min_length=1,max_length=30000)
    new: str = Field(max_length=40000)


class Proposal(BaseModel):
    model_config=ConfigDict(extra='forbid')
    summary: str = Field(min_length=1,max_length=1800)
    risk: Literal['low','manual']
    manual_reason: str = Field(default='',max_length=1800)
    edits: list[Edit] = Field(default_factory=list,max_length=12)


def safe_path(root: Path, name: str) -> Path:
    part=PurePosixPath(name)
    if not name or '\\' in name or ':' in name or part.is_absolute() or '..' in part.parts or str(part)!=name:
        raise GateError('补丁含不安全路径')
    path=root.joinpath(*part.parts)
    if not path.resolve().is_relative_to(root.resolve()): raise GateError('补丁路径越界')
    for ancestor in [path,*path.parents]:
        if ancestor==root.parent: break
        if ancestor.is_symlink(): raise GateError('补丁不允许符号链接')
    return path


def read_source(path: Path) -> str:
    """Editable sources are UTF-8 by contract. On Windows an editor may silently
    save GBK/ANSI, which would otherwise surface as an opaque decode crash."""
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError as exc:
        raise GateError('源码不是UTF-8编码，请用UTF-8重新保存该文件后再试：'+path.name) from exc


def context_files(root: Path) -> dict:
    result={}
    total=0
    for name in CONTEXT:
        path=safe_path(root,name)
        if not path.is_file(): continue
        if path.stat().st_size>MAX_FILE_BYTES: raise GateError('源码文件超过允许大小，请人工拆分')
        content=read_source(path)
        total+=len(content)
        if total>MAX_CONTEXT_CHARS: raise GateError('白名单源码超过上下文预算，请人工处理')
        result[name]=content
    return result


def protected_regions(text):
    pattern=r'// MAINT_PROTECTED_BEGIN:([a-z-]+)\n(.*?)\n// MAINT_PROTECTED_END:\1'
    found=re.findall(pattern,text,re.S)
    if not found or len({name for name,_ in found})!=len(found):
        raise GateError('关键前端保护标记缺失或重复，转人工处理')
    return dict(found)


def apply_proposal(root: Path, proposal: Proposal) -> list[str]:
    if proposal.risk!='low' or not proposal.edits: raise GateError('该意见需要人工开发，自动维护不改动后端/数据库等受保护内容')
    pending={}
    changed_lines=0
    for edit in proposal.edits:
        if edit.path not in EDITABLE: raise GateError('拒绝修改受保护文件：'+edit.path)
        path=safe_path(root,edit.path)
        if not path.is_file(): raise GateError('只允许精确修改已存在的白名单文件')
        original=pending.get(edit.path)
        if original is None: original=read_source(path)
        if original.count(edit.old)!=1: raise GateError('定位文本不是唯一匹配，拒绝猜测补丁位置')
        if edit.old==edit.new: raise GateError('补丁没有实际改动')
        updated=original.replace(edit.old,edit.new,1)
        if '\x00' in updated or len(updated.encode('utf-8'))>MAX_FILE_BYTES: raise GateError('生成文件过大或含无效字符')
        changed_lines+=len(edit.old.splitlines())+len(edit.new.splitlines())
        if changed_lines>MAX_CHANGED_LINES: raise GateError('修改规模超过500行预算，转人工处理')
        pending[edit.path]=updated
    if 'web/app.js' in pending:
        old=read_source(safe_path(root,'web/app.js'))
        if protected_regions(old)!=protected_regions(pending['web/app.js']):
            raise GateError('补丁触及前端权限、登录、门店选择或写入流程保护区，须人工处理')
    # All validations precede the first write.
    for name,content in pending.items(): safe_path(root,name).write_text(content,encoding='utf-8',newline='\n')
    return sorted(pending)


# --- change tiering -------------------------------------------------------
# The tier decides whether a change may be published without a human click. It is
# derived from the set of files the commit actually touched, never from the
# model's self-reported risk: a proposal that claims risk=low while editing
# app/analytics.py must still stop for a human.
TIER_AUTO = 'auto'
TIER_HUMAN = 'human'
AUTO_APPROVER = 'auto:frontend'


def change_tier(changed) -> str:
    """Classify a commit by its changed paths. Empty or unknown -> human."""
    files = {str(name) for name in (changed or ()) if str(name)}
    if not files: return TIER_HUMAN
    return TIER_AUTO if files <= EDITABLE else TIER_HUMAN


def tier_allows_auto_publish(changed, auto_publish_enabled: bool) -> bool:
    return bool(auto_publish_enabled) and change_tier(changed) == TIER_AUTO
