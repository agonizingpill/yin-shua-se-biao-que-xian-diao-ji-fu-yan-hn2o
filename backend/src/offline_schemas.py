from typing import Any,Literal
from pydantic import BaseModel,Field,field_validator
from .production_schemas import Inputs

class CheckoutInput(Inputs):
    job_id:int

class OfflineRecordIn(Inputs):
    client_uuid:str=Field(min_length=8,max_length=64)
    seq:int=Field(ge=1,le=1000000)
    op:Literal['proof','classify','adjustment','instruction','execute','reproof']
    client_ts:str=Field(min_length=4,max_length=40)
    payload:dict[str,Any]

class SyncInput(Inputs):
    records:list[OfflineRecordIn]=Field(min_length=1,max_length=500)

class ReconcileInput(Inputs):
    note:str=Field(min_length=5,max_length=500)
    @field_validator('note')
    @classmethod
    def _check(cls,v):
        if len(v.strip())<5:raise ValueError('核对依据至少5字')
        return v.strip()
