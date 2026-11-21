import {predict,featureVector} from './engine.js';
const KEY='press-offline-v1';
export const uuid=()=>(crypto.randomUUID?crypto.randomUUID():'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return (c==='x'?r:(r&3|8)).toString(16);}));
export const stamp=()=>new Date().toISOString();
function load(){try{return JSON.parse(localStorage.getItem(KEY))||{checkouts:[],records:[]};}catch{return {checkouts:[],records:[]};}}
function save(db){localStorage.setItem(KEY,JSON.stringify(db));}
export function listCheckouts(){return load().checkouts;}
export function getCheckout(id){return load().checkouts.find(c=>c.id===id);}
export function saveCheckout(co){const db=load();const i=db.checkouts.findIndex(c=>c.id===co.id);if(i>=0)db.checkouts[i]=co;else db.checkouts.push(co);save(db);return co;}
export function listRecords(coId){return load().records.filter(r=>r.checkout_id===coId).sort((a,b)=>a.seq-b.seq);}
export function pendingRecords(coId){return listRecords(coId).filter(r=>r.local_state!=='synced');}
function addRecord(coId,op,payload){
 const db=load();const mine=db.records.filter(r=>r.checkout_id===coId);
 const rec={client_uuid:uuid(),checkout_id:coId,seq:mine.length+1,op,client_ts:stamp(),payload,local_state:'pending'};
 db.records.push(rec);save(db);return rec;
}
export function markSynced(uuids,state='synced'){
 const db=load();for(const r of db.records)if(uuids.includes(r.client_uuid))r.local_state=state;save(db);
}
export function addProof(co,d){
 const rec=addRecord(co.id,'proof',{job_id:co.job_id,code:d.code,density_c:d.c,density_m:d.m,density_y:d.y,density_k:d.k,dot_gain:d.dot_gain});
 return rec;
}
export function classifyProof(co,proof,isReproof){
 const feat=featureVector({c:proof.payload.density_c,m:proof.payload.density_m,y:proof.payload.density_y,k:proof.payload.density_k},proof.payload.dot_gain,co.job_snapshot.target_density);
 const r=predict(co.model_snapshot,feat);
 const rounded={};for(const k of Object.keys(r.probabilities))rounded[k]=Number(r.probabilities[k].toFixed(5));
 const evidence={reference_version:co.reference_version,reference_count:co.reference_count,probabilities:rounded,labels:co.model_snapshot.labels,confusion_matrix:co.model_snapshot.holdout.confusion_matrix,accuracy:co.model_snapshot.holdout.accuracy,train_rows:co.model_snapshot.holdout.train_rows,holdout_rows:co.model_snapshot.holdout.holdout_rows,seed:42,current_proof_code:proof.payload.code,feature_names:['青密度比','品红密度比','黄密度比','黑密度比','网点扩大率'],features:feat,offline:true};
 return addRecord(co.id,isReproof?'reproof':'classify',{proof_code:proof.payload.code,defect:r.label,classified_at:stamp(),evidence});
}
export function addAdjustment(co,proofUuid){return addRecord(co.id,'adjustment',{proof_uuid:proofUuid,proof_code:proofCode(co,proofUuid)});}
export function reviseInstruction(co,adjUuid,ink,water){return addRecord(co.id,'instruction',{adjustment_uuid:adjUuid,ink_delta:ink,water_delta:water});}
export function executeAdjustment(co,adjUuid){return addRecord(co.id,'execute',{adjustment_uuid:adjUuid,executed_at:stamp()});}
function proofCode(co,proofUuid){return listRecords(co.id).find(r=>r.client_uuid===proofUuid)?.payload?.code;}
// 离线视图：把本地记录折叠成样张/调机两张工作台视图
export function localView(co){
 const proofs=[],adjustments=[];const proofByUuid={},proofByCode={};let adjByUuid={};
 for(const r of listRecords(co.id)){
  if(r.op==='proof'){const v={uuid:r.client_uuid,...r.payload,classification_state:'unmeasured',defect:null,pass_flag:false,evidence:null,classified_at:null,offline:true};proofs.push(v);proofByUuid[r.client_uuid]=v;proofByCode[v.code]=v;}
  if(r.op==='classify'||r.op==='reproof'){const v=proofByCode[r.payload.proof_code];if(v){v.classification_state='classified';v.defect=r.payload.defect;v.pass_flag=r.payload.defect==='合格';v.evidence=r.payload.evidence;v.classified_at=r.payload.classified_at;}}
  if(r.op==='adjustment'){const src=proofByUuid[r.payload.proof_uuid];const ink=src&&src.defect==='偏色'?-6:0,water=src&&src.defect==='乳化'?-8:0;const a={uuid:r.client_uuid,proof_uuid:r.payload.proof_uuid,proof_code:r.payload.proof_code,ink_delta:ink,water_delta:water,status:'issued',executed_at:null,offline:true};adjustments.push(a);adjByUuid[r.client_uuid]=a;}
  if(r.op==='instruction'){const a=adjByUuid[r.payload.adjustment_uuid];if(a){a.ink_delta=r.payload.ink_delta;a.water_delta=r.payload.water_delta;}}
  if(r.op==='execute'){const a=adjByUuid[r.payload.adjustment_uuid];if(a){a.status='executed';a.executed_at=r.payload.executed_at;}}
 }
 return {proofs,adjustments};
}
