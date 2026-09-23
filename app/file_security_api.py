from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from .db import get_db
from .security import get_user
from .file_security import file_security_detail, rescan_file

router = APIRouter(prefix='/api/flow/files', tags=['附件隔离与扫描'])


class ScanInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0, strict=True)
    request_id: str = Field(min_length=16, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')


@router.get('/{file_id}/security')
def detail(file_id: int, db=Depends(get_db), user=Depends(get_user)):
    return file_security_detail(db, user, file_id)


@router.post('/{file_id}/scan')
def scan(file_id: int, body: ScanInput, db=Depends(get_db), user=Depends(get_user)):
    return rescan_file(db, user, file_id, body.version, body.request_id)
