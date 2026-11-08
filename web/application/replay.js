"use strict";
/* Refit execution replay. All events are fetched from the published, immutable
 * recorded run; the timeline never invents model responses or tool calls.
 */
window.RefitReplay = (() => {
  let timer=null;
  let active=null;
  const escapeHTML=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const allow=new Set(["run_started","runtime_ready","phase_started","phase_completed","sandbox_started","sandbox_cleanup","inference_requested","inference_completed","case_completed","terminal"]);
  const labels={
    run_started:"Migration started",runtime_ready:"Agent runtime ready",
    phase_started:"Evaluation phase",phase_completed:"Phase completed",
    sandbox_started:"Sandbox launched",sandbox_cleanup:"Worker cleanup",
    inference_requested:"Model request sent",inference_completed:"Model response",
    case_completed:"Agent case evaluated",terminal:"Run completed"
  };
  const kinds={
    run_started:"start",runtime_ready:"runtime",phase_started:"phase",phase_completed:"phase",
    sandbox_started:"sandbox",sandbox_cleanup:"sandbox",
    inference_requested:"model",inference_completed:"model",case_completed:"case",terminal:"finish"
  };
  const meaningful=(events)=>events.filter(e=>allow.has(e.type)).sort((a,b)=>Number(a.seq)-Number(b.seq));
  function details(e){
    const d=e.details||{};
    const list=[];
    if(d.model)list.push(["Model",d.model]);
    if(d.phase)list.push(["Phase",d.phase]);
    if(d.case)list.push(["Case",d.case]);
    if(Array.isArray(d.tools_called))list.push(["Observed tool calls",d.tools_called.length?d.tools_called.join(", "):"None recorded in this event"]);
    if(d.passed===true||d.passed===false)list.push(["Observed case result",d.passed?"Passed":"Failed"]);
    if(d.verdict&&typeof d.verdict.required_tool_observed==="boolean")list.push(["Required tool observed",d.verdict.required_tool_observed?"Yes":"No"]);
    if(d.receipt&&typeof d.receipt.verified==="boolean")list.push(["Cleanup receipt verified",d.receipt.verified?"Yes":"No"]);
    if(d.error)list.push(["Recorded error",d.error]);
    if(d.status)list.push(["Status",d.status]);
    if(d.number!==undefined)list.push(["Request",d.number]);
    return list;
  }
  function status(e){
    const d=e.details||{};
    if(d.passed===false||d.receipt?.verified===false||d.error)return "failed";
    if(d.passed===true||d.receipt?.verified===true)return "passed";
    return "neutral";
  }
  function shell(record){
    const run=record.run||{},events=meaningful(record.events||[]);
    if(!events.length)return '<section class="replay-empty">No public execution events are available for this run.</section>';
    const observed=events.filter(e=>e.type==="inference_completed").length;
    const cases=events.filter(e=>e.type==="case_completed");
    const cleanups=events.filter(e=>e.type==="sandbox_cleanup"&&e.details?.receipt?.verified===true).length;
    const summary=[
      ["Model responses",observed],
      ["Cases observed",cases.length],
      ["Verified cleanups",cleanups]
    ].map(([label,value])=>'<span class="replay-fact"><strong>'+escapeHTML(value)+'</strong><small>'+escapeHTML(label)+'</small></span>').join("");
    return '<section class="replay-screen" id="replayScreen" aria-label="Recorded agent execution playback">'+
      '<div class="replay-kicker"><span class="replay-live-indicator"></span> Recorded execution <span class="replay-kicker-right">Real event log · Read-only replay</span></div>'+
      '<div class="replay-head"><div class="replay-head-copy"><h1>Watch the agent execute.</h1><p>Model requests, tool decisions, case verdicts and sandbox receipts. Every step below comes from a recorded run.</p></div><div class="replay-head-actions"><a href="/app/runs/'+escapeHTML(run.id)+'?view=traces" class="btn">Inspect raw trace</a><button class="btn primary" type="button" id="replayPlay" aria-label="Play recorded execution">Play execution</button></div></div>'+
      '<div class="replay-shell">'+
        '<section class="replay-stage" aria-live="off">'+
          '<div class="replay-stage-horizon"><span class="replay-stage-source">'+escapeHTML(run.source||"Source model")+'</span><span aria-hidden="true" class="replay-horizon-line"></span><span class="replay-stage-target">'+escapeHTML(run.target||"Target model")+'</span></div>'+
          '<div class="replay-stage-copy"><span id="replayEventLabel" class="replay-eyebrow">Observed execution</span><h2 id="replayEventTitle">Run recorded</h2><p id="replayEventDescription">Select Play to step through the original execution events.</p><dl id="replayEventDetails" class="replay-event-details"></dl></div>'+
          '<div class="replay-stage-bottom"><div class="replay-case-status" id="replayCaseStatus">Recorded evidence</div><span id="replaySequence" class="replay-sequence">01 / '+String(events.length).padStart(2,"0")+'</span></div>'+
        '</section>'+
        '<aside class="replay-rail" aria-label="Recorded execution event timeline"><div class="replay-rail-heading"><strong>Execution trace</strong><span>'+events.length+' events</span></div>'+
         '<div class="replay-steps" id="replaySteps" role="list">'+events.map((e,i)=>
           '<button type="button" role="listitem" data-replay-index="'+i+'" class="replay-step'+(i===0?" is-active":"")+'" aria-label="Jump to event '+(i+1)+': '+escapeHTML(labels[e.type]||e.type)+'">'+
           '<span class="replay-step-no">'+String(i+1).padStart(2,"0")+'</span><span class="replay-step-content"><strong>'+escapeHTML(labels[e.type]||e.type)+'</strong><small>'+escapeHTML(e.details?.case||e.details?.phase||e.details?.model||"Observed event")+'</small></span>'+
           '<span class="replay-step-indicator '+status(e)+'"></span></button>').join("")+'</div></aside>'+
      '</div>'+
      '<div class="replay-transport"><button type="button" data-replay-command="previous" aria-label="Previous event">←</button><button type="button" data-replay-command="toggle" aria-label="Play or pause">Play / pause</button><button type="button" data-replay-command="next" aria-label="Next event">→</button>'+
        '<label for="replaySpeed">Speed</label><select id="replaySpeed" aria-label="Replay speed"><option value="1">1×</option><option value="2" selected>2×</option><option value="4">4×</option></select>'+
        '<input type="range" min="0" max="'+Math.max(0,events.length-1)+'" value="0" id="replayScrub" aria-label="Go to recorded event">'+
        '<span id="replayProgress">1 / '+events.length+'</span></div>'+
      '<div class="replay-evidence-footer">'+summary+'<a href="/app/agents" class="replay-cta">Try a live agent run →</a></div>'+
      '<p class="replay-provenance">This is playback of an existing Python agent evaluation—not a new inference request. Individual results are limited to the recorded cases. The separate upstream tau2 24/24, 13/24 and 24/24 study is not this execution.</p>'+
    '</section>';
  }
  function mount(record){
    stop();
    const root=document.querySelector("#replayScreen");
    if(!root)return;
    const events=meaningful(record.events||[]);
    if(!events.length)return;
    const ctx={root,events,index:0,speed:2,playing:false};
    active=ctx;
    const btn=root.querySelector("#replayPlay");
    const title=root.querySelector("#replayEventTitle");
    const caption=root.querySelector("#replayEventDescription");
    const detail=root.querySelector("#replayEventDetails");
    const eyebrow=root.querySelector("#replayEventLabel");
    const counter=root.querySelector("#replayProgress");
    const sequence=root.querySelector("#replaySequence");
    const progress=root.querySelector("#replayScrub");
    const verdict=root.querySelector("#replayCaseStatus");
    function paint(next){
      ctx.index=Math.max(0,Math.min(events.length-1,next));
      const e=events[ctx.index],d=e.details||{};
      title.textContent=labels[e.type]||e.type.replaceAll("_"," ");
      eyebrow.textContent=[d.model,d.phase].filter(Boolean).join(" · ")||"Recorded event "+String(e.seq??ctx.index+1);
      caption.textContent=d.case?("Agent case: "+d.case):d.model?("Observed "+(e.type==="inference_completed"?"response from ":"execution with ")+d.model+"."):(e.type==="sandbox_cleanup"?"Worker cleanup recorded and checked against its receipt.":"The next observed step in the agent execution.");
      detail.innerHTML=details(e).map(([label,value])=>'<div><dt>'+escapeHTML(label)+'</dt><dd>'+escapeHTML(value)+'</dd></div>').join("")||
        '<div><dt>Event</dt><dd>'+escapeHTML(e.type)+'</dd></div>';
      verdict.textContent=e.type==="case_completed"?(d.passed===true?"Case passed":d.passed===false?"Case failed":"Case observation recorded"):
        e.type==="sandbox_cleanup"?(d.receipt?.verified===true?"Cleanup verified":"Cleanup observed"):
        e.type==="inference_completed"?"Model response observed":"Recorded evidence";
      verdict.dataset.verdict=status(e);
      counter.textContent=(ctx.index+1)+" / "+events.length;
      sequence.textContent=String(ctx.index+1).padStart(2,"0")+" / "+String(events.length).padStart(2,"0");
      progress.value=String(ctx.index);
      for(const node of root.querySelectorAll("[data-replay-index]"))node.classList.toggle("is-active",Number(node.dataset.replayIndex)===ctx.index);
      root.querySelector('.replay-step.is-active')?.scrollIntoView({block:"nearest",behavior:"smooth"});
    }
    function schedule(){
      clearTimeout(timer);
      if(!ctx.playing)return;
      if(ctx.index>=events.length-1){pause();return;}
      timer=setTimeout(()=>{if(active!==ctx)return;paint(ctx.index+1);schedule();},Math.round(1900/ctx.speed));
    }
    function pause(){ctx.playing=false;clearTimeout(timer);btn.textContent="Resume execution";}
    function play(){if(ctx.index===events.length-1)paint(0);ctx.playing=true;btn.textContent="Pause replay";schedule();}
    function toggle(){ctx.playing?pause():play();}
    root.addEventListener("click",event=>{
      const target=event.target.closest("[data-replay-index],[data-replay-command],#replayPlay");
      if(!target)return;
      if(target.dataset.replayIndex!==undefined){pause();paint(Number(target.dataset.replayIndex));}
      else {
        const command=target.dataset.replayCommand||"toggle";
        if(command==="next"){pause();paint(ctx.index+1);}
        else if(command==="previous"){pause();paint(ctx.index-1);}
        else toggle();
      }
    });
    root.querySelector("#replaySpeed").addEventListener("change",event=>{ctx.speed=Math.max(1,Math.min(4,Number(event.target.value)||1));if(ctx.playing)schedule();});
    progress.addEventListener("input",event=>{pause();paint(Number(event.target.value));});
    paint(0);
    const query=new URLSearchParams(location.search);
    if(query.get("autoplay")==="1")play();
  }
  function stop(){clearTimeout(timer);timer=null;active=null;}
  return {shell,mount,stop,labels};
})();
