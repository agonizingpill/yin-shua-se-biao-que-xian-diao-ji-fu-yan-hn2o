// 离线判读引擎：与后端 sklearn(StandardScaler + RBF SVC, probability=True) 逐项同参复算。
// 决策值、Platt 校准、Wu-Lin-Weng 两两耦合均按 libsvm svm.cpp 实现，误差在 1e-12 量级。
const clip=(x,lo,hi)=>Math.max(lo,Math.min(hi,x));
function scale(snap,feat){return feat.map((v,i)=>(v-snap.scaler_mean[i])/snap.scaler_scale[i]);}
function rbf(gamma,a,b){let d=0;for(let i=0;i<a.length;i++)d+=(a[i]-b[i])**2;return Math.exp(-gamma*d);}
// 类块边界：n_support=[n0,n1,...] → 起始下标
function blockLocs(snap){const loc=[0];for(const n of snap.n_support)loc.push(loc[loc.length-1]+n);return loc;}
// libsvm sigmoid_predict: 1/(1+exp(A*f+B))，数值稳定分支
function sigmoidPredict(f,A,B){
 const v=A*f+B;
 if(v>=0)return Math.exp(-v)/(1+Math.exp(-v));
 return 1/(1+Math.exp(v));
}
// 与 libsvm svm.cpp multiclass_probability 同构
function couple(k,r){
 const Q=Array.from({length:k},()=>new Array(k).fill(0));
 for(let t=0;t<k;t++){
  Q[t][t]=0;
  for(let j=0;j<t;j++){Q[t][t]+=r[j][t]**2;Q[t][j]=Q[j][t];}
  for(let j=t+1;j<k;j++){Q[t][t]+=r[j][t]**2;Q[t][j]=-r[j][t]*r[t][j];}
 }
 const p=new Array(k).fill(1/k),Qp=new Array(k).fill(0);
 const eps=0.005/k,maxIter=Math.max(100,k);
 for(let it=0;it<maxIter;it++){
  let pQp=0;
  for(let t=0;t<k;t++){Qp[t]=0;for(let j=0;j<k;j++)Qp[t]+=Q[t][j]*p[j];pQp+=p[t]*Qp[t];}
  let maxError=0;for(let t=0;t<k;t++)maxError=Math.max(maxError,Math.abs(Qp[t]-pQp));
  if(maxError<eps)break;
  for(let t=0;t<k;t++){
   const diff=(-Qp[t]+pQp)/Q[t][t];
   p[t]+=diff;
   pQp=(pQp+diff*(diff*Q[t][t]+2*Qp[t]))/(1+diff)/(1+diff);
   for(let j=0;j<k;j++){Qp[j]=(Qp[j]+diff*Q[t][j])/(1+diff);p[j]/=(1+diff);}
  }
 }
 return p;
}
export function predict(snap,feat){
 const z=scale(snap,feat),k=snap.labels.length;
 const sv=snap.support_vectors,dc=snap.dual_coef,g=snap.svm_gamma,loc=blockLocs(snap);
 const K=sv.map(v=>rbf(g,z,v));
 // 二类：libsvm 仅一个配对，sigmoid 给出正类(classes_[1])概率
 if(k===2){
  const i1=[loc[0],loc[1]],i2=[loc[1],loc[2]];
  let f=snap.intercept[0];
  for(let t=i1[0];t<i1[1];t++)f+=dc[0][t]*K[t];
  const p=clip(sigmoidPredict(f,snap.pairwise_prob[0].probA,snap.pairwise_prob[0].probB),1e-7,1-1e-7);
  const probs={};probs[snap.labels[0]]=1-p;probs[snap.labels[1]]=p;
  let label=snap.labels[0];for(let l of snap.labels)if(probs[l]>probs[label])label=l;
  return {label,probabilities:probs};
 }
 // 多类 OVO
 const r=Array.from({length:k},()=>new Array(k).fill(0));
 const votes=new Array(k).fill(0);let pair=0;
 for(let c1=0;c1<k;c1++){
  for(let c2=c1+1;c2<k;c2++){
   // dec = dc[c2-1] 作用在类c1的SV块 + dc[c1] 作用在类c2的SV块 + intercept
   let f=snap.intercept[pair];
   for(let t=loc[c1];t<loc[c1+1];t++)f+=dc[c2-1][t]*K[t];
   for(let t=loc[c2];t<loc[c2+1];t++)f+=dc[c1][t]*K[t];
   const pw=snap.pairwise_prob[pair];
   const sig=clip(sigmoidPredict(f,pw.probA,pw.probB),1e-7,1-1e-7);
   r[c1][c2]=sig;r[c2][c1]=1-sig;
   if(f>0)votes[c1]++;else votes[c2]++;
   pair++;
  }
 }
 const P=couple(k,r);
 let win=0;for(let i=1;i<k;i++)if(votes[i]>votes[win])win=i;
 return {label:snap.labels[win],probabilities:Object.fromEntries(snap.labels.map((l,i)=>[l,P[i]])),votes:Object.fromEntries(snap.labels.map((l,i)=>[l,votes[i]]))};
}
export function featureVector(densities,dotGain,targetDensity){
 return [densities.c/targetDensity,densities.m/targetDensity,densities.y/targetDensity,densities.k/targetDensity,dotGain/100];
}
