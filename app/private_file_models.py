"""Immutable private object identity; the owning FileAsset remains the authority."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import String,Integer,ForeignKey,DateTime,CheckConstraint,event
from sqlalchemy.orm import Mapped,mapped_column,Session
from .db import Base,utcnow
from .models import StoreScoped


class PrivateFileObject(StoreScoped,Base):
    __tablename__='private_file_objects'
    id:Mapped[int]=mapped_column(primary_key=True)
    store_id:Mapped[int]=mapped_column(ForeignKey('stores.id'),nullable=False,index=True)
    file_id:Mapped[int]=mapped_column(ForeignKey('flow_files.id'),unique=True)
    object_key:Mapped[str]=mapped_column(String(100),unique=True)
    sha256:Mapped[str]=mapped_column(String(64))
    size:Mapped[int]=mapped_column(Integer)
    created_at:Mapped[datetime]=mapped_column(DateTime,default=utcnow)
    __table_args__=(CheckConstraint('size > 0 AND size <= 10485760',name='ck_private_file_size'),)


@event.listens_for(Session,'before_flush')
def protect_private_objects(db,*_):
    if any(isinstance(row,PrivateFileObject) for row in list(db.dirty)+list(db.deleted)):
        raise HTTPException(409,'附件对象引用不可覆盖或删除；请新增补充附件')
    if any(isinstance(row,PrivateFileObject) for row in db.new) and not db.info.get('_private_file_authority'):
        raise HTTPException(403,'私有附件引用只能由附件存储服务建立')
