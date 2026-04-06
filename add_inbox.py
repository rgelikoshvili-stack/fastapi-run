# -*- coding: utf-8 -*-
with open('static/approval.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Nav item — Email Inbox (Bank Sync-ის წინ)
old_nav = '<div class="sb-item" onclick="goPage(\'bank\',this)"><span class="sb-icon-sm">🏦</span> Bank Sync</div>'
new_nav = '''<div class="sb-item" onclick="goPage('inbox',this)"><span class="sb-icon-sm">📧</span> Email Inbox <span class="sb-badge" id="sb-inbox">0</span></div>
  ''' + old_nav

content = content.replace(old_nav, new_nav)

# 2. Page content — Email Inbox (pg-bank-ის წინ)
inbox_page = '''
    <!-- EMAIL INBOX -->
    <div id="pg-inbox" class="page">
      <div class="card">
        <div class="card-header">
          <div class="card-title">📧 Email Inbox — Gmail</div>
          <div class="card-actions">
            <span class="card-badge badge-blue" id="inbox-mode">live</span>
            <button class="btn btn-ghost btn-sm" onclick="loadInbox()">⟳ განახლება</button>
          </div>
        </div>
        <div class="card-body" id="inbox-body">
          <div class="loading-row"><span class="spinner"></span></div>
        </div>
      </div>
    </div>

'''

old_bank_page = '    <!-- ═══ BANK SYNC ═══ -->'
content = content.replace(old_bank_page, inbox_page + old_bank_page)

# 3. goPage titles
content = content.replace(
    "bank:'🏦 Bank Sync'",
    "inbox:'📧 Email Inbox',bank:'🏦 Bank Sync'"
)
content = content.replace(
    "bank:'🏦 Bank Sync',",
    "inbox:'📧 Email Inbox',bank:'🏦 Bank Sync',"
)

# 4. loadPage function — inbox case
content = content.replace(
    "else if(curPage==='health')loadHealth();",
    "else if(curPage==='health')loadHealth();\n  else if(curPage==='inbox')loadInbox();"
)

# 5. loadInbox function (before INIT comment)
inbox_js = '''
// INBOX
async function loadInbox(){
  const el=document.getElementById('inbox-body');
  if(!el)return;
  el.innerHTML='<div class="loading-row"><span class="spinner"></span></div>';
  const d=await api('/email-invoice/inbox?limit=20');
  if(!d||!d.ok){el.innerHTML='<div class="empty-state"><div class="empty-icon">❌</div><div class="empty-text">Email სერვისი მიუწვდომელია</div></div>';return;}
  const emails=d.emails||[];
  document.getElementById('sb-inbox').textContent=emails.filter(e=>e.has_attachments).length;
  if(!emails.length){el.innerHTML='<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-text">Inbox ცარიელია</div></div>';return;}
  el.innerHTML=emails.map(em=>{
    const atts=em.attachments||[];
    const hasAtts=em.has_attachments;
    return `<div style="background:var(--gray-50);border:1px solid var(--gray-200);border-radius:var(--r);padding:14px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
        <div>
          <div style="font-size:13px;font-weight:700;color:var(--gray-900)">${em.subject||'(no subject)'}</div>
          <div style="font-size:11px;color:var(--gray-400);margin-top:2px">${em.from||''} · ${em.date||''}</div>
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-shrink:0;">
          ${hasAtts?`<span class="card-badge badge-blue">${atts.length} ფაილი</span>`:'<span class="card-badge badge-gray">attachment არ არის</span>'}
          ${hasAtts?`<button class="btn btn-green btn-sm" onclick="processEmail('${em.message_id}')">▶ გატარება</button>`:''}
        </div>
      </div>
      ${atts.length?`<div style="display:flex;gap:6px;flex-wrap:wrap;">
        ${atts.map(a=>`<span style="background:#fff;border:1px solid var(--gray-200);border-radius:6px;padding:4px 8px;font-size:11px;">📎 ${a.filename} (${Math.round(a.size/1024)}KB)</span>`).join('')}
      </div>`:''}
    </div>`;
  }).join('');
}

async function processEmail(msgId){
  if(!confirm('ეს email-ის invoice-ები გაიტარება. გაგრძელება?'))return;
  toast('📧 Email მუშავდება...','info');
  const d=await api('/email-invoice/confirm-process','POST',{message_id:msgId,force:false});
  if(!d||!d.ok){toast('Error','err');return;}
  const results=d.results||[];
  const dups=results.filter(r=>r.duplicate);
  const ok=results.filter(r=>!r.duplicate);
  if(dups.length){
    toast(`⚠️ ${dups.length} დუბლიკატი გამოტოვდა`,'warn');
  }
  if(ok.length){
    toast(`✅ ${ok.length} invoice გაიტარა`,'ok');
    loadKPI();loadInbox();
  }
  if(!ok.length&&!dups.length){
    toast('⚠️ attachment ვერ დამუშავდა','warn');
  }
}

'''

content = content.replace('// INIT\n', inbox_js + '// INIT\n')
if '// INIT\n' not in content:
    content = content.replace('loadPage();\n', inbox_js + 'loadPage();\n')

with open('static/approval.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
