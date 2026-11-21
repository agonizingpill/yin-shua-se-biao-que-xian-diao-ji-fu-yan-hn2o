from fastapi import APIRouter,Depends
from sqlalchemy import select
from .db import db_session
from .auth import current,writers,admin
from .offline_models import OfflineCheckout,OfflineRecord
from .offline_schemas import CheckoutInput,SyncInput,ReconcileInput
from .services import pack,audit
from . import offline_service
router=APIRouter()

@router.get('/offline/checkouts')
def checkouts(s=Depends(db_session),u=Depends(current)):
    return [pack(x)for x in s.scalars(select(OfflineCheckout).order_by(OfflineCheckout.id.desc()))]

@router.post('/offline/checkouts')
def create_checkout(b:CheckoutInput,s=Depends(db_session),u=Depends(writers)):
    return pack(offline_service.checkout(s,b.job_id,u))

@router.get('/offline/checkouts/{key}')
def checkout_detail(key:int,s=Depends(db_session),u=Depends(current)):
    co=s.get(OfflineCheckout,key)
    if not co:from fastapi import HTTPException;raise HTTPException(404,'领单不存在')
    row=pack(co);row['records']=[pack(x)for x in s.scalars(select(OfflineRecord).where(OfflineRecord.checkout_id==key).order_by(OfflineRecord.seq))]
    return row

@router.get('/offline/records')
def records(s=Depends(db_session),u=Depends(current)):
    return [pack(x)for x in s.scalars(select(OfflineRecord).order_by(OfflineRecord.id.desc()).limit(200))]

@router.post('/offline/checkouts/{key}/sync')
def sync(key:int,b:SyncInput,s=Depends(db_session),u=Depends(writers)):
    return offline_service.sync(s,key,[x.model_dump()for x in b.records],u)

@router.post('/offline/checkouts/{key}/reconcile')
def reconcile(key:int,b:ReconcileInput,s=Depends(db_session),u=Depends(admin)):
    return pack(offline_service.reconcile(s,key,b.note,u))
