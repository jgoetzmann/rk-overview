"""The interactive demo page: CSS, JavaScript and body markup.

Everything the page needs is inlined by generate.py, including tools/demo_data.json, so
the published page is one file with no fetches. The JavaScript re-implements
rk_harness.fixedpoint and rk_harness.simulate.solve_q15 exactly; demo_data.json carries a
154-run fixture from the Python originals and the page checks itself against it on load.
"""
from __future__ import annotations

DEMO_CSS = """
.ctlbar{position:sticky;top:0;z-index:5;background:var(--surface-0);
  border-bottom:1px solid var(--line);padding:10px 0 12px;margin:0 0 18px;
  display:flex;gap:26px;flex-wrap:wrap;align-items:flex-end}
.ctl{display:flex;flex-direction:column;gap:5px}
.ctl>label{font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--text-3)}
.seg{display:flex;flex-wrap:wrap;gap:3px;background:var(--grid);border-radius:9px;padding:3px}
.seg button{appearance:none;border:1px solid transparent;background:transparent;
  color:var(--text-2);font:inherit;font-size:13px;padding:5px 11px;border-radius:7px;
  cursor:pointer;white-space:nowrap}
.seg button:hover{color:var(--text-1)}
.seg button[aria-pressed="true"]{background:var(--surface-1);border-color:var(--line);
  color:var(--text-1);font-weight:600}
.seg button .tag{font-size:10.5px;color:var(--text-3);margin-left:5px;font-weight:400}
.seg button[aria-pressed="true"] .tag{color:var(--text-2)}
.selfcheck{display:flex;align-items:center;gap:10px;font-size:13px;margin:16px 0 4px;
  padding:9px 14px;border:1px solid var(--line);border-radius:10px;background:var(--surface-1);
  max-width:76ch}
.selfcheck .dot{width:9px;height:9px;border-radius:50%;background:var(--text-3);flex:none}
.selfcheck.pass .dot{background:var(--s3)}
.selfcheck.fail .dot{background:var(--bad-fg)}
.readout{display:grid;grid-template-columns:max-content 1fr;gap:4px 18px;font-size:13px;
  align-content:start}
.readout dt{color:var(--text-2)}
.readout dd{margin:0;font-variant-numeric:tabular-nums;font-weight:600}
.readout dd.wide{font-weight:400;font-size:12.5px;color:var(--text-2)}
.demo-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:16px;
  align-items:stretch}
@media (max-width:880px){.demo-grid{grid-template-columns:1fr}}
.demo-grid>.panel{margin:0;min-width:0}
.panel>div[id]{overflow-x:auto}
.hint{font-size:12.5px;color:var(--text-3);margin:6px 0 0}
svg .bar{fill:var(--s1)}
svg .bar.classical{fill:var(--s2)}
svg .bar.sel{stroke:var(--text-1);stroke-width:1.5}
svg .ghost{fill:none;stroke:var(--text-3);stroke-width:1.5}
svg .rowlab{font-size:12.5px}
svg .rowlab.on{font-weight:700;fill:var(--text-1)}
svg .val{font-size:12px;fill:var(--text-2);font-variant-numeric:tabular-nums}
svg .refline{fill:none;stroke:var(--text-3);stroke-width:1.5;stroke-dasharray:5 4}
svg .q15line{fill:none;stroke:var(--s1);stroke-width:1.8}
svg .dot{fill:var(--s1)}
svg .dot.classical{fill:var(--s2)}
svg .dot.sel{stroke:var(--text-1);stroke-width:2}
svg .front{fill:none;stroke:var(--s1);stroke-width:1.2;stroke-dasharray:4 3;opacity:.8}
svg .hot{cursor:pointer}
.tabsm{display:flex;gap:14px;font-size:12.5px;color:var(--text-2);flex-wrap:wrap;margin:0 0 8px}
.tabsm b{color:var(--text-1)}
table.tab{font-size:12.5px;margin:8px 0 0}
table.tab td,table.tab th{padding:3px 9px}
.flip{font-size:15px;line-height:1.6;max-width:76ch;margin:10px 0 4px}
.flip b{font-variant-numeric:tabular-nums}
"""

DEMO_JS = r"""
(function(){
"use strict";
var D = window.__RKDEMO__;
if(!D){ return; }
var BUD = D.budget_cycles;

/* ---------------------------------------------------------------- Q15 primitives
   Mirrors rk_harness/fixedpoint.py. Products reach 2^30, so every shift is a
   Math.floor division rather than JavaScript's 32-bit >> operator. */
var QMIN=-32768, QMAX=32767, QONE=32768;
var POW=[], HALF=[];
for(var i=0;i<=22;i++){ POW[i]=Math.pow(2,i); HALF[i]=i>0?Math.pow(2,i-1):0; }

function chk(v){ if(v<QMIN||v>QMAX) throw new RangeError("q15 overflow"); return v; }
function rhe(x){                       /* Python round(): half to even */
  var f=Math.floor(x), d=x-f;
  if(d>0.5) return f+1;
  if(d<0.5) return f;
  return (f%2===0)?f:f+1;
}
function fromFloat(x){
  if(!isFinite(x)) throw new RangeError("non-finite");
  return chk(rhe(x*QONE));
}
function shFloor(v,k){ return Math.floor(v/POW[k]); }
function shNear(v,k){ return k===0?v:Math.floor((v+HALF[k])/POW[k]); }

/* ---------------------------------------------------------------- right-hand sides
   Operation order matches rk_harness/problems.py term for term, because float64 is
   only reproducible if the associativity is. */
var ZETA=0.1, OMEGA=1.0, MU=0.5, RR=2.0, LL=0.5, KE=0.1, KT=0.1, BB=0.02, JJ=0.02, VV=1.0;
var WX=0.3, WY=0.2, WZ=0.5;
var RCA=[[-11.0,10.0,0.0],[5.0,-6.0,1.0],[0.0,2.0,-2.0]];
var RHS={
  dahlquist:function(t,y){ return [-y[0]]; },
  damped_osc:function(t,y){ return [y[1], -2.0*ZETA*OMEGA*y[1] - OMEGA*OMEGA*y[0]]; },
  vanderpol_mild:function(t,y){ return [y[1], MU*(1.0-y[0]*y[0])*y[1] - y[0]]; },
  pendulum:function(t,y){ return [y[1], -Math.sin(y[0])]; },
  dc_motor:function(t,y){ return [(-RR*y[0]-KE*y[1]+VV)/LL, (KT*y[0]-BB*y[1])/JJ]; },
  rc_thermal:function(t,y){
    var o=[0,0,0];
    for(var r=0;r<3;r++){ o[r]=RCA[r][0]*y[0]+RCA[r][1]*y[1]+RCA[r][2]*y[2]; }
    return o;
  },
  quaternion:function(t,y){
    var q0=y[0],q1=y[1],q2=y[2],q3=y[3];
    return [0.5*(-WX*q1-WY*q2-WZ*q3), 0.5*(WX*q0+WZ*q2-WY*q3),
            0.5*(WY*q0-WZ*q1+WX*q3), 0.5*(WZ*q0+WY*q1-WX*q2)];
  }
};
var E0PEND = 1.0 - Math.cos(1.0);

function toPhys(yq, scale){
  var o=new Array(yq.length);
  for(var i=0;i<yq.length;i++){ o[i]=yq[i]/32768.0/scale; }
  return o;
}
function makeRhs(p){
  var f=RHS[p.name], sc=p.scale, ds=p.deriv_scale;
  return function(t,yq){
    var y=toPhys(yq,sc), d=f(t,y), o=new Array(d.length);
    for(var i=0;i<d.length;i++){ o[i]=fromFloat(d[i]*sc*ds); }
    return o;
  };
}

/* ---------------------------------------------------------------- the integrator
   rk_harness/simulate.py solve_q15, with the shift rule as a parameter. */
function solve(meth,p,n,mode,sampleEvery){
  var h=p.t_end/n;
  var hq=fromFloat(h/p.deriv_scale);
  var sh = (mode==="floor")?shFloor:shNear;
  var s=meth.b.length, ns=p.n_states, A=meth.A, b=meth.b, c=meth.c;
  var f=makeRhs(p);
  var y=p.y0.slice(), hk=new Array(s);
  var samples=[[0,y.slice()]];
  var peak=0, m, i, j;
  for(m=0;m<ns;m++){ if(Math.abs(y[m])>peak) peak=Math.abs(y[m]); }
  for(var step=0;step<n;step++){
    var tk=step*h;
    for(i=0;i<s;i++){
      var acc=y, row=A[i];
      for(j=0;j<i;j++){
        var rep=row[j];
        if(!rep) continue;
        var na=new Array(ns), hkj=hk[j];
        for(m=0;m<ns;m++){ na[m]=chk(acc[m]+chk(sh(hkj[m]*rep[0],rep[1]))); }
        acc=na;
      }
      for(m=0;m<ns;m++){ if(Math.abs(acc[m])>peak) peak=Math.abs(acc[m]); }
      var ki=f(tk+c[i]*h, acc), v=new Array(ns);
      for(m=0;m<ns;m++){ v[m]=chk(sh(ki[m]*hq,15)); }
      hk[i]=v;
    }
    var yn=y;
    for(i=0;i<s;i++){
      var rb=b[i];
      if(!rb) continue;
      var nv=new Array(ns), hki=hk[i];
      for(m=0;m<ns;m++){ nv[m]=chk(yn[m]+chk(sh(hki[m]*rb[0],rb[1]))); }
      yn=nv;
    }
    y=yn;
    for(m=0;m<ns;m++){ if(Math.abs(y[m])>peak) peak=Math.abs(y[m]); }
    if(sampleEvery>0 && ((step+1)%sampleEvery===0 || step===n-1)){
      samples.push([(step+1)*h, y.slice()]);
    }
  }
  return {final:y, samples:samples, peak:peak};
}

function errorOf(p, q){
  var y=toPhys(q,p.scale), s=0, i;
  if(p.metric==="energy"){
    var e=0.5*y[1]*y[1]+(1.0-Math.cos(y[0]));
    return Math.abs(e-E0PEND)/E0PEND;
  }
  if(p.metric==="norm1"){
    for(i=0;i<y.length;i++){ s+=y[i]*y[i]; }
    return Math.abs(Math.sqrt(s)-1.0);
  }
  for(i=0;i<y.length;i++){ var d=y[i]-p.ref_end[i]; s+=d*d; }
  return Math.sqrt(s)/p.peak;
}
function stepsFor(meth,p){
  var cyc=meth.cycles.m0plus_fast[String(p.n_states)];
  return cyc>0?Math.floor(BUD/cyc):0;
}
function cyclesFor(meth,p){ return meth.cycles.m0plus_fast[String(p.n_states)]; }

/* ---------------------------------------------------------------- run cache */
var CACHE={};
function run(mk,pk,mode,sample){
  var key=mk+"|"+pk+"|"+mode+"|"+(sample||0);
  if(CACHE[key]) return CACHE[key];
  var meth=METH[mk], p=PROB[pk], n=stepsFor(meth,p), out;
  if(n<=0){ out={status:"no_steps",steps:0}; }
  else{
    try{
      var r=solve(meth,p,n,mode,sample||0);
      out={status:"ok",steps:n,final:r.final,samples:r.samples,
           error:errorOf(p,r.final),
           headroom:r.peak>0?32767/r.peak:Infinity};
    }catch(e){ out={status:"overflow",steps:n}; }
  }
  CACHE[key]=out;
  return out;
}

var METH={}, PROB={};
D.methods.forEach(function(m){ METH[m.key]=m; });
D.problems.forEach(function(p){ PROB[p.name]=p; });

/* ---------------------------------------------------------------- svg helpers */
function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;"); }
function fmt(v){
  if(v===null||v===undefined||!isFinite(v)) return "n/a";
  if(v===0) return "0";
  var a=Math.abs(v);
  if(a>=1e4||a<1e-3) return v.toExponential(3).replace("e","e");
  return String(Number(v.toPrecision(4)));
}
function lg(v){ return Math.log(v)/Math.LN10; }
function logScale(lo,hi,a,bb){
  var l0=lg(lo), l1=lg(hi);
  if(!(l1>l0)){ l0-=0.5; l1+=0.5; }
  return function(v){ return a+(lg(v)-l0)/(l1-l0)*(bb-a); };
}
function decades(lo,hi){
  var out=[], k=Math.floor(lg(lo)), top=Math.ceil(lg(hi));
  for(;k<=top;k++){ out.push(Math.pow(10,k)); }
  return out;
}
function powLabel(v){
  var e=Math.round(lg(v));
  return "10" + String(e).replace(/-/g,"−").split("").map(function(ch){
    return "⁰¹²³⁴⁵⁶⁷⁸⁹".charAt("0123456789".indexOf(ch)) || "⁻";
  }).join("");
}

/* ---------------------------------------------------------------- state */
var S={prob:"damped_osc", mode:"floor", meth:"11e898cb", state:0};

/* ---------------------------------------------------------------- 1. leaderboard */
function board(){
  var p=PROB[S.prob];
  var rows=D.methods.map(function(m){
    var a=run(m.key,S.prob,S.mode,0), o=run(m.key,S.prob,S.mode==="floor"?"nearest":"floor",0);
    return {m:m, r:a, other:o};
  });
  var ok=rows.filter(function(r){ return r.r.status==="ok" && isFinite(r.r.error) && r.r.error>0; });
  /* Exact ties are a real result here, not a rounding artefact: under floor several
     methods land on the reference value itself. Order is broken by key so the list is
     stable, and rank is competition rank so tied methods share a number and a tie never
     shows up as movement between the two modes. */
  function by(f){ return function(x,y){ return f(x)-f(y) || (x.m.key<y.m.key?-1:1); }; }
  function ranks(list,f){
    var out={}, prev=null, r=0;
    list.forEach(function(z,i){ var v=f(z); if(prev===null||v!==prev){ r=i+1; prev=v; } out[z.m.key]=r; });
    return out;
  }
  ok.sort(by(function(r){ return r.r.error; }));
  var oth=ok.slice().sort(by(function(r){ return r.other.error; }));
  var rankHere=ranks(ok,function(r){ return r.r.error; });
  var rankOther=ranks(oth,function(r){ return r.other.error; });
  var tied=ok.filter(function(r){ return r.r.error===ok[0].r.error; }).length;

  var lo=ok[0].r.error, hi=ok[ok.length-1].r.error;
  ok.forEach(function(r){ var e=r.other.error; if(isFinite(e)&&e>0){ if(e<lo)lo=e; if(e>hi)hi=e; } });
  var W=760, ml=190, mr=74, rowh=27, top=30;
  var H=top+rows.length*rowh+30;
  var x=logScale(lo*0.7,hi*1.4,ml,W-mr);
  var out=['<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" role="img" aria-label="methods ranked by final error">'];
  decades(lo*0.7,hi*1.4).forEach(function(d){
    var px=x(d);
    if(px<ml-1||px>W-mr+1) return;
    out.push('<line class="gridline" x1="'+px.toFixed(1)+'" y1="'+top+'" x2="'+px.toFixed(1)+'" y2="'+(top+ok.length*rowh)+'"/>');
    out.push('<text x="'+px.toFixed(1)+'" y="'+(top-10)+'" text-anchor="middle">'+powLabel(d)+'</text>');
  });
  ok.forEach(function(r,i){
    var y=top+i*rowh, bw=x(r.r.error)-ml, cls=r.m.origin==="classical"?"bar classical":"bar";
    if(r.m.key===S.meth) cls+=" sel";
    out.push('<g class="hot" data-meth="'+esc(r.m.key)+'"><title>'+esc(r.m.label)+
      " — error "+fmt(r.r.error)+", "+cyclesFor(r.m,p)+" cycles/step, "+r.r.steps+" steps</title>");
    out.push('<rect x="0" y="'+y+'" width="'+W+'" height="'+rowh+'" fill="transparent"/>');
    out.push('<text class="rowlab'+(r.m.key===S.meth?" on":"")+'" x="'+(ml-52)+'" y="'+(y+rowh/2+4)+'" text-anchor="end">'+esc(r.m.label)+"</text>");
    out.push('<text class="val" x="'+(ml-10)+'" y="'+(y+rowh/2+4)+'" text-anchor="end">#'+rankHere[r.m.key]+
      " · "+cyclesFor(r.m,p)+"c</text>");
    out.push('<rect class="'+cls+'" x="'+ml+'" y="'+(y+6)+'" width="'+Math.max(1,bw).toFixed(1)+'" height="'+(rowh-13)+'" rx="3"/>');
    var e2=r.other.error;
    if(isFinite(e2)&&e2>0){
      var gx=x(e2);
      out.push('<line class="ghost" x1="'+gx.toFixed(1)+'" y1="'+(y+3)+'" x2="'+gx.toFixed(1)+'" y2="'+(y+rowh-4)+'"/>');
    }
    out.push('<text class="val" x="'+(W-mr+8)+'" y="'+(y+rowh/2+4)+'">'+fmt(r.r.error)+"</text>");
    out.push("</g>");
  });
  out.push("</svg>");
  document.getElementById("board").innerHTML=out.join("");

  var best=ok[0], worst=ok[ok.length-1];
  var other=S.mode==="floor"?"round-to-nearest":"floor";
  var movers=ok.map(function(r){ return {k:r.m.label, d:rankOther[r.m.key]-rankHere[r.m.key]}; })
               .filter(function(z){ return z.d!==0; })
               .sort(function(a,b){ return Math.abs(b.d)-Math.abs(a.d); });
  var head = tied>1
    ? "<b>"+tied+" methods</b> tie for first at exactly "+fmt(best.r.error)
    : "<b>"+esc(best.m.label)+"</b> ranks first at "+fmt(best.r.error);
  var line = "On <b>"+esc(S.prob)+"</b> under <b>"+esc(S.mode==="floor"?"floor (ASRS)":"round-to-nearest")+
    "</b>, "+head+" and <b>"+esc(worst.m.label)+"</b> ranks last at "+fmt(worst.r.error)+
    " (<b>"+fmt(worst.r.error/best.r.error)+"×</b> apart). ";
  line += movers.length
    ? "Switch to "+other+" and "+movers.length+" of "+ok.length+" methods change rank; the largest move is <b>"+
      esc(movers[0].k)+"</b>, by "+Math.abs(movers[0].d)+" place"+(Math.abs(movers[0].d)===1?"":"s")+"."
    : "Under "+other+" the order is unchanged.";
  document.getElementById("rankline").innerHTML=line;
}

/* ---------------------------------------------------------------- 2. trajectory */
function traj(){
  var p=PROB[S.prob], m=METH[S.meth];
  if(S.state>=p.n_states) S.state=0;
  var n=stepsFor(m,p);
  var every=Math.max(1,Math.floor(n/420));
  var r=run(S.meth,S.prob,S.mode,every);
  var W=760, H=300, ml=62, mr=14, mt=16, mb=34;
  var out=['<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" role="img" aria-label="trajectory against the reference">'];
  var lo=Infinity, hi=-Infinity, k=S.state;
  p.ref_curve.forEach(function(row){ var v=row[1+k]; if(v<lo)lo=v; if(v>hi)hi=v; });
  if(r.status==="ok"){
    r.samples.forEach(function(sm){ var v=sm[1][k]/32768.0/p.scale; if(v<lo)lo=v; if(v>hi)hi=v; });
  }
  if(!(hi>lo)){ hi=lo+1; lo=lo-1; }
  var pad=(hi-lo)*0.09; lo-=pad; hi+=pad;
  var X=function(t){ return ml+(t/p.t_end)*(W-ml-mr); };
  var Y=function(v){ return mt+(1-(v-lo)/(hi-lo))*(H-mt-mb); };
  for(var g=0;g<=4;g++){
    var vy=lo+(hi-lo)*g/4, py=Y(vy);
    out.push('<line class="gridline" x1="'+ml+'" y1="'+py.toFixed(1)+'" x2="'+(W-mr)+'" y2="'+py.toFixed(1)+'"/>');
    out.push('<text x="'+(ml-8)+'" y="'+(py+4).toFixed(1)+'" text-anchor="end">'+fmt(vy)+"</text>");
  }
  for(var t=0;t<=4;t++){
    var vt=p.t_end*t/4;
    out.push('<text x="'+X(vt).toFixed(1)+'" y="'+(H-12)+'" text-anchor="middle">'+fmt(vt)+"</text>");
  }
  out.push('<text x="'+ml+'" y="'+(H-1)+'">t</text>');
  var d1=p.ref_curve.map(function(row,i){ return (i?"L":"M")+X(row[0]).toFixed(1)+" "+Y(row[1+k]).toFixed(1); }).join(" ");
  out.push('<path class="refline" d="'+d1+'"/>');
  if(r.status==="ok"){
    var d2=r.samples.map(function(sm,i){ return (i?"L":"M")+X(sm[0]).toFixed(1)+" "+Y(sm[1][k]/32768.0/p.scale).toFixed(1); }).join(" ");
    out.push('<path class="q15line" d="'+d2+'"/>');
  }else{
    out.push('<text x="'+(W/2)+'" y="'+(H/2)+'" text-anchor="middle">the Q15 state overflowed int16 at this budget</text>');
  }
  out.push("</svg>");
  document.getElementById("traj").innerHTML=out.join("");

  var lsb=1/32768.0/p.scale;
  var rows=[
    ["method", esc(m.label)+" · order "+m.order+", "+m.stages+" stage"+(m.stages===1?"":"s")],
    ["what it is", '<span class="wide">'+esc(m.note||"")+(m.hash?" · "+esc(m.hash.slice(0,12)):"")+"</span>"],
    ["cycles per step", cyclesFor(m,p)+" (m0plus_fast, "+p.n_states+" state"+(p.n_states===1?"":"s")+")"],
    ["steps in budget", n.toLocaleString()+" at "+BUD.toLocaleString()+" cycles"],
    ["step size h", fmt(p.t_end/n)],
    ["final error", r.status==="ok"?fmt(r.error):"overflow"],
    ["one LSB", fmt(lsb)+" in physical units"],
    ["int16 headroom", r.status==="ok"?fmt(r.headroom)+"×":"—"]
  ];
  var dl=rows.map(function(z){ return "<dt>"+z[0]+"</dt><dd>"+z[1]+"</dd>"; }).join("");
  var tab='<table class="tab"><tr><th>A</th>'+m.b_frac.map(function(_,j){ return "<th>col "+j+"</th>"; }).join("")+"</tr>";
  m.A_frac.forEach(function(row,i){
    tab+="<tr><td>row "+i+"</td>"+row.map(function(v){ return "<td>"+esc(v)+"</td>"; }).join("")+"</tr>";
  });
  tab+="<tr><td><b>b</b></td>"+m.b_frac.map(function(v){ return "<td>"+esc(v)+"</td>"; }).join("")+"</tr></table>";
  document.getElementById("readout").innerHTML='<dl class="readout">'+dl+"</dl>"+tab+
    '<p class="hint">Coefficients are exact fractions; the integrator applies each as (v×m)≫s.</p>';
}

/* ---------------------------------------------------------------- 3. pareto */
function pareto(){
  var p=PROB[S.prob];
  var pts=D.methods.map(function(m){
    var r=run(m.key,S.prob,S.mode,0);
    return {m:m, x:cyclesFor(m,p), y:r.error, ok:r.status==="ok"&&isFinite(r.error)&&r.error>0};
  }).filter(function(z){ return z.ok; });
  var W=760, H=330, ml=64, mr=118, mt=18, mb=42;
  var xs=pts.map(function(z){ return z.x; }), ys=pts.map(function(z){ return z.y; });
  var X=logScale(Math.min.apply(null,xs)*0.82, Math.max.apply(null,xs)*1.22, ml, W-mr);
  var Y=logScale(Math.min.apply(null,ys)*0.6, Math.max.apply(null,ys)*1.7, H-mb, mt);
  var out=['<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" role="img" aria-label="cycles per step against final error">'];
  decades(Math.min.apply(null,xs)*0.82, Math.max.apply(null,xs)*1.22).forEach(function(d){
    var px=X(d); if(px<ml-1||px>W-mr+1) return;
    out.push('<line class="gridline" x1="'+px.toFixed(1)+'" y1="'+mt+'" x2="'+px.toFixed(1)+'" y2="'+(H-mb)+'"/>');
    out.push('<text x="'+px.toFixed(1)+'" y="'+(H-mb+16)+'" text-anchor="middle">'+powLabel(d)+"</text>");
  });
  decades(Math.min.apply(null,ys)*0.6, Math.max.apply(null,ys)*1.7).forEach(function(d){
    var py=Y(d); if(py<mt-1||py>H-mb+1) return;
    out.push('<line class="gridline" x1="'+ml+'" y1="'+py.toFixed(1)+'" x2="'+(W-mr)+'" y2="'+py.toFixed(1)+'"/>');
    out.push('<text x="'+(ml-8)+'" y="'+(py+4).toFixed(1)+'" text-anchor="end">'+powLabel(d)+"</text>");
  });
  out.push('<text x="'+ml+'" y="'+(H-6)+'">cycles per step (m0plus_fast, log)</text>');
  out.push('<text x="'+ml+'" y="'+(mt-4)+'">final error (log)</text>');
  var sorted=pts.slice().sort(function(a,b){ return a.x-b.x||a.y-b.y; });
  var front=[], bestY=Infinity;
  sorted.forEach(function(z){ if(z.y<bestY){ bestY=z.y; front.push(z); } });
  if(front.length>1){
    out.push('<path class="front" d="'+front.map(function(z,i){
      return (i?"L":"M")+X(z.x).toFixed(1)+" "+Y(z.y).toFixed(1); }).join(" ")+'"/>');
  }
  pts.forEach(function(z){
    var cls="dot"+(z.m.origin==="classical"?" classical":"")+(z.m.key===S.meth?" sel":"");
    var onFront=front.indexOf(z)>=0;
    out.push('<g class="hot" data-meth="'+esc(z.m.key)+'"><title>'+esc(z.m.label)+" — "+z.x+
      " cycles/step, error "+fmt(z.y)+(onFront?", on the frontier":"")+"</title>");
    out.push('<circle class="'+cls+'" cx="'+X(z.x).toFixed(1)+'" cy="'+Y(z.y).toFixed(1)+'" r="'+(z.m.key===S.meth?7:5)+'"/>');
    if(onFront||z.m.key===S.meth){
      out.push('<text class="val" x="'+(X(z.x)+9).toFixed(1)+'" y="'+(Y(z.y)+4).toFixed(1)+'">'+esc(z.m.key)+"</text>");
    }
    out.push("</g>");
  });
  out.push("</svg>");
  document.getElementById("pareto").innerHTML=out.join("");
  document.getElementById("paretoline").innerHTML =
    "Down and left is better. "+front.length+" of "+pts.length+
    (front.length===1?" methods sits":" methods sit")+" on the frontier for this problem: "+
    front.map(function(z){ return "<b>"+esc(z.m.label)+"</b> at "+z.x+" cycles"; }).join(", ")+".";
}

/* ---------------------------------------------------------------- self-check */
function selfCheck(){
  var el=document.getElementById("selfcheck");
  var rows=D.expected.filter(function(e){ return e.status==="ok"; });
  var idx=0, pass=0, fail=[];
  function chunk(){
    var t0=Date.now();
    while(idx<rows.length && Date.now()-t0<40){
      var e=rows[idx++];
      var got=run(e.m,e.p,e.mode,0);
      var same = got.status==="ok" && got.steps===e.steps &&
                 got.final.length===e.final.length &&
                 got.final.every(function(v,i){ return v===e.final[i]; });
      if(same) pass++; else fail.push(e.m+"/"+e.p+"/"+e.mode);
    }
    var done=idx>=rows.length;
    el.className="selfcheck"+(done?(fail.length?" fail":" pass"):"");
    el.innerHTML='<span class="dot"></span><span>'+
      (done
        ? (fail.length
            ? "<b>"+pass+" of "+rows.length+"</b> browser runs reproduce the Python evaluator exactly. Mismatched: "+esc(fail.slice(0,4).join(", "))
            : "<b>"+pass+" of "+rows.length+"</b> browser runs reproduce <span class=\"mono\">rk_harness.simulate.solve_q15</span> exactly, final int16 state and step count. The same arithmetic that scored the archive is running on this page.")
        : "checking this page's arithmetic against the Python evaluator… "+idx+" / "+rows.length)+
      "</span>";
    if(!done) setTimeout(chunk,0);
  }
  chunk();
}

/* ---------------------------------------------------------------- wiring */
function seg(id, items, get, set){
  var host=document.getElementById(id);
  host.innerHTML=items.map(function(it){
    return '<button type="button" data-v="'+esc(it.v)+'" aria-pressed="false">'+esc(it.t)+
           (it.tag?'<span class="tag">'+esc(it.tag)+"</span>":"")+"</button>";
  }).join("");
  host.addEventListener("click",function(ev){
    var b=ev.target.closest("button");
    if(!b) return;
    set(b.getAttribute("data-v"));
    render();
  });
  host.__sync=function(){
    Array.prototype.forEach.call(host.querySelectorAll("button"),function(b){
      b.setAttribute("aria-pressed", b.getAttribute("data-v")===String(get())?"true":"false");
    });
  };
}

function render(){
  ["probseg","modeseg","methseg"].forEach(function(id){
    var h=document.getElementById(id);
    if(h&&h.__sync) h.__sync();
  });
  var p=PROB[S.prob];
  var ss=document.getElementById("stateseg");
  if(p.n_states>1){
    ss.parentNode.style.display="";
    if(!ss.__n || ss.__n!==p.n_states){
      var items=[];
      for(var i=0;i<p.n_states;i++) items.push({v:String(i),t:"y"+i});
      ss.innerHTML=items.map(function(it){
        return '<button type="button" data-v="'+it.v+'" aria-pressed="false">'+it.t+"</button>"; }).join("");
      ss.__n=p.n_states;
    }
    Array.prototype.forEach.call(ss.querySelectorAll("button"),function(b){
      b.setAttribute("aria-pressed", b.getAttribute("data-v")===String(S.state)?"true":"false");
    });
  }else{
    ss.parentNode.style.display="none";
    S.state=0;
  }
  board(); traj(); pareto();
}

document.addEventListener("DOMContentLoaded",function(){
  seg("probseg", D.problems.map(function(p){
    return {v:p.name,t:p.name,tag:p.set==="search"?"search":"held out"}; }),
    function(){ return S.prob; }, function(v){ S.prob=v; S.state=0; });
  seg("modeseg", [{v:"floor",t:"floor (ASRS)"},{v:"nearest",t:"round-to-nearest"}],
    function(){ return S.mode; }, function(v){ S.mode=v; });
  seg("methseg", D.methods.map(function(m){
    return {v:m.key,t:m.label,tag:m.tag||""}; }),
    function(){ return S.meth; }, function(v){ S.meth=v; });
  document.getElementById("stateseg").addEventListener("click",function(ev){
    var b=ev.target.closest("button");
    if(!b) return;
    S.state=parseInt(b.getAttribute("data-v"),10);
    render();
  });
  ["board","pareto"].forEach(function(id){
    document.getElementById(id).addEventListener("click",function(ev){
      var g=ev.target.closest("g[data-meth]");
      if(!g) return;
      S.meth=g.getAttribute("data-meth");
      render();
    });
  });
  render();
  setTimeout(selfCheck,60);
});
})();
"""


def body(live_url: str) -> str:
    """The demo page body. Every number on it is computed in the browser at view time."""
    return f"""
<p class="herolead">Everything below runs in your browser: the Q15 primitives, the
explicit Runge&ndash;Kutta step and the error metric are a line-for-line port of
<span class="mono">rk_harness.fixedpoint</span> and
<span class="mono">rk_harness.simulate</span>. Nothing here is a pre-rendered chart, so
the ranking you see is computed from the coefficients when you click.</p>

<div class="selfcheck" id="selfcheck"><span class="dot"></span><span>checking this page's
arithmetic against the Python evaluator&hellip;</span></div>

<div class="ctlbar">
  <div class="ctl"><label for="probseg">Problem</label><div class="seg" id="probseg"></div></div>
  <div class="ctl"><label for="modeseg">Rounding of every multiply</label>
    <div class="seg" id="modeseg"></div></div>
  <div class="ctl"><label for="stateseg">State</label><div class="seg" id="stateseg"></div></div>
</div>

<h2>Rank the whole field at one cycle budget</h2>
<p class="lead">Eleven methods, one budget of 65,536 cycles, one problem. A cheap method
takes more and smaller steps inside that budget than an expensive one, so this is a
comparison of methods rather than of step sizes. The thin vertical mark on each bar is
where that method lands under the other rounding mode.</p>
<p class="flip" id="rankline"></p>
<div class="panel"><div id="board"></div></div>
<p class="hint">Click a bar to load that method into the trajectory below. Orange is
classical, blue is discovered by the search.</p>

<h2>Watch one method integrate</h2>
<div class="ctl" style="margin:0 0 12px"><label for="methseg">Method</label>
  <div class="seg" id="methseg"></div></div>
<div class="demo-grid">
  <div class="panel"><div id="traj"></div>
    <p class="hint">Dashed is the float64 reference solution; solid is the int16 state,
    converted back to physical units for display.</p></div>
  <div class="panel"><div id="readout"></div></div>
</div>

<h2>Cost against error, recomputed live</h2>
<p class="lead">The same eleven methods placed by what they cost and what they achieve on
the selected problem. The dashed line is the Pareto frontier: the methods no other method
matches on both axes at once. It is computed from the runs above, so it moves when you
change the problem or the rounding mode.</p>
<div class="panel"><div id="pareto"></div>
  <p class="hint" id="paretoline"></p></div>

<h2>How this page is checked</h2>
<p>A browser reimplementation is only worth showing if it is the same arithmetic, so the
page checks that rather than asserting it.
<span class="mono">tools/demo_data.py</span> runs
every (method, problem, rounding) case through the pinned Python evaluator and stores the
final int16 state and step count; the badge at the top recomputes all of them here and
reports how many match to the last bit. The round-to-nearest rule was pinned the same way:
it reproduces all 56 published errors in
<span class="mono">tools/floor_round.json</span>, the file the floor-bias finding is
computed from, with a maximum relative difference of 0.</p>
<p>Two honest limits. The cycle counts are the analytic cost model, not silicon; the
<a href="tradeoffs.html#speed">measured wall clock</a> is where that model is checked
against a real clock. And the archive fitness that ranks methods on the
<a href="{live_url}">findings site</a> is the RMS over four held-out problems, while this
page shows one problem at a time so the mechanism stays visible.</p>
"""


# --------------------------------------------------------------------------- landing hero

HERO_CSS = """
.hero{margin:22px 0 8px}
.hero h2{font-size:15px;margin:0 0 4px;letter-spacing:.01em}
.heroq{font-size:13.5px;color:var(--text-2);margin:0 0 12px;max-width:78ch}
.flipwrap{background:var(--surface-1);border:1px solid var(--line);border-radius:12px;
  padding:14px 16px 10px}
.flipbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 8px}
.flipbar .lab{font-size:11px;letter-spacing:.07em;text-transform:uppercase;
  color:var(--text-3)}
.flipseg{display:flex;flex-wrap:wrap;gap:3px;background:var(--grid);border-radius:9px;
  padding:3px}
.flipseg button{appearance:none;border:1px solid transparent;background:transparent;
  color:var(--text-2);font:inherit;font-size:12.5px;padding:4px 10px;border-radius:7px;
  cursor:pointer;white-space:nowrap}
.flipseg button:hover{color:var(--text-1)}
.flipseg button[aria-pressed="true"]{background:var(--surface-1);border-color:var(--line);
  color:var(--text-1);font-weight:600}
#flip{overflow-x:auto}
#flipsay{font-size:14.5px;line-height:1.6;margin:10px 0 2px;max-width:80ch}
#flipsay b{font-variant-numeric:tabular-nums}
svg .fl{stroke:var(--text-3);stroke-width:1.4;fill:none;opacity:.5}
svg .fl.up{stroke:var(--s3);opacity:1;stroke-width:2.2}
svg .fl.dn{stroke:var(--s2);opacity:1;stroke-width:2.2}
svg .fn{font-size:12.5px;fill:var(--text-2)}
svg .fn.on{fill:var(--text-1);font-weight:700}
svg .fh{font-size:11px;fill:var(--text-3);letter-spacing:.06em;text-transform:uppercase}
svg .fd{fill:var(--text-3)}
svg .fd.disc{fill:var(--s1)}
.cta{margin:14px 0 0;font-size:14px}
.cta a{font-weight:650;text-decoration:none}
.cta a:hover{text-decoration:underline}
.cta span{color:var(--text-2)}
"""

HERO_JS = r"""
(function(){
"use strict";
var H=window.__RKFLIP__;
if(!H||!document.getElementById("flip")) return;
var prob=H.default_problem, hot=null;

function esc(s){ return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function fmt(v){
  if(!isFinite(v)) return "n/a";
  var a=Math.abs(v);
  if(a>=1e4||a<1e-3) return v.toExponential(2);
  return String(Number(v.toPrecision(3)));
}
/* Competition rank: exact ties share a number, because under floor several methods land
   on the reference value itself and a tie is not movement. */
function ranked(mode){
  var xs=H.methods.map(function(m,i){ return {m:m, e:H.err[prob][mode][i]}; })
        .filter(function(z){ return z.e!==null && isFinite(z.e) && z.e>0; });
  xs.sort(function(a,b){ return a.e-b.e || (a.m.key<b.m.key?-1:1); });
  var prev=null, r=0;
  xs.forEach(function(z,i){ if(prev===null||z.e!==prev){ r=i+1; prev=z.e; } z.rank=r; });
  return xs;
}

function draw(){
  var L=ranked("floor"), R=ranked("nearest");
  var pos={}; R.forEach(function(z,i){ pos[z.m.key]=i; });
  var rank={}; R.forEach(function(z){ rank[z.m.key]=z.rank; });
  var rowh=25, top=44, W=760, H2=top+L.length*rowh+16;
  var xl=250, xr=W-250;
  var o=['<svg viewBox="0 0 '+W+' '+H2+'" width="'+W+'" height="'+H2+'" role="img" '+
         'aria-label="method ranking under floor rounding against round-to-nearest">'];
  o.push('<text class="fh" x="'+xl+'" y="20" text-anchor="end">floor (what the chip does)</text>');
  o.push('<text class="fh" x="'+xr+'" y="20" text-anchor="start">round-to-nearest</text>');
  L.forEach(function(z,i){
    var j=pos[z.m.key], y1=top+i*rowh, y2=top+j*rowh, d=z.rank-rank[z.m.key];
    var cls="fl"+(d>0?" up":d<0?" dn":"");
    var on=hot===z.m.key;
    o.push('<g class="hot" data-k="'+esc(z.m.key)+'">');
    o.push('<rect x="0" y="'+(y1-rowh/2)+'" width="'+W+'" height="'+rowh+'" fill="transparent"/>');
    o.push('<title>'+esc(z.m.label)+": rank "+z.rank+" under floor, rank "+rank[z.m.key]+
           " under round-to-nearest</title>");
    o.push('<path class="'+cls+(on?" on":"")+'" d="M'+(xl+8)+' '+y1+' C'+(xl+80)+' '+y1+' '+
           (xr-80)+' '+y2+' '+(xr-8)+' '+y2+'"'+(on?' stroke-width="3"':'')+'/>');
    o.push('<circle class="fd'+(z.m.origin==="discovered"?" disc":"")+'" cx="'+(xl+8)+'" cy="'+y1+'" r="3.5"/>');
    o.push('<text class="fn'+(on?" on":"")+'" x="'+(xl-6)+'" y="'+(y1+4)+'" text-anchor="end">'+
           z.rank+"  "+esc(z.m.label)+'  <tspan class="fd">'+fmt(z.e)+"</tspan></text>");
    o.push("</g>");
  });
  R.forEach(function(z,j){
    var y=top+j*rowh, on=hot===z.m.key;
    o.push('<g class="hot" data-k="'+esc(z.m.key)+'">');
    o.push('<circle class="fd'+(z.m.origin==="discovered"?" disc":"")+'" cx="'+(xr-8)+'" cy="'+y+'" r="3.5"/>');
    o.push('<text class="fn'+(on?" on":"")+'" x="'+(xr+6)+'" y="'+(y+4)+'">'+z.rank+"  "+
           esc(z.m.label)+'  <tspan class="fd">'+fmt(z.e)+"</tspan></text>");
    o.push("</g>");
  });
  o.push("</svg>");
  document.getElementById("flip").innerHTML=o.join("");

  var moved=L.filter(function(z){ return z.rank!==rank[z.m.key]; });
  var big=moved.slice().sort(function(a,b){
    return Math.abs(b.rank-rank[b.m.key])-Math.abs(a.rank-rank[a.m.key]); })[0];
  var tied=L.filter(function(z){ return z.e===L[0].e; }).length;
  var lead = tied>1
    ? "<b>"+tied+" methods</b> tie for first"
    : "<b>"+esc(L[0].m.label)+"</b> comes first";
  document.getElementById("flipsay").innerHTML =
    "On <b>"+esc(prob)+"</b>, the hardware's rounding alone moves <b>"+moved.length+" of "+
    L.length+"</b> methods. "+lead+" once every multiply floors"+
    (big?", and <b>"+esc(big.m.label)+"</b> shifts "+Math.abs(big.rank-rank[big.m.key])+
     " place"+(Math.abs(big.rank-rank[big.m.key])===1?"":"s"):"")+
    ". Same tableaus, same budget, same problems; only the rounding changed.";
}

function sync(){
  Array.prototype.forEach.call(document.querySelectorAll("#flipseg button"),function(b){
    b.setAttribute("aria-pressed", b.getAttribute("data-v")===prob?"true":"false");
  });
}
document.addEventListener("DOMContentLoaded",function(){
  var seg=document.getElementById("flipseg");
  seg.innerHTML=H.problems.map(function(p){
    return '<button type="button" data-v="'+esc(p)+'" aria-pressed="false">'+esc(p)+"</button>";
  }).join("");
  seg.addEventListener("click",function(ev){
    var b=ev.target.closest("button");
    if(!b) return;
    prob=b.getAttribute("data-v"); hot=null; sync(); draw();
  });
  var f=document.getElementById("flip");
  f.addEventListener("mouseover",function(ev){
    var g=ev.target.closest("g[data-k]");
    var k=g?g.getAttribute("data-k"):null;
    if(k!==hot){ hot=k; draw(); }
  });
  f.addEventListener("mouseleave",function(){ if(hot){ hot=null; draw(); } });
  sync(); draw();
});
})();
"""


def hero_body() -> str:
    """The one thing worth putting above the fold: the result, running."""
    return """
<div class="hero">
<h2>The result, in one interaction</h2>
<p class="heroq">Eleven Runge&ndash;Kutta methods, ranked by their error at an equal
65,536-cycle budget. On the left the multiplies floor, which is what an FPU-less
Cortex-M0+ actually does. On the right they round to nearest, which is what the textbooks
assume. Hover a line; switch problems.</p>
<div class="flipwrap">
  <div class="flipbar"><span class="lab">test problem</span><div class="flipseg" id="flipseg"></div></div>
  <div id="flip"></div>
  <p id="flipsay"></p>
</div>
<p class="cta"><a href="demo.html">Run it yourself &rarr;</a> <span>change the method and
the problem, watch the trajectory quantize, and read a Pareto frontier recomputed on every
click.</span></p>
</div>
"""
