"""Owner-scoped customer suggestions for an explicit employee selection."""
from fastapi import APIRouter,Depends,Query
from .db import get_db
from .security import get_user
from .customer_choice import matches
router=APIRouter(prefix='/api/customer-choice',tags=['客户识别确认'])

@router.get('/matches')
def candidates(phone:str=Query('',max_length=30),q:str=Query('',max_length=100),db=Depends(get_db),user=Depends(get_user)):
    return matches(db,user,phone,q)
