// sklearn 对拍的 Node 端：读取快照与基准，调用离线引擎比对标签与概率。
// 用法：node parity_check.mjs <parity-in.json> <engine.js>
import fs from 'node:fs';
import assert from 'node:assert/strict';
const [inFile,engineFile]=process.argv.slice(2);
const {predict}=await import(engineFile);
const {snapshot,cases}=JSON.parse(fs.readFileSync(inFile,'utf8'));
let maxDiff=0;
for(const c of cases){
 const r=predict(snapshot,c.features);
 assert.equal(r.label,c.label,`标签不一致 ${c.name}: js=${r.label} py=${c.label}`);
 for(const k of Object.keys(c.proba)){
  const d=Math.abs(r.probabilities[k]-c.proba[k]);maxDiff=Math.max(maxDiff,d);
  assert.ok(d<1e-4,`概率偏差过大 ${c.name}.${k}: js=${r.probabilities[k]} py=${c.proba[k]}`);
 }
 console.log(`ok ${c.name} 标签=${r.label} 概率=`,Object.fromEntries(Object.entries(r.probabilities).map(([k,v])=>[k,v.toFixed(5)])));
}
console.log('PARITY OK, 最大概率偏差 =',maxDiff.toExponential(2));
