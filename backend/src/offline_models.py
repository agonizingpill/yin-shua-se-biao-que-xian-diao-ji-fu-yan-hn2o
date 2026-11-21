from sqlalchemy import String,Integer,Float,ForeignKey,JSON,Text,UniqueConstraint,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base

class OfflineCheckout(Base):
    __tablename__='offline_checkouts'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    job_id:Mapped[int]=mapped_column(ForeignKey('print_jobs.id'))
    reference_version:Mapped[str]=mapped_column(String(64))
    reference_count:Mapped[int]=mapped_column()
    model_snapshot:Mapped[dict]=mapped_column(JSON)
    job_snapshot:Mapped[dict]=mapped_column(JSON)
    adjustment_snapshot:Mapped[list]=mapped_column(JSON,default=list)
    state:Mapped[str]=mapped_column(String(24),default='active')
    checked_out_by:Mapped[str]=mapped_column(String(100))
    checked_out_at:Mapped[str]=mapped_column(String(40))
    synced_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    reconciled_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    reconciled_by:Mapped[str]=mapped_column(String(100),default='')
    reconcile_note:Mapped[str]=mapped_column(String(500),default='')

class OfflineRecord(Base):
    __tablename__='offline_records'
    __table_args__=(UniqueConstraint('client_uuid'),CheckConstraint("op IN ('proof','classify','adjustment','instruction','execute','reproof')"))
    id:Mapped[int]=mapped_column(primary_key=True)
    checkout_id:Mapped[int]=mapped_column(ForeignKey('offline_checkouts.id'))
    client_uuid:Mapped[str]=mapped_column(String(64),unique=True)
    seq:Mapped[int]=mapped_column()
    op:Mapped[str]=mapped_column(String(20))
    payload:Mapped[dict]=mapped_column(JSON)
    client_ts:Mapped[str]=mapped_column(String(40))
    state:Mapped[str]=mapped_column(String(20),default='pending')
    conflict_reason:Mapped[str]=mapped_column(String(300),default='')
    proof_id:Mapped[int|None]=mapped_column(ForeignKey('proof_sheets.id'),nullable=True)
    adjustment_id:Mapped[int|None]=mapped_column(ForeignKey('adjustments.id'),nullable=True)
    applied_at:Mapped[str|None]=mapped_column(String(40),nullable=True)
    actor:Mapped[str]=mapped_column(String(100))
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
