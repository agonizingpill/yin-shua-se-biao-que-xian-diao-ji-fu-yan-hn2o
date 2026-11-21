"""sklearn 与浏览器离线判读引擎的数值对拍。

流程：用真实参考集训练 pipeline，导出模型快照与 sklearn 概率基准，
再调用 Node 运行 frontend/src/offline/engine.js 复算，逐标签/逐概率比对。
运行：cd backend && python tests/parity_generate.py
"""
import os,sys,json,pathlib,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
FRONT=ROOT.parent/'frontend'
sys.path.insert(0,str(ROOT))
DB='/tmp/qianye-parity.db';pathlib.Path(DB).unlink(missing_ok=True)
os.environ.update(DATABASE_URL='sqlite:////'+DB,REDIS_URL='redis://x/0',JWT_SECRET='test-secret-1234567890',SEED_DEMO='false')
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import src.db as dbmod
e=create_engine('sqlite:////'+DB);dbmod.engine=e;dbmod.Session=sessionmaker(e,expire_on_commit=False)
import src.main as m;m.engine=e
from src.db import Base;Base.metadata.create_all(e)
from scripts.seed_demo import seed;seed()
from src.db import Session
from src.classifier import export_model,classify
from src.models import ProofSheet
with Session() as s:
    snap=export_model(s)
    cases=[
        ('乳化坏样',ProofSheet(job_id=1,code='C1',density_c=1.02,density_m=1.04,density_y=1.0,density_k=1.05,dot_gain=28)),
        ('合格复验',ProofSheet(job_id=1,code='C2',density_c=1.4,density_m=1.39,density_y=1.41,density_k=1.4,dot_gain=14)),
        ('偏色样',ProofSheet(job_id=1,code='C3',density_c=1.7,density_m=1.1,density_y=1.55,density_k=1.4,dot_gain=15)),
        ('边界混合',ProofSheet(job_id=1,code='C4',density_c=1.25,density_m=1.3,density_y=1.2,density_k=1.35,dot_gain=20)),
    ]
    py=[]
    for name,p in cases:
        label,ev=classify(s,p)
        py.append({'name':name,'label':label,'proba':ev['probabilities'],'features':ev['features']})
payload={'snapshot':snap,'cases':py}
infile=pathlib.Path('/tmp/qianye-parity-in.json');infile.write_text(json.dumps(payload,ensure_ascii=False))
checker=pathlib.Path(__file__).parent/'parity_check.mjs'
print('sklearn 标签:',[(c['name'],c['label'])for c in py])
r=subprocess.run(['node',str(checker),str(infile),str(FRONT/'src'/'offline'/'engine.js')],capture_output=True,text=True)
print(r.stdout,end='');print(r.stderr,file=sys.stderr,end='')
sys.exit(r.returncode)
