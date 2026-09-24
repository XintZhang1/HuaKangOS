"""A deliberately public, sanitized login photo; never a business attachment."""
import base64
import hashlib
import io
import warnings
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from .db import get_db
from .models import AppMetadata
from .security import get_user
from .services import audit
router=APIRouter(prefix='/api/branding',tags=['登录图片'])
KEY='public_login_photo'

def admin(user):
    if getattr(user,'account_role',user.role)!='admin' or getattr(user,'_aggregate_scope',False):
        raise HTTPException(403,'请联系系统管理员更换图片')

@router.get('/photo')
def photo(db=Depends(get_db)):
    row=db.get(AppMetadata,KEY)
    if row:
        return Response(base64.b64decode(row.value['image']),media_type='image/jpeg')
    with Image.open(Path(__file__).resolve().parent.parent/'web/assets/huakang-store-source.jpg') as source:
        output=io.BytesIO();source.crop((0,0,1080,724)).save(output,format='JPEG',quality=95)
    return Response(output.getvalue(),media_type='image/jpeg')

@router.post('/photo')
async def replace_photo(file:UploadFile=File(...),db=Depends(get_db),user=Depends(get_user)):
    admin(user)
    raw=await file.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise HTTPException(413,'图片不能超过8MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG','PNG','WEBP'}:raise ValueError()
                if source.width*source.height>24000000 or min(source.size)<320:raise ValueError()
                source.load()
                clean=ImageOps.exif_transpose(source).convert('RGB')
                clean.thumbnail((3840,3840))
                output=io.BytesIO();clean.save(output,format='JPEG',quality=92)
    except (ValueError,OSError,UnidentifiedImageError,Image.DecompressionBombWarning,Image.DecompressionBombError):
        raise HTTPException(422,'请选择清晰的JPG、PNG或WebP图片，宽高至少320像素，最多2400万像素')
    image=output.getvalue();digest=hashlib.sha256(image).hexdigest()
    row=db.get(AppMetadata,KEY)
    value={'image':base64.b64encode(image).decode('ascii'),'sha256':digest}
    if row:row.value=value
    else:db.add(AppMetadata(key=KEY,value=value))
    audit(db,user.id,'replace_photo','maintenance',None,after={'sha256':digest},reason='更换登录图片')
    db.commit()
    return {'ok':True,'sha256':digest}

@router.delete('/photo')
def reset_photo(db=Depends(get_db),user=Depends(get_user)):
    admin(user);row=db.get(AppMetadata,KEY)
    if row:db.delete(row)
    audit(db,user.id,'reset_photo','maintenance',None,reason='恢复默认登录图片')
    db.commit();return {'ok':True}
