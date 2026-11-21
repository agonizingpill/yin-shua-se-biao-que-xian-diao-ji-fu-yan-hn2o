import os,sys,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
DB='/tmp/qianye-offline-it.db'
pathlib.Path(DB).unlink(missing_ok=True)
os.environ['DATABASE_URL']='sqlite:////'+DB
os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
os.environ['JWT_SECRET']='test-secret-at-least-32-bytes-long-xx'
os.environ['SEED_DEMO']='false'

from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
import src.db as dbmod
test_engine=create_engine('sqlite:////'+DB)
dbmod.engine=test_engine;dbmod.Session=sessionmaker(test_engine,expire_on_commit=False)

from fastapi.testclient import TestClient
import src.main as mainmod
mainmod.engine=test_engine
from src.db import Base
Base.metadata.create_all(test_engine)

from scripts.seed_demo import seed
seed()
# 用不依赖Redis的健康检查替换
mainmod.r.ping=lambda:True
client=TestClient(mainmod.app)

def login(email):
    r=client.post('/auth/login',json={'email':email,'password':'Press2026!'});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
PRESS=login('pressman@qianye.demo');ADMIN=login('admin@qianye.demo')

def call(method,path,token,**kw):
    r=getattr(client,method)(path,headers=token,**kw)
    return r

from src.db import Session
from src.models import PrintJob,ProofSheet,Adjustment,Audit
from src.production_models import PlateSet
from src.dispatch_models import PressMachine,PressInspection
from src.offline_models import OfflineCheckout,OfflineRecord
from datetime import date

fails=[]
def check(name,cond,detail=''):
    print(('  ok ' if cond else 'FAIL ')+name+(' :: '+detail if detail and not cond else ''))
    if not cond:fails.append(name)

# ---------- 场景1：正常离线领单-补传-核对 ----------
jobs=client.get('/jobs',headers=PRESS).json();job=jobs[0]
r=client.post('/offline/checkouts',json={'job_id':job['id']},headers=PRESS);assert r.status_code==200,r.text
co=r.json();co_id=co['id']
check('领单带模型快照',bool(co['model_snapshot']['support_vectors']) and co['reference_count']==150)
check('领单冻结调机快照',co['adjustment_snapshot']==[])

recs=[]
def rec(op,payload,seq):
    return {'client_uuid':f'uu-{co_id}-{seq:03d}','seq':seq,'op':op,'client_ts':'2026-11-20T0%d:00:00+00:00'%seq,'payload':payload}
# 离线乳化样张
recs.append(rec('proof',{'job_id':job['id'],'code':'PS-OFF-BAD','density_c':1.02,'density_m':1.04,'density_y':1.0,'density_k':1.05,'dot_gain':28},1))
# 用导出快照在服务端无法直接复算浏览器结果，这里构造与同版本模型一致的判读证据
with Session() as s:
    from src.classifier import build_model,classify
    p_tmp=ProofSheet(job_id=job['id'],code='TMP',density_c=1.02,density_m=1.04,density_y=1.0,density_k=1.05,dot_gain=28)
    label,ev=classify(s,p_tmp)
check('坏样判为乳化',label=='乳化',label)
ev['reference_version']=co['reference_version']
recs.append(rec('classify',{'proof_code':'PS-OFF-BAD','defect':label,'classified_at':'2026-11-20T02:00:00+00:00','evidence':ev},2))
recs.append(rec('adjustment',{'proof_code':'PS-OFF-BAD'},3))
recs.append(rec('instruction',{'adjustment_uuid':f'uu-{co_id}-003','ink_delta':0,'water_delta':-7},4))
# 准备就绪印版+今日点检，供后续执行/签印
with Session() as s:
    j=s.scalar(select(PrintJob).where(PrintJob.id==job['id']))
    plate=PlateSet(job_id=j.id,version='VOFF',source_note='离线流程测试定稿来源足够长',registration_error_mm=0.08,state='ready',approved_by='admin@qianye.demo');s.add(plate)
    m=PressMachine(code='PRESS-OFF',state='ready');s.add(m);s.flush()
    s.add(PressInspection(job_id=j.id,machine_id=m.id,inspection_date=date.today(),lubricated=True,guards_checked=True,state='approved',approved_by='admin@qianye.demo'))
    s.commit()
recs.append(rec('execute',{'adjustment_uuid':f'uu-{co_id}-003','executed_at':'2026-11-20T05:00:00+00:00'},5))
# 离线复验合格张
recs.append(rec('proof',{'job_id':job['id'],'code':'PS-OFF-GOOD','density_c':1.4,'density_m':1.39,'density_y':1.41,'density_k':1.4,'dot_gain':14},6))
with Session() as s:
    p_tmp2=ProofSheet(job_id=job['id'],code='TMP2',density_c=1.4,density_m=1.39,density_y=1.41,density_k=1.4,dot_gain=14)
    label2,ev2=classify(s,p_tmp2)
check('复验样判为合格',label2=='合格',label2)
ev2['reference_version']=co['reference_version']
recs.append(rec('reproof',{'proof_code':'PS-OFF-GOOD','defect':label2,'classified_at':'2026-11-20T06:00:00+00:00','evidence':ev2},7))

# 模拟补传中断：先传前3条
r=client.post(f'/offline/checkouts/{co_id}/sync',json={'records':recs[:3]},headers=PRESS)
assert r.status_code==200,r.text;body=r.json()
check('首批3条全部落地',len(body['applied'])==3 and body['failed']==[] and body['resume_from'] is None)
# 重试前3条（幂等，不重复收样）
r=client.post(f'/offline/checkouts/{co_id}/sync',json={'records':recs[:3]},headers=PRESS);body=r.json()
with Session() as s:
    n_proof=s.scalar(select(func.count()).select_from(ProofSheet).where(ProofSheet.code.in_(['PS-OFF-BAD'])))
    n_rec=s.scalar(select(func.count()).select_from(OfflineRecord).where(OfflineRecord.checkout_id==co_id))
check('重试不重复收样/不重复记录',n_proof==1 and n_rec==3,f'proof={n_proof} rec={n_rec}')
# 续传剩余
r=client.post(f'/offline/checkouts/{co_id}/sync',json={'records':recs[3:]},headers=PRESS);assert r.status_code==200,r.text
body=r.json();check('续传全部成功',body['failed']==[] and body['state']=='active',json.dumps(body,ensure_ascii=False))
with Session() as s:
    co_row=s.get(OfflineCheckout,co_id)
    adj=s.scalar(select(Adjustment).where(Adjustment.job_id==job['id']))
    good=s.scalar(select(ProofSheet).where(ProofSheet.code=='PS-OFF-GOOD'))
    bad=s.scalar(select(ProofSheet).where(ProofSheet.code=='PS-OFF-BAD'))
check('调机按离线修订为减水7%',adj.water_delta==-7 and adj.ink_delta==0)
check('执行时间采用离线时刻',adj.executed_at=='2026-11-20T05:00:00+00:00',adj.executed_at)
check('离线证据落库并标记',good.evidence.get('offline') is True and bad.evidence.get('offline') is True)
check('补传完成写synced_at',co_row.synced_at is not None)

# 未核对前签印被守卫拦截
r=client.post(f'/adjustments/{adj.id}/sign',json={'reproof_id':good.id},headers=ADMIN)
check('未核对领单拦签印',r.status_code==409 and '核对' in r.json()['detail'],r.text)
# 主管核对
r=client.post(f'/offline/checkouts/{co_id}/reconcile',json={'note':'离线记录与线上一致，核对通过允许签印'},headers=ADMIN)
check('主管核对关闭',r.status_code==200 and r.json()['state']=='reconciled',r.text)
# 核对后用离线复验张签印成功
r=client.post(f'/adjustments/{adj.id}/sign',json={'reproof_id':good.id},headers=ADMIN)
check('核对后离线复验张可签印',r.status_code==200 and r.json()['status']=='signed',r.text)
with Session() as s:
    j=s.get(PrintJob,job['id'])
check('签印后工单量产',j.status=='production')

# ---------- 场景2：线上已改调机 → 离线记录冲突留档、重新取样 ----------
job2=client.get('/jobs',headers=PRESS).json()[1]
# 在线造一张已判读坏样+调机
with Session() as s:
    j=s.get(PrintJob,job2['id'])
    p=ProofSheet(job_id=j.id,code='PS-ONLINE-BAD',density_c=1.01,density_m=1.0,density_y=1.03,density_k=1.05,dot_gain=29,classification_state='classified',defect='乳化',pass_flag=False,classified_at='2026-11-20T01:00:00+00:00')
    s.add(p);s.flush()
    s.add(Adjustment(job_id=j.id,proof_id=p.id,ink_delta=0,water_delta=-8,status='issued'))
    s.commit();online_proof=p.id;online_adj=s.query(Adjustment).filter_by(job_id=j.id).one()
r=client.post('/offline/checkouts',json={'job_id':job2['id']},headers=PRESS);co2=r.json();co2_id=co2['id']
# 领单后线上修订调机（模拟在线仍可调机）
r=client.patch(f'/adjustments/{online_adj.id}',json={'ink_delta':0,'water_delta':-5},headers=PRESS)
check('领单后线上仍可调机',r.status_code==200,r.text)
off_recs=[
 {'client_uuid':'c2-001-xx','seq':1,'op':'proof','client_ts':'2026-11-20T03:00:00+00:00','payload':{'job_id':job2['id'],'code':'PS-OFF2-X','density_c':1.0,'density_m':1.0,'density_y':1.0,'density_k':1.0,'dot_gain':28}},
 {'client_uuid':'c2-002-xx','seq':2,'op':'adjustment','client_ts':'2026-11-20T04:00:00+00:00','payload':{'proof_code':'PS-OFF2-X'}},
]
r=client.post(f'/offline/checkouts/{co2_id}/sync',json={'records':off_recs},headers=PRESS);body=r.json()
check('离线样张落地但调机冲突',body['applied'] and body['failed'] and body['failed'][0]['reason'].find('线上')>=0,json.dumps(body,ensure_ascii=False))
with Session() as s:
    co_row=s.get(OfflineCheckout,co2_id)
    states=[x.state for x in s.scalars(select(OfflineRecord).where(OfflineRecord.checkout_id==co2_id))]
    adj_count=s.query(Adjustment).filter_by(job_id=job2['id']).count()
check('领单置冲突态且记录留档',co_row.state=='conflicted' and 'conflicted' in states)
check('冲突调机不落地（仍只有线上1条）',adj_count==1)
# 待核对期间继续拦签印（用在线流程也拦）
r=client.post(f'/offline/checkouts/{co2_id}/reconcile',json={'note':'线上已改调机，离线调机留档，安排重新取样'},headers=ADMIN)
check('冲突核对关闭',r.status_code==200 and r.json()['state']=='reconciled',r.text)

# ---------- 场景3：判读版本漂移 → 离线判读留档 ----------
job3_id=jobs[0]['id']  # 已量产的工单不能再领单，新建一个工单
r=client.post('/jobs',json={'code':'PJ-OFF-3','title':'漂移演练工单','paper':'157g 哑粉','target_density':1.4},headers=PRESS);assert r.status_code==200,r.text
job3=r.json()
r=client.post('/offline/checkouts',json={'job_id':job3['id']},headers=PRESS);co3=r.json();co3_id=co3['id']
from src.models import ReferenceSheet
with Session() as s:
    maxcode=s.scalar(select(func.max(ReferenceSheet.id)))
    s.add(ReferenceSheet(code='REF-DRIFT',density_c=1.4,density_m=1.4,density_y=1.4,density_k=1.4,dot_gain=14,label='合格'));s.commit()
drift_recs=[
 {'client_uuid':'c3-001-xx','seq':1,'op':'proof','client_ts':'2026-11-20T03:00:00+00:00','payload':{'job_id':job3['id'],'code':'PS-DRIFT','density_c':1.4,'density_m':1.4,'density_y':1.4,'density_k':1.4,'dot_gain':14}},
 {'client_uuid':'c3-002-xx','seq':2,'op':'classify','client_ts':'2026-11-20T04:00:00+00:00','payload':{'proof_code':'PS-DRIFT','defect':'合格','classified_at':'2026-11-20T04:00:00+00:00','evidence':{'reference_version':co3['reference_version']}}},
]
r=client.post(f'/offline/checkouts/{co3_id}/sync',json={'records':drift_recs},headers=PRESS);body=r.json()
check('版本漂移判读冲突留档',any('漂移' in f['reason'] for f in body['failed']),json.dumps(body,ensure_ascii=False))
with Session() as s:
    p=s.scalar(select(ProofSheet).where(ProofSheet.code=='PS-DRIFT'))
check('漂移样张保留但未判读',p is not None and p.classification_state=='unmeasured')

# ---------- 场景4：重复领单被拒 ----------
r=client.post('/offline/checkouts',json={'job_id':job3['id']},headers=PRESS)
check('未核对领单禁止重复领单',r.status_code==409,r.text)

print('\nRESULT:', 'ALL PASS' if not fails else 'FAILURES: '+','.join(fails))
sys.exit(1 if fails else 0)
