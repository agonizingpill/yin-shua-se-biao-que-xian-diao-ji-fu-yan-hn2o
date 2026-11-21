import {esc,formData,fixed,localStamp} from '../utils/format.js';
import {badge,notify,jobLabel,empty} from '../components/press.js';
import {api,send} from '../api.js';
import {CHECKOUT_STATES,OP_LABELS} from '../constants.js';
import * as store from '../offline/storage.js';

export function render(s){
 const local=store.listCheckouts();
 const selected=local.find(c=>c.id===s.offlineId)||local[0];if(selected)s.offlineId=selected?.id;
 return `<div class="head"><div><div class="eyebrow">OFFLINE / CHECKOUT / SYNC / 10</div><h1>断网也能判色，回来再补传核对。</h1><p>领单带走当时的判读版本与开机单快照；离线用同参模型判缺陷、记调机与复验。网络恢复后按条补传，冲突留档、重新取样，核对通过才允许签印。</p></div><span class="mono" id="net-flag">网络检测中…</span></div>
 <div class="production-layout">
 <section class="section"><h2>① 领单（需联网）</h2><form id="checkout-form"><label>开机工单</label><select name="job_id">${s.jobs.map(j=>`<option value="${j.id}">${esc(j.code+' '+j.title)} · ${esc(j.status)}</option>`).join('')}</select><div class="actions"><button class="primary" ${s.user.role==='viewer'?'disabled':''}>带走判读版本离线领单</button></div></form><p class="note">领单冻结参考集指纹、模型快照与当时调机台账。同一工单存在未核对领单时禁止重复领单，也禁止签印。</p>
 <h2>③ 补传与核对（需联网）</h2>${s.offlineCheckouts?.length?s.offlineCheckouts.map(co=>`<article class="section checkout ${esc(co.state)}"><div class="eyebrow">${esc(co.code)} / ${jobLabel(s,co.job_id)}</div><h3>${CHECKOUT_STATES[co.state]||co.state} <span class="status ${co.state==='reconciled'?'pass':co.state==='conflicted'?'fail':''}">版本${esc(co.reference_version)}</span></h3><p class="muted">领单 ${esc(localStamp(co.checked_out_at))} · 参考${co.reference_count}张${co.synced_at?' · 补传 '+esc(localStamp(co.synced_at)):''}${co.reconciled_at?' · 核对 '+esc(localStamp(co.reconciled_at))+' '+esc(co.reconciled_by):''}</p>${co.state!=='reconciled'?`<div class="actions"><button data-sync="${co.id}" ${s.user.role==='viewer'?'disabled':''}>断点补传本机记录</button></div>`:''}${co.state==='conflicted'?`<form class="reconcile" data-id="${co.id}"><label>主管核对依据（冲突留档，安排重新取样）</label><textarea name="note" minlength="5" required placeholder="已核对线上调机改动，离线记录留档，重新取样在线复验"></textarea><button class="magenta" ${s.user.role==='admin'?'':'disabled'}>主管核对关闭领单</button></form>`:''}${co.reconcile_note?`<p class="note">${esc(co.reconcile_note)}</p>`:''}</article>`).join(''):empty('尚无领单记录')}</section>
 <section class="section"><h2>② 离线工作台（断网可用）</h2>${selected?offlineBoard(s,selected):empty('先联网领单，之后断网也能在本机判读与记录。')}</section>
 </div>`;
}
function offlineBoard(s,co){
 const view=store.localView(co);const recs=store.listRecords(co.id);const executed=view.adjustments.find(a=>a.status==='executed');
 const rows=view.proofs.map(p=>{
  const canAdj=!view.adjustments.some(a=>a.proof_uuid===p.uuid)&&p.defect&&!p.pass_flag;
  return `<tr><td class="mono">${esc(p.code)}</td><td class="mono">${fixed(p.density_c)}/${fixed(p.density_m)}/${fixed(p.density_y)}/${fixed(p.density_k)}</td><td class="mono">${p.dot_gain}%</td><td>${p.defect?badge(p.pass_flag?'pass':'fail',p.defect+' · 离线'):badge('unmeasured')}</td><td><button data-off-classify="${p.uuid}" data-co="${co.id}" ${p.defect||s.user.role==='viewer'?'disabled':''}>判读</button>${canAdj?` <button data-off-adj="${p.uuid}" data-co="${co.id}">生成调机</button>`:''}</td></tr>`;
 }).join('')||'<tr><td colspan="5">本机暂无离线色标</td>';
 return `<div class="checkout-head"><b class="mono">${esc(co.code)}</b><span class="status ${co.state==='reconciled'?'pass':''}">${CHECKOUT_STATES[co.state]||co.state}</span></div>
 <p class="muted">${jobLabel(s,co.job_id)} · 目标密度 ${fixed(co.job_snapshot.target_density)} · 判读版本 ${esc(co.reference_version)}（${co.reference_count}张参考）</p>
 <h3>离线登记色标${executed?'（执行后在此登记复验张，判读即标记为离线复验）':''}</h3>
 <form id="off-proof-form" data-co="${co.id}"><label>新色标编号</label><input name="code" value="PS-OFF-${Date.now().toString().slice(-6)}" required><div class="cmykfields">${['c','m','y','k'].map(k=>`<div class="tone"><label>${k.toUpperCase()} 密度</label><input name="density_${k}" type="number" min="0" max="3" step=".01" value="1.4" required></div>`).join('')}</div><label>网点扩大率 / %</label><input name="dot_gain" type="number" min="0" max="50" step=".1" value="14" required><div class="actions"><button ${s.user.role==='viewer'?'disabled':''}>离线登记色标</button></div></form>
 <div class="tablewrap"><table><thead><tr><th>色标</th><th>C/M/Y/K</th><th>扩大</th><th>离线判读</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table></div>
 <h3>离线调机与复验</h3>${view.adjustments.map(a=>`<article class="section ${a.status}"><div class="eyebrow">离线调机 / 源色标 ${esc(a.proof_code)}</div><h3>墨${a.ink_delta>0?'+':''}${a.ink_delta}% 水${a.water_delta>0?'+':''}${a.water_delta}% ${badge(a.status)}</h3>${a.status==='issued'?`<form class="off-revise" data-co="${co.id}" data-adj="${a.uuid}"><div class="formgrid"><div><label>供墨%</label><input name="ink_delta" type="number" min="-15" max="15" value="${a.ink_delta}" required></div><div><label>供水%</label><input name="water_delta" type="number" min="-15" max="15" value="${a.water_delta}" required></div></div><div class="actions"><button class="revise-btn">修订指令</button><button type="button" class="primary" data-off-exec="${a.uuid}" data-co="${co.id}" ${s.user.role==='viewer'?'disabled':''}>登记已执行</button></div></form>`:`<p class="muted">执行于 ${esc(localStamp(a.executed_at))}；请在上方登记新复验色标并判读，补传核对后供主管在线签印。</p>`}</article>`).join('')||'<p class="note">离线判为乳化/偏色后，可在对应色标上生成调机指令。</p>'}
 <div class="tablewrap"><table><thead><tr><th>#</th><th>操作</th><th>时间</th><th>补传状态</th></tr></thead><tbody>${recs.map(r=>`<tr><td>${r.seq}</td><td>${OP_LABELS[r.op]||r.op}</td><td>${esc(localStamp(r.client_ts))}</td><td>${badge(r.local_state==='synced'?'pass':'unmeasured',r.local_state==='synced'?'已补传':'待补传')}</td></tr>`).join('')}</tbody></table></div>`;
}
export function bind(s,reload){
 const flag=document.querySelector('#net-flag');
 const ping=async()=>{try{await api('/health');flag.textContent='● 在线：可领单/补传/签印';flag.style.color='var(--green)';return true;}catch{flag.textContent='○ 离线：本机工作台仍可判读记录';flag.style.color='var(--magenta)';return false;}};
 ping();
 document.querySelector('#checkout-form').onsubmit=async e=>{e.preventDefault();if(!await ping())return notify('当前离线，无法领单，请恢复网络');const d=formData(e.target);try{const co=await send('/offline/checkouts',{job_id:Number(d.job_id)});store.saveCheckout({id:co.id,code:co.code,job_id:co.job_id,reference_version:co.reference_version,reference_count:co.reference_count,model_snapshot:co.model_snapshot,job_snapshot:co.job_snapshot,state:co.state});notify('已领单，判读版本已存本机');await reload();}catch(err){notify(err.message);}};
 const board=document.querySelector('#off-proof-form');
 if(board){const co=store.getCheckout(Number(board.dataset.co));
  board.onsubmit=e=>{e.preventDefault();const d=formData(e.target);for(const k of ['density_c','density_m','density_y','density_k','dot_gain'])d[k]=Number(d[k]);store.addProof(co,d);notify('离线色标已存本机');reload();};
  document.querySelectorAll('[data-off-classify]').forEach(b=>b.onclick=()=>{const c=store.getCheckout(Number(b.dataset.co));const rec=store.listRecords(c.id).find(r=>r.client_uuid===b.dataset.offClassify);const isReproof=store.localView(c).adjustments.some(a=>a.status==='executed');store.classifyProof(c,rec,isReproof);notify('已用领单版本离线判读');reload();});
  document.querySelectorAll('[data-off-adj]').forEach(b=>b.onclick=()=>{const c=store.getCheckout(Number(b.dataset.co));store.addAdjustment(c,b.dataset.offAdj);notify('离线调机指令已生成');reload();});
  document.querySelectorAll('.off-revise').forEach(f=>f.onsubmit=e=>{e.preventDefault();if(e.submitter&&e.submitter.classList.contains('revise-btn')){const d=formData(f);store.reviseInstruction(co,f.dataset.adj,Number(d.ink_delta),Number(d.water_delta));notify('离线修订已记录');reload();}});
  document.querySelectorAll('[data-off-exec]').forEach(b=>b.onclick=()=>{store.executeAdjustment(store.getCheckout(Number(b.dataset.co)),b.dataset.offExec);notify('离线执行已记录，请重新取样复验');reload();});
 }
 document.querySelectorAll('[data-sync]').forEach(b=>b.onclick=async()=>{if(!await ping())return notify('当前离线，无法补传');const id=Number(b.dataset.sync);const localCo=store.listCheckouts().find(c=>c.id===id);if(!localCo)return notify('本机没有该领单的离线记录');const pending=store.pendingRecords(id);if(!pending.length)return notify('本机记录均已补传');try{const res=await send('/offline/checkouts/'+id+'/sync',{records:pending.map(({client_uuid,seq,op,client_ts,payload})=>({client_uuid,seq,op,client_ts,payload}))});store.markSynced(res.applied.filter(x=>x.state==='applied').map(x=>x.client_uuid));if(res.failed.length){store.markSynced(res.failed.map(x=>x.client_uuid),'conflicted');notify('补传中断/存在冲突：'+res.failed.map(f=>f.reason).join('；')+'，可重新点击续传');}else notify('补传完成，无冲突');await reload();}catch(err){notify('补传中断，已保留进度，可重试：'+err.message);}});
 document.querySelectorAll('.reconcile').forEach(f=>f.onsubmit=async e=>{e.preventDefault();try{await send('/offline/checkouts/'+f.dataset.id+'/reconcile',formData(f));notify('领单已核对关闭，离线复验张可用于签印');await reload();}catch(err){notify(err.message);}});
}
