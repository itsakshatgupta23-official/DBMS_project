/**
 * Chronicle – main.js
 * Global JS: modal system, fetch helpers, flash auto-dismiss,
 * notification polling.
 */

// ═══════════════════════════════════════
// MODAL SYSTEM
// ═══════════════════════════════════════

/**
 * Open modal and load HTML from a URL into #modal-content.
 * @param {string} url
 */
async function openModal(url) {
  const overlay = document.getElementById('modal-overlay');
  const content = document.getElementById('modal-content');
  content.innerHTML = '<div style="text-align:center;padding:2rem;"><div class="spinner"></div></div>';
  overlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  try {
    const res = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    content.innerHTML = await res.text();
  } catch (e) {
    content.innerHTML = `<p style="color:#fca5a5;text-align:center;">Failed to load content.<br><small>${e.message}</small></p>`;
  }
}

/** Close modal when clicking the dark overlay (not the box itself). */
function closeModal(event) {
  if (event.target === document.getElementById('modal-overlay')) {
    closeModalBtn();
  }
}

/** Close modal programmatically. */
function closeModalBtn() {
  const overlay = document.getElementById('modal-overlay');
  overlay.classList.add('hidden');
  document.body.style.overflow = '';
  document.getElementById('modal-content').innerHTML = '';
}

// Close on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModalBtn();
});


// ═══════════════════════════════════════
// FLASH & TOAST MESSAGES (programmatic)
// ═══════════════════════════════════════

function showFlash(message, type = 'info') {
  const container = document.getElementById('flash-container');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `alert alert-${type} flash-msg`;
  div.innerHTML = `${message} <button class="alert-close" onclick="this.parentElement.remove()">×</button>`;
  container.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}

function showToast(message, type = 'danger') {
  showFlash(message, type);
}
window.showFlash = showFlash;
window.showToast = showToast;

// Auto-dismiss existing flash messages after 4 s
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash-msg').forEach((el) => {
    setTimeout(() => el.remove(), 4000);
  });
});


// ═══════════════════════════════════════
// CREATE SPACE HANDLER
// ═══════════════════════════════════════

async function createSpace(event) {
  if (event) event.preventDefault();
  const form = event ? (event.target.tagName === 'FORM' ? event.target : event.target.closest('form')) : document.getElementById('create-space-form');
  if (!form) return;

  const btn  = form.querySelector('[type=submit]');
  const orig = btn ? btn.innerHTML : null;
  if (btn) {
    btn.innerHTML = '<span class="spinner"></span> Creating...';
    btn.disabled = true;
  }

  const nameInput = form.querySelector('[name=name]');
  const descInput = form.querySelector('[name=description]');
  const typeInput = form.querySelector('[name=space_type]');

  const spaceName = nameInput ? nameInput.value.trim() : '';
  const spaceDesc = descInput ? descInput.value.trim() : '';
  const spaceType = typeInput ? typeInput.value.trim() : 'Other';

  if (!spaceName) {
    showToast('Space name is required', 'danger');
    if (btn) { btn.innerHTML = orig; btn.disabled = false; }
    return;
  }

  try {
    const response = await fetch('/spaces/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({ name: spaceName, description: spaceDesc, space_type: spaceType })
    });

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      const result = await response.json();

      if (response.status === 401) {
        showToast(result.error || 'Session expired. Please log in again.', 'danger');
        setTimeout(() => { window.location.href = '/login'; }, 1200);
        return;
      }

      if (response.ok && result.success !== false) {
        closeModalBtn(); // Close the modal instantly
        window.location.href = result.redirect_url || result.redirect || '/dashboard';
        return;
      } else {
        showToast(result.error || 'Failed to create space', 'danger');
      }
    } else {
      const errorText = await response.text();
      console.error('Non-JSON response received:', errorText);
      showToast('Server error during space creation. Please check backend logs.', 'danger');
    }
  } catch (error) {
    console.error('Error creating space:', error);
    showToast('Network error: ' + error.message, 'danger');
  } finally {
    if (btn) { btn.innerHTML = orig; btn.disabled = false; }
  }
}
window.createSpace = createSpace;


// ═══════════════════════════════════════
// GENERIC FETCH FORM SUBMIT
// ═══════════════════════════════════════

/**
 * Submit a form inside a modal via fetch and show flash messages or reload.
 * Verifies application/json content-type before parsing to avoid syntax crashes.
 * Usage: <form onsubmit="submitModalForm(event, '/endpoint')">
 */
async function submitModalForm(event, url, reloadTarget = null) {
  event.preventDefault();
  const form = event.target;
  const btn  = form.querySelector('[type=submit]');
  const orig = btn ? btn.innerHTML : null;
  if (btn) {
    btn.innerHTML = '<span class="spinner"></span> Creating...';
    btn.disabled = true;
  }

  try {
    const formData = new FormData(form);
    const formObj  = Object.fromEntries(formData.entries());

    const hasFile = Array.from(form.elements).some(el => el.type === 'file' && el.files && el.files.length > 0);
    const headers = {
      'Accept': 'application/json',
      'X-Requested-With': 'XMLHttpRequest'
    };
    let body;

    if (hasFile) {
      body = formData;
    } else {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(formObj);
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: headers,
      body: body
    });

    const contentType = response.headers.get('content-type');
    if (contentType && contentType.includes('application/json')) {
      const result = await response.json();

      if (response.status === 401) {
        showToast(result.error || 'Session expired. Please log in again.', 'danger');
        setTimeout(() => { window.location.href = '/login'; }, 1200);
        return;
      }

      if (response.ok && result.success !== false) {
        if (result.redirect_url || result.redirect) {
          closeModalBtn(); // Close modal instantly upon successful creation
          window.location.href = result.redirect_url || result.redirect;
          return;
        }
        if (result.reload) {
          closeModalBtn();
          window.location.reload();
          return;
        }
        if (result.message) {
          showToast(result.message, 'success');
          closeModalBtn();
          if (reloadTarget) {
            document.querySelector(reloadTarget)?.dispatchEvent(new Event('chronicle:refresh'));
          }
        }
      } else {
        showToast(result.error || 'Failed to process request.', 'danger');
      }
    } else {
      const errorText = await response.text();
      console.error('Non-JSON response received:', errorText);
      showToast('Server error during space creation. Please check backend logs.', 'danger');
    }
  } catch (e) {
    console.error('Network or parsing error:', e);
    showToast('Network error: ' + e.message, 'danger');
  } finally {
    if (btn) { btn.innerHTML = orig; btn.disabled = false; }
  }
}
window.submitModalForm = submitModalForm;


// ═══════════════════════════════════════
// NOTIFICATION BADGE POLLING (every 30s)
// ═══════════════════════════════════════

function pollNotifications() {
  const badge = document.getElementById('notif-badge');
  if (!badge) return;

  setInterval(async () => {
    try {
      const res  = await fetch('/notifications/count');
      const data = await res.json();
      badge.textContent = data.count ?? 0;
      badge.style.display = (data.count > 0) ? 'inline-flex' : 'none';
    } catch (_) {}
  }, 30_000);
}

document.addEventListener('DOMContentLoaded', pollNotifications);


// ═══════════════════════════════════════
// CHAT POLLING & RENDERING (used by chat.html)
// ═══════════════════════════════════════

let _lastMsgId  = 0;
let _chatPoller = null;

function startChatPolling(spaceId, conversationId = null) {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  // Set initial last ID from existing messages in DOM
  const msgs = container.querySelectorAll('[data-msg-id]');
  msgs.forEach(m => {
    const id = parseInt(m.dataset.msgId) || 0;
    if (id > _lastMsgId) _lastMsgId = id;
  });

  async function poll() {
    const base = conversationId
      ? `/spaces/${spaceId}/private/${conversationId}/poll`
      : `/spaces/${spaceId}/chat/poll`;
    try {
      const res  = await fetch(`${base}?after=${_lastMsgId}`);
      const data = await res.json();
      if (data.messages && data.messages.length > 0) {
        data.messages.forEach(appendChatMessage);
        scrollChatToBottom();
      }
    } catch (_) {}
  }

  _chatPoller = setInterval(poll, 4000); // Poll every 4s – Aiven supports high concurrency
  scrollChatToBottom();
}

function stopChatPolling() {
  if (_chatPoller) clearInterval(_chatPoller);
}

function appendChatMessage(msg) {
  const container = document.getElementById('chat-messages');
  if (!container || !msg || !msg.message_id) return;

  // Strict deduplication: check if message with this ID is already in the DOM
  if (container.querySelector(`[data-msg-id="${msg.message_id}"]`)) {
    return;
  }

  const isMine = msg.is_mine;
  const div = document.createElement('div');
  div.dataset.msgId = msg.message_id;
  div.className = `chat-msg ${isMine ? 'chat-msg-mine' : 'chat-msg-other'}`;

  // Attachment markup
  let attachmentHtml = '';
  if (msg.file_url) {
    const isImg = (msg.file_type && ['jpg','jpeg','png','gif','webp','svg'].includes(msg.file_type.toLowerCase())) ||
                  (/\.(jpeg|jpg|gif|png|webp|svg)($|\?)/i.test(msg.file_url));
    const dlUrl = msg.file_url.includes('/upload/')
      ? msg.file_url.replace('/upload/', '/upload/fl_attachment/')
      : msg.file_url;
    const fileName = escHtml(msg.original_filename || (isImg ? 'Photo' : 'Attachment'));

    if (isImg) {
      attachmentHtml = `
        <div class="chat-attachment-img-box">
          <a href="${msg.file_url}" target="_blank">
            <img src="${msg.file_url}" alt="${fileName}" class="chat-img-thumb" loading="lazy" />
          </a>
          <div class="chat-attachment-meta">
            <span class="chat-filename">${fileName}</span>
            <a href="${dlUrl}" download="${fileName}" target="_blank" class="btn-chat-dl">📥 Download</a>
          </div>
        </div>
      `;
    } else {
      attachmentHtml = `
        <div class="chat-attachment-doc-box">
          <div class="chat-doc-info">
            <span class="chat-doc-icon">📄</span>
            <span class="chat-filename">${fileName}</span>
          </div>
          <a href="${dlUrl}" download="${fileName}" target="_blank" class="btn-chat-dl">📥 Download</a>
        </div>
      `;
    }
  }

  const isPinned = msg.is_pinned === 1 || msg.is_pinned === true || msg.is_pinned === '1';

  div.innerHTML = `
    ${!isMine ? `<div class="chat-msg-sender">${escHtml(msg.sender)}</div>` : ''}
    ${msg.message ? `<div class="chat-msg-text">${escHtml(msg.message)}</div>` : ''}
    ${attachmentHtml}
    <div class="chat-msg-footer">
      <span class="chat-msg-time">${msg.time || ''}</span>
      <span class="pin-badge ${isPinned ? '' : 'hidden'}" id="pin-badge-${msg.message_id}" title="Pinned to Notes">📌</span>
      <button type="button" class="btn-pin-note" onclick="pinToNotes(${msg.message_id}, this)" title="Pin to Notes">
        📌 Pin to Notes
      </button>
    </div>
  `;
  container.appendChild(div);

  // Update _lastMsgId so polling doesn't re-fetch messages we already received
  const msgIdNum = parseInt(msg.message_id) || 0;
  if (msgIdNum > _lastMsgId) {
    _lastMsgId = msgIdNum;
  }
}
window.appendChatMessage = appendChatMessage;

function renderMessages(messages) {
  const chatContainer = document.getElementById('chat-messages');
  if (!chatContainer || !Array.isArray(messages)) return;

  // Wipe any optimistic/temporary elements before re-rendering from server payload
  chatContainer.innerHTML = '';
  // Reset tracker so appendChatMessage rebuilds _lastMsgId from fresh data
  _lastMsgId = 0;

  messages.forEach(msg => {
    appendChatMessage(msg);
  });
  scrollChatToBottom();
}
window.renderMessages = renderMessages;

function scrollChatToBottom() {
  const c = document.getElementById('chat-messages');
  if (c) c.scrollTop = c.scrollHeight;
}

async function sendChatMessage(event, spaceId, conversationId = null) {
  event.preventDefault();
  const form = event.target.tagName === 'FORM' ? event.target : event.target.closest('form');
  const submitBtn = form ? form.querySelector('button[type="submit"]') : null;
  const input = document.getElementById('chat-input');
  const fileInput = document.getElementById('chat-file-input');

  const msg = input ? input.value.trim() : '';
  const file = (fileInput && fileInput.files && fileInput.files[0]) ? fileInput.files[0] : null;

  if (!msg && !file) return;

  const origBtnText = submitBtn ? submitBtn.innerHTML : 'Send';
  if (submitBtn) {
    submitBtn.disabled = true; // Prevent double-clicking
    if (file) submitBtn.innerHTML = '<span class="spinner"></span> Uploading...';
  }

  const url = conversationId
    ? `/spaces/${spaceId}/private/${conversationId}/send`
    : `/spaces/${spaceId}/chat/send`;

  try {
    let res;
    if (file) {
      const formData = new FormData();
      if (msg) formData.append('message', msg);
      formData.append('file', file);
      res = await fetch(url, {
        method: 'POST',
        body: formData,
      });
    } else {
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });
    }

    const data = await res.json();
    if (data.error) {
      showToast(data.error, 'danger');
    } else if (data.message_obj) {
      appendChatMessage(data.message_obj);
      scrollChatToBottom();
      if (input) input.value = '';
      clearChatFile();
    }
  } catch (e) {
    showToast('Could not send message.', 'danger');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = origBtnText;
    }
    if (input) input.focus();
  }
}
window.sendChatMessage = sendChatMessage;

function handleChatFileSelect(fileInput) {
  const preview = document.getElementById('chat-file-preview');
  const nameEl = document.getElementById('chat-file-name');
  if (fileInput.files && fileInput.files[0]) {
    if (nameEl) nameEl.textContent = '📎 ' + fileInput.files[0].name;
    if (preview) preview.classList.remove('hidden');
  } else {
    clearChatFile();
  }
}
window.handleChatFileSelect = handleChatFileSelect;

function clearChatFile() {
  const fileInput = document.getElementById('chat-file-input');
  if (fileInput) fileInput.value = '';
  const preview = document.getElementById('chat-file-preview');
  if (preview) preview.classList.add('hidden');
}
window.clearChatFile = clearChatFile;

async function pinToNotes(messageId, btn) {
  if (btn) btn.disabled = true;
  try {
    const res = await fetch(`/messages/${messageId}/pin-to-notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || 'Pinned and saved to Notes!', 'success');
      const badge = document.getElementById(`pin-badge-${messageId}`);
      if (badge) badge.classList.remove('hidden');
    } else {
      showToast(data.error || 'Failed to pin to Notes', 'danger');
      if (btn) btn.disabled = false;
    }
  } catch (e) {
    showToast('Network error: ' + e.message, 'danger');
    if (btn) btn.disabled = false;
  }
}
window.pinToNotes = pinToNotes;




// ═══════════════════════════════════════
// MARK SETTLEMENT PAID
// ═══════════════════════════════════════

async function markSettlementPaid(settlementId, btn, spaceId) {
  btn.disabled = true;
  // Build correct URL: blueprint is mounted at /spaces/<space_id>/expenses/
  const url = spaceId
    ? `/spaces/${spaceId}/expenses/settlement/${settlementId}/pay`
    : `/spaces/0/expenses/settlement/${settlementId}/pay`; // fallback (shouldn't happen)
  try {
    const res  = await fetch(url, { method: 'POST' });
    const data = await res.json();
    if (data.error) { showFlash(data.error, 'danger'); btn.disabled = false; return; }
    showFlash('Settlement marked as paid!', 'success');
    btn.closest('.settlement-row')?.remove();
  } catch (e) {
    showFlash('Failed to mark paid.', 'danger');
    btn.disabled = false;
  }
}


// ═══════════════════════════════════════
// UTILITY
// ═══════════════════════════════════════

function escHtml(str) {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(str));
  return d.innerHTML;
}


// ═══════════════════════════════════════
// JOIN REQUESTS & SIDEBAR BADGES
// ═══════════════════════════════════════

function openJoinRequestsModal(spaceId) {
  const id = spaceId || document.querySelector('[data-space-id]')?.getAttribute('data-space-id');
  if (id) {
    openModal(`/spaces/${id}/members/requests`);
  }
}
window.openJoinRequestsModal = openJoinRequestsModal;

async function decideRequest(requestId, status, btnElement = null) {
  const btn = btnElement || (typeof event !== 'undefined' && event ? (event.target.tagName === 'BUTTON' ? event.target : event.target.closest('button')) : null);
  if (btn) btn.disabled = true; // Prevent double-clicking

  try {
    const response = await fetch(`/spaces/requests/${requestId}/decide`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ status: status })
    });

    const data = await response.json();

    if (response.ok && data.success) {
      // Smoothly fade out and remove card element
      const card = document.getElementById(`request-${requestId}`) || (btn ? (btn.closest('.request-item') || btn.closest('.join-request-card') || btn.closest('.member-item')) : null);
      if (card) {
        card.style.transition = 'opacity 0.3s ease';
        card.style.opacity = '0';
        setTimeout(() => {
          card.remove();
          const list = document.getElementById('join-requests-list');
          if (list && list.querySelectorAll('.join-request-card, .member-item').length === 0) {
            list.innerHTML = '<p class="text-muted" style="text-align:center;padding:1rem;">No pending requests.</p>';
          }
        }, 300);
      } else {
        window.location.reload();
      }
      showToast(data.message || `Request ${status.toLowerCase()}.`, 'success');

      // Update sidebar badge counter immediately
      const spaceContainer = document.querySelector('[data-space-id]');
      if (spaceContainer) {
        const sId = spaceContainer.getAttribute('data-space-id');
        updateSidebarBadges(sId);
      }
    } else {
      alert(data.error || 'Failed to update request.');
      if (btn) btn.disabled = false;
    }
  } catch (error) {
    console.error('Error handling join request:', error);
    alert('An error occurred. Please try again.');
    if (btn) btn.disabled = false;
  }
}
window.decideRequest = decideRequest;

async function updateSidebarBadges(spaceId) {
  if (!spaceId) return;
  try {
    const response = await fetch(`/spaces/${spaceId}/badge-counts`);
    if (!response.ok) return;

    const data = await response.json();

    // Update Pending Join Requests Badge
    const reqBadge = document.getElementById('join-requests-badge');
    if (reqBadge) {
      if (data.pending_requests > 0) {
        reqBadge.innerText = data.pending_requests > 99 ? '99+' : data.pending_requests;
        reqBadge.style.display = 'inline-block';
      } else {
        reqBadge.style.display = 'none';
      }
    }
  } catch (err) {
    console.error('Error fetching sidebar badges:', err);
  }
}
window.updateSidebarBadges = updateSidebarBadges;

// Automatically trigger polling if inside a space page
document.addEventListener('DOMContentLoaded', () => {
  const spaceContainer = document.querySelector('[data-space-id]');
  if (spaceContainer) {
    const spaceId = spaceContainer.getAttribute('data-space-id');
    updateSidebarBadges(spaceId);
    setInterval(() => updateSidebarBadges(spaceId), 8000); // Poll every 8s – Aiven supports high concurrency
  }
});
