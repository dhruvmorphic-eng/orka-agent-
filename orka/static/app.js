const $=id=>document.getElementById(id);
let task=null, busy=false, caps={}, displayedApproval=null;
const el=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
function log(event,detail='',failed=false){$('idle').hidden=true;const row=el('div','',`log${failed?' failed':''}`);row.append(el('time',new Date().toLocaleTimeString([],{hour12:false})),el('span',event,'event'));if(detail)row.append(el('span',detail,'detail'));$('logs').append(row);$('activity-scroll').scrollTop=$('activity-scroll').scrollHeight;}
async function api(path,method='GET',body){
  log(`${method} ${path}`,body?JSON.stringify(body,null,2):'');
  const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Orka-Client':'workspace'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json();
  log(`${r.status} ${r.ok?'completed':'failed'}`,r.ok?(data.state?`task.state = "${data.state}"\nrevision = ${data.revision}`:'response received'):(typeof data.detail==='string'?data.detail:'Invalid request'),!r.ok);
  if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Please check your request and try again.');
  return data;
}
function state(){ $('send').disabled=busy||!$('prompt').value.trim();$('prompt').disabled=busy;document.querySelectorAll('.approve').forEach(b=>b.disabled=busy);$('new-chat').disabled=busy;$('history-button').disabled=busy;$('pending').hidden=!busy; }
function scroll(){ $('scroll').scrollTop=$('scroll').scrollHeight; }
function message(role,text){const n=el('div','',`msg ${role}`);if(role==='assistant')n.append(el('span','orka','speaker'));n.append(document.createTextNode(text));$('messages').append(n);return n;}
function render(t){
 task=t;displayedApproval=null;localStorage.setItem('orka_task',t.id);$('welcome').hidden=true;$('messages').replaceChildren();
 t.messages.forEach(m=>message(m.role,m.text));
 if(t.state==='clarifying'&&t.messages.at(-1)?.role==='user')message('assistant','I’ll help you shape a search plan. Tell me what you sell and who you want to reach.');
 if(t.plan){
  const b=t.brief,p=el('div','','plan');
  p.append(el('strong',`Search plan · version ${t.plan_version}`));
  [['Offer',b.offering],['Buyers',b.buyer],['Region',b.geography],['Buying evidence',b.intent],['Exclude',b.exclusions||'None specified'],['Sources',b.sources.map(s=>s.replaceAll('_',' ')).join(', ')]].forEach(([label,value])=>{const n=el('p','');n.append(el('strong',label+': '),document.createTextNode(value));p.append(n);});
  p.append(el('p',`${b.lead_count} leads · evidence within ${b.freshness_days} days · $${b.budget_usd} search cap`));
  const steps=el('ol','');t.plan.steps.forEach(s=>steps.append(el('li',s)));p.append(steps,el('small',t.plan.approval_scope+' '+t.plan.estimate+' AI planning costs are separate.'));
  if(!t.approval){displayedApproval={revision:t.revision,plan_version:t.plan_version};const b=el('button','Approve search plan','approve');b.onclick=()=>run(approve);p.append(b,el('small','Or reply “yes”. You can also tell me what to change.'));}
  else p.append(el('small','Approved and saved. Search is not connected yet; no research or emails have run.'));
  $('messages').append(p);
 }
 $('task-status').textContent=t.state.replaceAll('_',' ');$('plan-code').hidden=!t.plan;$('plan-json').textContent=t.plan?JSON.stringify({version:t.plan_version,approval:t.approval,plan:t.plan},null,2):'';
 state();scroll();
}
async function run(fn){if(busy)return;busy=true;$('error').hidden=true;state();try{await fn();}catch(e){$('error').textContent=e.message;$('error').hidden=false;log('operation.failed',e.message,true);if(task){try{render(await api('/tasks/'+task.id));}catch{}}}finally{busy=false;state();scroll();$('prompt').focus();}}
async function approve(){if(!task||!displayedApproval)throw new Error('Review the current plan before approving.');$('pending-text').textContent='Saving your approval';render(await api(`/tasks/${task.id}/approve`,'POST',displayedApproval));}
async function send(){const text=$('prompt').value.trim();if(!text)return;await run(async()=>{
 $('prompt').value='';$('prompt').style.height='auto';
 if(task&&displayedApproval&&/^(yes|approve|approved|go ahead|yes, go ahead)[.!\s]*$/i.test(text)){await approve();return;}
 if(!caps.ai_planner)throw new Error('Connect your AI key in .env and restart Orka to chat.');
 if(!task){$('pending-text').textContent='Saving your request';task=await api('/tasks','POST',{request:text});render(task);}else{message('user',text);scroll();}
 $('pending-text').textContent='Understanding your request';
 render(await api(`/tasks/${task.id}/message`,'POST',{revision:task.revision,message:text}));
 });}
$('composer').onsubmit=e=>{e.preventDefault();send();};
$('prompt').oninput=()=>{state();$('prompt').style.height='auto';$('prompt').style.height=Math.min($('prompt').scrollHeight,130)+'px';};
$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();if(!busy)send();}};
$('new-chat').onclick=()=>{if(busy)return;task=null;displayedApproval=null;localStorage.removeItem('orka_task');$('messages').replaceChildren();$('logs').replaceChildren();$('plan-code').hidden=true;$('idle').hidden=false;$('welcome').hidden=false;$('history').hidden=true;$('task-status').textContent='No active task';$('error').hidden=true;$('prompt').focus();};
$('history-button').onclick=()=>run(async()=>{if(!$('history').hidden){$('history').hidden=true;return;}const tasks=await api('/tasks');$('history').replaceChildren();if(!tasks.length)$('history').append(el('p','No saved conversations yet.'));tasks.forEach(t=>{const b=el('button',t.request);b.onclick=()=>run(async()=>{$('history').hidden=true;render(await api('/tasks/'+t.id));});$('history').append(b);});$('history').hidden=false;});
$('toggle-activity').onclick=()=>{const hidden=!$('activity-panel').hidden;$('activity-panel').hidden=hidden;$('toggle-activity').setAttribute('aria-expanded',String(!hidden));};
if(matchMedia('(max-width:760px)').matches){$('activity-panel').hidden=true;$('toggle-activity').setAttribute('aria-expanded','false');}
run(async()=>{caps=await api('/capabilities');$('connection').textContent=caps.ai_planner?'Orka · AI connected':'AI setup needed';const id=localStorage.getItem('orka_task');if(id){try{render(await api('/tasks/'+id));}catch{localStorage.removeItem('orka_task');}}});
