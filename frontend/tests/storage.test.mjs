import assert from 'node:assert/strict';
const mem=new Map();
globalThis.localStorage={getItem:k=>mem.has(k)?mem.get(k):null,setItem:(k,v)=>mem.set(k,String(v)),removeItem:k=>mem.delete(k)};
const snap={labels:['合格','乳化','偏色'],scaler_mean:[1,1,1,1,.14],scaler_scale:[.1,.1,.1,.1,.05],svm_gamma:.2,
 support_vectors:[[0,0,0,0,0],[1,1,1,1,1],[-1,-1,-1,-1,-1]],n_support:[1,1,1],dual_coef:[[-1,.5,-.5],[.5,0,-1]],intercept:[0,0,0],
 pairwise_prob:[{probA:1,probB:0},{probA:1,probB:0},{probA:1,probB:0}],
 holdout:{confusion_matrix:[[10,0,0],[0,10,0],[0,0,10]],accuracy:1,train_rows:120,holdout_rows:30}};
const co={id:7,job_id:3,reference_version:'abc123',reference_count:150,model_snapshot:snap,job_snapshot:{code:'PJ-X',target_density:1.4},state:'active'};
const storage=await import('../src/offline/storage.js');
storage.saveCheckout(co);
// 登记两张离线样张：一张乳化样、一张复验合格样
const bad=storage.addProof(co,{code:'PS-OFF-1',c:1.02,m:1.04,y:1.0,k:1.05,dot_gain:28});
const good=storage.addProof(co,{code:'PS-OFF-2',c:1.4,m:1.39,y:1.41,k:1.4,dot_gain:14});
storage.classifyProof(co,bad,false);
let view=storage.localView(co);
assert.equal(view.proofs.length,2);
const p1=view.proofs.find(p=>p.code==='PS-OFF-1');
assert.ok(p1.defect&&p1.evidence.offline===true,'classified offline with evidence');
assert.equal(p1.evidence.reference_version,'abc123');
// 不合格样张生成调机（乳化默认减供水）
const adjRec=storage.addAdjustment(co,bad.client_uuid);
view=storage.localView(co);
assert.equal(view.adjustments.length,1);
const expectInk=p1.defect==='偏色'?-6:0,expectWater=p1.defect==='乳化'?-8:0;
assert.deepEqual([view.adjustments[0].ink_delta,view.adjustments[0].water_delta],[expectInk,expectWater]);
assert.equal(view.adjustments[0].status,'issued');
// 修订指令
storage.reviseInstruction(co,adjRec.client_uuid,-1,-7);
view=storage.localView(co);assert.deepEqual([view.adjustments[0].ink_delta,view.adjustments[0].water_delta],[-1,-7]);
// 执行
storage.executeAdjustment(co,adjRec.client_uuid);
view=storage.localView(co);assert.equal(view.adjustments[0].status,'executed');assert.ok(view.adjustments[0].executed_at);
// 执行后判读新样=复验
storage.classifyProof(co,good,true);
const recs=storage.listRecords(co.id);
assert.deepEqual(recs.map(r=>r.op),['proof','proof','classify','adjustment','instruction','execute','reproof']);
assert.deepEqual(recs.map(r=>r.seq),[1,2,3,4,5,6,7],'seq递增');
const pending=storage.pendingRecords(co.id);assert.equal(pending.length,7);
// 幂等标记
storage.markSynced([bad.client_uuid,good.client_uuid]);
assert.equal(storage.pendingRecords(co.id).length,5);
storage.markSynced(recs.filter(r=>!['PS-OFF-1','PS-OFF-2'].includes(r.payload.code)).map(r=>r.client_uuid).filter((u,i,a)=>a.indexOf(u)===i));
assert.equal(storage.pendingRecords(co.id).length,0);
// 复验证据带版本
view=storage.localView(co);const gp=view.proofs.find(p=>p.code==='PS-OFF-2');
assert.equal(gp.evidence.offline,true);assert.equal(gp.pass_flag,gp.defect==='合格');
console.log('offline storage flow test: OK, ops=',recs.map(r=>r.op).join(','));
