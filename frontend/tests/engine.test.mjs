import {predict,featureVector} from '../src/offline/engine.js';
import assert from 'node:assert/strict';
// 构造一个可控的三类快照（与后端labels顺序 合格/乳化/偏色 对齐）
const snap={
 labels:['合格','乳化','偏色'],
 scaler_mean:[1,1,1,1,.14],scaler_scale:[.1,.1,.1,.1,.05],
 svm_gamma:0.2,svm_C:2,
 support_vectors:[[0,0,0,0,0],[1,1,1,1,1],[-1,-1,-1,-1,-1]],
 n_support:[1,1,1],
 dual_coef:[[-1,0.5,-0.5],[0.5,0,-1]],
 intercept:[0,0,0],
 pairwise_prob:[{probA:1,probB:0},{probA:1,probB:0},{probA:1,probB:0}],
};
// 1) 特征向量归一化口径
const fv=featureVector({c:1.4,m:1.4,y:1.4,k:1.4},14,1.4);
assert.deepEqual(fv.map(x=>Number(x.toFixed(4))),[1,1,1,1,.14]);
// 2) 预测结构完整且概率和为1、标签在三类中
const r=predict(snap,fv);
assert.ok(snap.labels.includes(r.label));
const sum=Object.values(r.probabilities).reduce((a,b)=>a+b,0);
assert.ok(Math.abs(sum-1)<1e-9,'probs sum 1, got '+sum);
for(const v of Object.values(r.probabilities))assert.ok(v>=0&&v<=1);
// 3) 极端输入仍有限（不溢出）
const far=predict(snap,[9,9,9,9,9]);
assert.ok(Number.isFinite(far.probabilities['合格']));
assert.ok(Object.values(far.probabilities).every(Number.isFinite));
// 4) 投票标签与votes最高票一致（predict 的 OvO 规则）
const sharp={...snap,svm_gamma:5,intercept:[0,0,0]};
const near0=predict(sharp,[0,0,0,0,0]);
const top=Object.entries(near0.votes).sort((a,b)=>b[1]-a[1])[0][0];
assert.equal(near0.label,top,'label equals OvO majority, got '+near0.label);
// 5) 二类快照走sigmoid分支
const bin={labels:['合格','乳化'],scaler_mean:[0,0,0,0,0],scaler_scale:[1,1,1,1,1],svm_gamma:.5,
 support_vectors:[[0,0,0,0,0],[2,2,2,2,2]],n_support:[1,1],dual_coef:[[1,-1]],intercept:[0],pairwise_prob:[{probA:1,probB:0}]};
const rb=predict(bin,[2,2,2,2,2]);
assert.ok(Math.abs(rb.probabilities['合格']+rb.probabilities['乳化']-1)<1e-9);
assert.ok(bin.labels.includes(rb.label));
assert.ok(rb.probabilities['乳化']>=0&&rb.probabilities['乳化']<=1);
// 6) 引擎确定性：同输入两次一致
assert.deepEqual(predict(snap,fv),predict(snap,fv));
console.log('offline engine node tests: OK',r.label,Object.fromEntries(Object.entries(r.probabilities).map(([k,v])=>[k,v.toFixed(4)])));
