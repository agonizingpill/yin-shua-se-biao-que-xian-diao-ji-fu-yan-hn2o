from sqlalchemy import select
from fastapi import HTTPException
from .models import PrintJob,ProofSheet,Adjustment,Audit
from .offline_models import OfflineCheckout,OfflineRecord
from .classifier import reference_fingerprint,export_model
from .services import get,audit,now
from .paper_service import locked

OPS=('proof','classify','adjustment','instruction','execute','reproof')

def active_for_job(s,job_id):
    return s.scalar(select(OfflineCheckout).where(OfflineCheckout.job_id==job_id,OfflineCheckout.state.in_(['active','conflicted'])).order_by(OfflineCheckout.id.desc()))

def checkout(s,job_id,u):
    job=locked(s,PrintJob,job_id)
    if active_for_job(s,job_id):raise HTTPException(409,'该工单已有未核对的离线领单，请先补传并核对')
    version,count=reference_fingerprint(s)
    snapshot=export_model(s)
    adj_snapshot=[{'id':a.id,'status':a.status,'ink_delta':a.ink_delta,'water_delta':a.water_delta,'executed_at':a.executed_at}for a in s.scalars(select(Adjustment).where(Adjustment.job_id==job_id))]
    row=OfflineCheckout(code='OFF-'+job.code+'-'+now()[-12:].replace(':','').replace('.',''),job_id=job_id,reference_version=version,reference_count=count,model_snapshot=snapshot,job_snapshot={'code':job.code,'title':job.title,'paper':job.paper,'target_density':job.target_density,'status':job.status},adjustment_snapshot=adj_snapshot,checked_out_by=u.email,checked_out_at=now())
    s.add(row);audit(s,u,f'离线领单 {job.code} 判读版本{version} 参考{count}张');s.commit();return row

def ensure_version(s,co):
    version,count=reference_fingerprint(s)
    if version!=co.reference_version or count!=co.reference_count:
        raise HTTPException(409,f'判读版本已漂移（领单{co.reference_version}/{co.reference_count}张 → 当前{version}/{count}张），离线判读留档，须重新取样在线判读')

def _proof_fields(p):
    keys=('job_id','code','density_c','density_m','density_y','density_k','dot_gain')
    return {k:p[k]for k in keys}

def _resolve_proof(s,rec,p):
    if rec.proof_id:return s.get(ProofSheet,rec.proof_id)
    return s.scalar(select(ProofSheet).where(ProofSheet.code==p.get('proof_code')))

def _resolve_adjustment(s,co,rec,p):
    if rec.adjustment_id:return s.get(Adjustment,rec.adjustment_id)
    ref=p.get('adjustment_uuid')
    if ref:
        prior=s.scalar(select(OfflineRecord).where(OfflineRecord.client_uuid==ref,OfflineRecord.checkout_id==co.id))
        if prior and prior.adjustment_id:return s.get(Adjustment,prior.adjustment_id)
    return s.scalar(select(Adjustment).where(Adjustment.job_id==co.job_id,Adjustment.status!='signed').order_by(Adjustment.id.desc()))

def _online_adjustment(s,co):
    """与领单时快照比对：新增调机或已有调机被在线改动即冲突；本领单已落地记录产生的调机除外。"""
    offline_adj_ids=set(s.scalars(select(OfflineRecord.adjustment_id).where(OfflineRecord.checkout_id==co.id,OfflineRecord.state=='applied',OfflineRecord.adjustment_id.is_not(None))).all())
    snap={x['id']:x for x in (co.adjustment_snapshot or [])}
    for a in s.scalars(select(Adjustment).where(Adjustment.job_id==co.job_id)):
        if a.id in offline_adj_ids:continue
        old=snap.get(a.id)
        if not old:return a
        if (old['status'],old['ink_delta'],old['water_delta'],old['executed_at'])!=(a.status,a.ink_delta,a.water_delta,a.executed_at):return a
    return None

def apply_record(s,co,rec):
    """在调用方事务/保存点内重放一条离线记录。"""
    p=rec.payload
    if rec.op=='proof':
        if p['job_id']!=co.job_id:raise HTTPException(409,'离线条目不属于领单工单')
        if s.scalar(select(ProofSheet.id).where(ProofSheet.code==p['code'])):raise HTTPException(409,'色标编号已存在，离线样张留档不重复收样')
        job=get(s,PrintJob,co.job_id)
        if job.status in ('production','hold'):raise HTTPException(409,'工单已量产/停机，离线录入留档，量产须走在线抽检流程')
        proof=ProofSheet(**_proof_fields(p),classification_state='unmeasured')
        s.add(proof);s.flush();rec.proof_id=proof.id
        return {'proof_id':proof.id,'code':proof.code}
    if rec.op in ('classify','reproof'):
        ensure_version(s,co)
        proof=_resolve_proof(s,rec,p)
        if not proof:raise HTTPException(409,'离线判读对应样张不存在')
        if proof.job_id!=co.job_id:raise HTTPException(409,'离线判读样张不属于领单工单')
        if proof.classification_state=='classified':raise HTTPException(409,'样张已判读，离线判读留档不重复')
        ev=p.get('evidence') or {};label=p.get('defect')
        if label not in ('合格','乳化','偏色') or ev.get('reference_version')!=co.reference_version:raise HTTPException(409,'离线判读证据与领单版本不一致，须重新取样')
        proof.classification_state='classified';proof.defect=label;proof.pass_flag=label=='合格';proof.classified_at=p['classified_at']
        proof.evidence={**ev,'offline':True,'checkout_id':co.id,'checkout_code':co.code}
        return {'proof_id':proof.id,'code':proof.code,'defect':label}
    if rec.op=='adjustment':
        ensure_version(s,co)
        if _online_adjustment(s,co):raise HTTPException(409,'领单期间线上已登记调机指令，离线调机留档，须重新取样')
        proof=_resolve_proof(s,rec,p)
        if not proof:raise HTTPException(409,'离线调机对应样张不存在')
        from .services import issue
        adj=issue(s,proof.id);rec.adjustment_id=adj.id
        return {'adjustment_id':adj.id}
    if rec.op=='instruction':
        if _online_adjustment(s,co):raise HTTPException(409,'领单期间线上已修改调机指令，离线修订留档，须重新取样')
        adj=_resolve_adjustment(s,co,rec,p)
        if not adj:raise HTTPException(409,'离线修订的调机指令不存在')
        from .schemas import InstructionInput
        from .services import change_instruction
        change_instruction(s,adj,InstructionInput(ink_delta=p['ink_delta'],water_delta=p['water_delta']))
        return {'adjustment_id':adj.id}
    if rec.op=='execute':
        if _online_adjustment(s,co):raise HTTPException(409,'领单期间线上已改动调机，离线执行留档，须重新取样')
        adj=_resolve_adjustment(s,co,rec,p)
        if not adj:raise HTTPException(409,'离线执行对应的调机指令不存在')
        if adj.status!='issued':raise HTTPException(409,'调机指令当前状态不可登记离线执行')
        from .plate_service import require_ready
        from .inspection_service import ready
        require_ready(s,co.job_id);ready(s,co.job_id)
        adj.status='executed';adj.executed_at=p['executed_at']
        return {'adjustment_id':adj.id,'executed_at':adj.executed_at}
    raise HTTPException(409,'未知离线操作类型 '+rec.op)

def sync(s,co_id,records,u):
    co=get(s,OfflineCheckout,co_id)
    if co.state not in ('active','conflicted'):raise HTTPException(409,'领单已核对关闭，不能继续补传')
    applied,failed=[],[]
    for item in sorted(records,key=lambda r:r['seq']):
        if item['op']not in OPS:raise HTTPException(409,'未知离线操作 '+str(item['op']))
        existing=s.scalar(select(OfflineRecord).where(OfflineRecord.client_uuid==item['client_uuid']))
        if existing:
            # 幂等：重传已处理条目直接回放结果，不重复收样
            applied.append({'client_uuid':existing.client_uuid,'state':existing.state,'reason':existing.conflict_reason,'result':existing.result})
            if existing.state=='conflicted':failed.append({'client_uuid':existing.client_uuid,'state':'conflicted','reason':existing.conflict_reason})
            continue
        row=OfflineRecord(checkout_id=co.id,client_uuid=item['client_uuid'],seq=item['seq'],op=item['op'],payload=item['payload'],client_ts=item['client_ts'],actor=u.email)
        s.add(row);s.flush()
        try:
            with s.begin_nested():
                result=apply_record(s,co,row)
                s.flush()  # 固化保存点内产生的主键（样张/调机ID回写）
        except HTTPException as ex:
            # begin_nested已回滚保存点，行本身仍在事务内，标记冲突后提交留档
            row.state='conflicted';row.conflict_reason=str(ex.detail)
            if co.state=='active':co.state='conflicted'
            s.add(Audit(actor=u.email,action=f'离线补传冲突 {co.code} {row.op}: {ex.detail}',stamp=now()));s.commit()
            failed.append({'client_uuid':row.client_uuid,'state':'conflicted','reason':str(ex.detail)})
            return {'checkout_id':co.id,'state':co.state,'applied':applied,'failed':failed,'resume_from':row.client_uuid}
        row.state='applied';row.applied_at=now();row.result=result
        s.add(Audit(actor=u.email,action=f'离线补传 {co.code} {row.op} 序号{row.seq}',stamp=now()));s.commit()
        applied.append({'client_uuid':row.client_uuid,'state':'applied','result':result})
    if not s.scalar(select(OfflineRecord.id).where(OfflineRecord.checkout_id==co_id,OfflineRecord.state=='pending')):
        c2=s.get(OfflineCheckout,co.id);c2.synced_at=now()
        if c2.state=='active':audit(s,u,f'离线领单 {co.code} 补传完成，无冲突')
        s.commit()
    return {'checkout_id':co.id,'state':s.get(OfflineCheckout,co.id).state,'applied':applied,'failed':failed,'resume_from':None}

def reconcile(s,co_id,note,u):
    co=locked(s,OfflineCheckout,co_id)
    if co.state not in ('active','conflicted'):raise HTTPException(409,'领单已核对，不能重复核对')
    if s.scalar(select(OfflineRecord.id).where(OfflineRecord.checkout_id==co_id,OfflineRecord.state=='pending')):raise HTTPException(409,'仍有待补传记录，不能核对')
    conflicts=s.scalars(select(OfflineRecord.id).where(OfflineRecord.checkout_id==co_id,OfflineRecord.state=='conflicted')).all()
    co.state='reconciled';co.reconciled_at=now();co.reconciled_by=u.email;co.reconcile_note=note.strip()
    audit(s,u,f'离线领单核对 {co.code} 冲突{len(conflicts)}条 依据：{note.strip()}');s.commit();return co

def sign_guard(s,job_id):
    """签印/复机前调用：未核对关闭的领单一律拦截。"""
    co=active_for_job(s,job_id)
    if co:
        reason='离线领单存在冲突待核对' if co.state=='conflicted' else '离线领单未补传核对'
        raise HTTPException(409,f'{reason}（{co.code}），核对通过后才能签印')
