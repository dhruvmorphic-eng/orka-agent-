const $ = (id) => document.getElementById(id);
let task = null, capabilities = {}, dirty = false, busy = false;
const fields = ['offering','buyer','geography','intent','exclusions','lead_count','freshness_days','budget_usd'];
const labels = {clarifying:'Clarifying your request', awaiting_approval:'Awaiting approval', approved_waiting_integration:'Approved · integration pending'};
function notice(text='') { $('notice').textContent = text; }
async function api(path, method='GET', body) {
  const response = await fetch('/api'+path, {method, headers:{'Content-Type':'application/json','X-Orka-Client':'workspace'}, body:body === undefined ? undefined : JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Check your inputs and try again.');
  return result;
}
function node(tag, text, className) { const n=document.createElement(tag); n.textContent=text; if(className)n.className=className; return n; }
async function run(fn) {
  if(busy)return;
  busy=true; notice(); document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try {await fn();} catch(e) {notice(e.message);} finally {busy=false; document.querySelectorAll('button').forEach(b=>b.disabled=false); syncControls();}
}
function syncControls(){
  $('send-message').disabled=!capabilities.ai_planner || busy;
  $('message').disabled=!capabilities.ai_planner || busy;
  $('approve').disabled=busy || dirty || !task || task.state!=='awaiting_approval';
  $('dirty').hidden=!dirty;
}
async function listTasks(){
  const rows=await api('/tasks'); $('tasks').replaceChildren();
  rows.forEach(t=>{const b=node('button',t.request.slice(0,65),t.id===task?.id?'active':''); b.append(node('small',labels[t.state]||t.state)); b.onclick=()=>run(async()=>{if(dirty&&!confirm('Discard unsaved brief edits?'))return; render(await api('/tasks/'+t.id)); await listTasks();}); $('tasks').append(b);});
}
function render(t){
  task=t; dirty=false; localStorage.setItem('orka_task',t.id);
  $('welcome').hidden=true; $('workspace').hidden=false;
  $('task-title').textContent=t.request; $('state').textContent=labels[t.state]||t.state;
  $('version').textContent=t.plan_version?'Version '+t.plan_version:'Draft';
  $('messages').replaceChildren(...t.messages.map(m=>{const el=node('div','',`message ${m.role}`);el.append(node('strong',m.role==='user'?'You':'Orka'),document.createTextNode(m.text));return el;}));
  fields.forEach(f=>$(f).value=t.brief[f]??'');
  document.querySelectorAll('[name=sources]').forEach(el=>el.checked=t.brief.sources.includes(el.value));
  $('questions').replaceChildren(...(t.questions.length?t.questions.map(q=>node('li',q.question)):[node('li','All required details are captured. Review the plan below.')]));
  $('planner-mode').textContent=capabilities.ai_planner?'AI planning is enabled. Review extracted details before approval.':'Guided mode: complete the brief fields. AI chat needs server-side provider configuration.';
  $('plan-card').hidden=!t.plan;
  if(t.plan){
    $('plan-summary').replaceChildren(...[t.brief.geography,`${t.brief.lead_count} leads`,`${t.brief.freshness_days}-day evidence window`,`$${t.brief.budget_usd} search cap`].map(s=>node('span',s)));
    $('plan-steps').replaceChildren(...t.plan.steps.map(s=>node('li',s)));
    $('scope').textContent=t.plan.approval_scope;
    $('estimate').textContent=t.plan.estimate+' Stop when: '+t.plan.stop_conditions.join('; ')+'.';
  }
  $('approved-note').textContent=t.approval?'Approval saved for version '+t.plan_version+'. Search integration is pending. No search has run. Editing the brief revokes this approval.':'Approval applies only to this version. Editing it will require a new approval.';
  $('events').replaceChildren(...t.events.map(e=>node('li',`${new Date(e.at).toLocaleString()} · ${e.type.replaceAll('_',' ')}${e.plan_version?' · v'+e.plan_version:''}`)));
  syncControls();
}
$('new-task').onclick=()=>{if(busy)return;if(dirty&&!confirm('Discard unsaved brief edits?'))return;task=null;dirty=false;localStorage.removeItem('orka_task');$('welcome').hidden=false;$('workspace').hidden=true;notice();$('request').focus();};
$('create-form').onsubmit=e=>{e.preventDefault();run(async()=>{let t=await api('/tasks','POST',{request:$('request').value});render(t);await listTasks();if(capabilities.ai_planner){t=await api(`/tasks/${t.id}/message`,'POST',{revision:t.revision,message:t.request});render(t);await listTasks();}});};
$('brief-form').oninput=()=>{dirty=true;syncControls();};
$('brief-form').onsubmit=e=>{e.preventDefault();run(async()=>{const brief={};fields.forEach(f=>brief[f]=['lead_count','freshness_days','budget_usd'].includes(f)?($(f).value===''?null:Number($(f).value)):$(f).value);brief.sources=Array.from(document.querySelectorAll('[name=sources]:checked')).map(e=>e.value);render(await api(`/tasks/${task.id}/brief`,'PUT',{revision:task.revision,brief}));await listTasks();});};
$('message-form').onsubmit=e=>{e.preventDefault();if(!capabilities.ai_planner)return;if(dirty){notice('Save your brief edits before asking Orka to revise them.');return;}if(!$('message').value.trim())return;run(async()=>{render(await api(`/tasks/${task.id}/message`,'POST',{revision:task.revision,message:$('message').value}));$('message').value='';await listTasks();});};
$('approve').onclick=()=>run(async()=>{if(dirty)throw new Error('Save changes before approving.');render(await api(`/tasks/${task.id}/approve`,'POST',{revision:task.revision,plan_version:task.plan_version}));await listTasks();});
run(async()=>{capabilities=await api('/capabilities');const id=localStorage.getItem('orka_task');if(id){try{render(await api('/tasks/'+id));}catch{localStorage.removeItem('orka_task');}}await listTasks();});
