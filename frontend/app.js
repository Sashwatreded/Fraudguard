const API_BASE = 'http://localhost:8001';

// ── Tab Counts (for overview tier bars) ──────────────────────────────────────
const _tierCounts = { SAFE: 0, SUSPICIOUS: 0, HIGH_RISK: 0, CRITICAL: 0 };
let _totalAlerts = 0;

// ── DOM: Stats ────────────────────────────────────────────────────────────────
const statTotal      = document.getElementById('stat-total');
const statFraudCount = document.getElementById('stat-fraud-count');
const statFraudRate  = document.getElementById('stat-fraud-rate');
const statAlerts     = document.getElementById('stat-alerts');

// ── Tab Navigation ────────────────────────────────────────────────────────────
const TAB_META = {
    'overview':    { title: 'Real-Time Fraud Detection',    sub: 'Monitoring active transactions and predicting anomalies' },
    'ai-analysis': { title: 'AI-Powered Transaction Analysis', sub: 'Claude Sonnet 4 behavioral anomaly detection & bank alert system' },
    'live-testing':{ title: 'Live Testing',                  sub: 'Test individual transactions or upload a CSV batch' },
    'feed':        { title: 'Transaction Feed',              sub: 'Live stream of all evaluated transactions' },
};

document.querySelectorAll('.nav-links a[data-tab]').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        const tab = link.dataset.tab;
        activateTab(tab);
    });
});

function activateTab(tabId) {
    // Update nav active state
    document.querySelectorAll('.nav-links li').forEach(li => li.classList.remove('active'));
    const activeLink = document.querySelector(`.nav-links a[data-tab="${tabId}"]`);
    if (activeLink) activeLink.parentElement.classList.add('active');

    // Show/hide panes
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.add('hidden'));
    const pane = document.getElementById(`tab-${tabId}`);
    if (pane) pane.classList.remove('hidden');

    // Update header
    const meta = TAB_META[tabId] || {};
    document.getElementById('page-title').textContent   = meta.title  || '';
    document.getElementById('page-subtitle').textContent = meta.sub   || '';
}

// ── Risk Tier Helpers ─────────────────────────────────────────────────────────
const TIER_META = {
    SAFE:       { color: '#22c55e', icon: '✅', label: 'SAFE' },
    SUSPICIOUS: { color: '#eab308', icon: '⚠️',  label: 'SUSPICIOUS' },
    HIGH_RISK:  { color: '#f97316', icon: '🔶', label: 'HIGH RISK' },
    CRITICAL:   { color: '#ef4444', icon: '🚨', label: 'CRITICAL' },
};

function tierBadgeHTML(tier) {
    const m = TIER_META[tier] || { color: '#888', icon: '❓', label: tier };
    return `<span class="tier-badge" style="background:${m.color}22;color:${m.color};border:1px solid ${m.color}55">${m.icon} ${m.label}</span>`;
}

function recBadgeHTML(rec) {
    const recColors = {
        APPROVE: '#22c55e', MONITOR: '#eab308', HOLD: '#f97316', BLOCK: '#ef4444'
    };
    const col = recColors[rec] || '#888';
    return `<span class="rec-badge" style="background:${col}22;color:${col};border:1px solid ${col}55">${rec}</span>`;
}

// ── Dashboard Stats & Transactions Polling ────────────────────────────────────
async function fetchData() {
    try {
        await Promise.all([fetchStats(), fetchTransactions()]);
    } catch (e) {
        console.error('Failed to fetch dashboard data:', e);
    }
}

async function fetchStats() {
    try {
        const res  = await fetch(`${API_BASE}/stats`);
        const data = await res.json();
        statTotal.textContent      = data.total_transactions.toLocaleString();
        statFraudCount.textContent = data.fraud_count.toLocaleString();
        statFraudRate.textContent  = data.fraud_percentage.toFixed(2) + '%';
    } catch (_) {}
}

async function fetchTransactions() {
    try {
        const res  = await fetch(`${API_BASE}/transactions?limit=15`);
        const data = await res.json();

        const rows = data.transactions.map(tx => buildTxRow(tx));
        const tbody = document.getElementById('transaction-tbody');
        const feedTbody = document.getElementById('feed-tbody');
        if (tbody)     tbody.innerHTML     = rows.join('');
        if (feedTbody) feedTbody.innerHTML = rows.join('');
    } catch (_) {}
}

function buildTxRow(tx) {
    const isFraud    = tx.is_fraud;
    const confidence = (tx.confidence * 100).toFixed(1);
    const time       = new Date(tx.timestamp).toLocaleTimeString();
    const shortId    = tx.transaction_id.substring(0, 8) + '…';
    const amountStr  = tx.transaction_data?.amount != null
        ? `$${tx.transaction_data.amount.toFixed(2)}`
        : 'N/A';
    return `<tr>
        <td><span title="${tx.transaction_id}">${shortId}</span></td>
        <td><strong>${amountStr}</strong></td>
        <td>${time}</td>
        <td><span class="badge ${isFraud ? 'badge-fraud' : 'badge-safe'}">${isFraud ? 'FRAUD' : 'SAFE'}</span></td>
        <td>${confidence}%</td>
    </tr>`;
}

// ── Live Alerts Feed ──────────────────────────────────────────────────────────
async function fetchAlerts() {
    try {
        const res  = await fetch(`${API_BASE}/api/alerts?limit=20`);
        const data = await res.json();

        _totalAlerts = data.total || 0;
        if (statAlerts) statAlerts.textContent = _totalAlerts.toLocaleString();

        const feed  = document.getElementById('alerts-feed');
        const empty = document.getElementById('alerts-empty');
        if (!feed) return;

        const alerts = data.alerts || [];
        if (alerts.length === 0) {
            if (empty) empty.classList.remove('hidden');
            return;
        }
        if (empty) empty.classList.add('hidden');

        // Rebuild feed (keep existing if same count to avoid flicker)
        feed.innerHTML = alerts.map(a => buildAlertCard(a)).join('');
    } catch (_) {}
}

function buildAlertCard(alert) {
    const tier      = alert.risk_tier?.tier || 'UNKNOWN';
    const m         = TIER_META[tier] || { color: '#888', icon: '❓' };
    const time      = new Date(alert.timestamp).toLocaleTimeString();
    const amount    = alert.transaction?.amount ?? 0;
    const score     = alert.transaction?.risk_score ?? 0;
    const flags     = alert.ai_analysis?.red_flags || [];
    const flagsHTML = flags.slice(0, 3).map(f => `<li>${f}</li>`).join('');
    const action    = alert.recommended_action || alert.risk_tier?.action || '—';
    const alertId   = (alert.alert_id || '').substring(0, 13);
    const rec       = alert.ai_analysis?.recommendation || '—';

    return `
    <div class="alert-card" style="border-left: 3px solid ${m.color}">
        <div class="alert-card-header">
            <span class="alert-icon">${m.icon}</span>
            <div class="alert-card-title">
                ${tierBadgeHTML(tier)}
                <span class="alert-time">${time}</span>
            </div>
            <span class="alert-id">ID: ${alertId}</span>
        </div>
        <div class="alert-card-body">
            <div class="alert-stat"><span>Amount</span><strong>₹${Number(amount).toLocaleString()}</strong></div>
            <div class="alert-stat"><span>Risk Score</span><strong>${Number(score).toFixed(4)}</strong></div>
            <div class="alert-stat"><span>Action</span><strong>${action}</strong></div>
            <div class="alert-stat"><span>AI Rec.</span>${recBadgeHTML(rec)}</div>
        </div>
        ${flags.length ? `<ul class="alert-flags">${flagsHTML}</ul>` : ''}
    </div>`;
}

// ── AI Analysis Form ─────────────────────────────────────────────────────────
const aiForm      = document.getElementById('ai-analyze-form');
const aiSubmitBtn = document.getElementById('ai-submit-btn');
const aiResultContent    = document.getElementById('ai-result-content');
const aiResultPlaceholder = document.getElementById('ai-result-placeholder');

// Sync risk slider ↔ number input
const riskSlider = document.getElementById('ai-risk-slider');
const riskInput  = document.getElementById('ai-risk');
if (riskSlider && riskInput) {
    riskSlider.addEventListener('input', () => { riskInput.value = riskSlider.value; });
    riskInput.addEventListener('input', () => {
        const v = parseFloat(riskInput.value);
        if (!isNaN(v)) riskSlider.value = Math.min(1, Math.max(0, v));
    });
}

if (aiForm) {
    aiForm.addEventListener('submit', async e => {
        e.preventDefault();

        aiSubmitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analyzing…';
        aiSubmitBtn.disabled  = true;
        aiResultPlaceholder.classList.add('hidden');
        aiResultContent.classList.add('hidden');
        aiResultContent.innerHTML = '';

        const payload = {
            amount:          parseFloat(document.getElementById('ai-amount').value),
            hour:            parseInt(document.getElementById('ai-hour').value),
            day:             parseInt(document.getElementById('ai-day').value),
            txns_last_24h:   parseFloat(document.getElementById('ai-txns').value),
            amount_last_24h: parseFloat(document.getElementById('ai-amount24h').value),
            risk_score:      parseFloat(document.getElementById('ai-risk').value),
        };

        try {
            const res    = await fetch(`${API_BASE}/api/analyze-transaction`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify(payload),
            });
            const result = await res.json();
            renderAIResult(result, payload);
            // Refresh alerts panel
            await fetchAlerts();
        } catch (err) {
            aiResultContent.classList.remove('hidden');
            aiResultContent.innerHTML = `<div class="ai-error">
                <i class="fa-solid fa-circle-exclamation"></i>
                <p>API error — is the server running?<br><code>${err.message}</code></p>
            </div>`;
        } finally {
            aiSubmitBtn.innerHTML = '<i class="fa-solid fa-brain"></i> Analyze with AI';
            aiSubmitBtn.disabled  = false;
        }
    });
}

function renderAIResult(result, txn) {
    const tier    = result.tier || {};
    const ai      = result.ai_analysis || null;
    const alert   = result.alert_triggered;
    const tierName = tier.tier || 'UNKNOWN';
    const m        = TIER_META[tierName] || { color: '#888', icon: '❓' };

    // Confidence bar fill
    const score    = txn.risk_score || 0;
    const scoreBar = `<div class="score-bar-track">
        <div class="score-bar-fill" style="width:${(score*100).toFixed(1)}%;background:${m.color}"></div>
    </div>`;

    let aiSection = '';
    if (ai) {
        const flags = (ai.red_flags || []).map(f => `<li><i class="fa-solid fa-flag" style="color:${m.color}"></i> ${f}</li>`).join('');
        const src   = ai.source === 'claude_ai'
            ? `<span class="ai-source-badge"><i class="fa-solid fa-brain"></i> Claude AI</span>`
            : `<span class="ai-source-badge rule-badge"><i class="fa-solid fa-gear"></i> Rule-Based</span>`;

        aiSection = `
        <div class="ai-section">
            <div class="ai-section-header">
                <span>AI Analysis</span>${src}
            </div>
            <ul class="ai-flags-list">${flags}</ul>
            <p class="ai-explanation">${ai.explanation || ''}</p>
            <div class="ai-footer">
                <div class="ai-stat"><span>Confidence</span><strong>${ai.confidence || '—'}</strong></div>
                <div class="ai-stat"><span>Recommendation</span>${recBadgeHTML(ai.recommendation || '—')}</div>
            </div>
        </div>`;
    } else {
        aiSection = `<div class="ai-section"><p class="ai-dim">Risk score ≤ 0.45 — AI analysis skipped (SAFE range)</p></div>`;
    }

    const alertBadge = alert
        ? `<div class="alert-triggered-badge"><i class="fa-solid fa-bell"></i> Bank Alert Triggered & Logged</div>`
        : '';

    aiResultContent.innerHTML = `
    <div class="ai-result-inner">
        <div class="ai-result-top">
            <div class="ai-tier-display" style="border-color:${m.color}33;background:${m.color}11">
                <span class="ai-tier-icon">${m.icon}</span>
                <div>
                    <div class="ai-tier-name" style="color:${m.color}">${tierName.replace('_', ' ')}</div>
                    <div class="ai-tier-action">${tier.action || ''}</div>
                </div>
            </div>
            <div class="score-display">
                <span class="score-label">Risk Score</span>
                <span class="score-value" style="color:${m.color}">${score.toFixed(4)}</span>
                ${scoreBar}
            </div>
        </div>
        ${aiSection}
        ${alertBadge}
    </div>`;

    aiResultContent.classList.remove('hidden');
    aiResultPlaceholder.classList.add('hidden');
}

// ── Existing Single Prediction ────────────────────────────────────────────────
const formSingle = document.getElementById('single-predict-form');
const resultSingle = document.getElementById('single-result');

if (formSingle) {
    formSingle.addEventListener('submit', async e => {
        e.preventDefault();
        const btn = formSingle.querySelector('button');
        btn.textContent = 'Evaluating…';
        btn.disabled = true;

        const payload = {
            amount:          parseFloat(document.getElementById('amount').value),
            hour:            parseInt(document.getElementById('hour').value),
            dayofweek:       parseInt(document.getElementById('dayofweek').value),
            txns_last_24h:   parseFloat(document.getElementById('txns_last_24h').value),
            amount_last_24h: parseFloat(document.getElementById('amount_last_24h').value),
            risk_score:      parseFloat(document.getElementById('risk_score').value),
        };

        try {
            const res = await fetch(`${API_BASE}/predict`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const result = await res.json();
            resultSingle.classList.remove('hidden', 'result-fraud', 'result-safe');
            if (result.is_fraud) {
                resultSingle.classList.add('result-fraud');
                resultSingle.innerHTML = `🚨 Fraudulent Activity Detected (Confidence: ${(result.confidence*100).toFixed(1)}%)`;
            } else {
                resultSingle.classList.add('result-safe');
                resultSingle.innerHTML = `✅ Transaction is Safe (Confidence: ${(result.confidence*100).toFixed(1)}%)`;
            }
            fetchData();
        } catch (e) {
            resultSingle.classList.remove('hidden', 'result-safe');
            resultSingle.classList.add('result-fraud');
            resultSingle.textContent = 'API Error. Check console.';
        } finally {
            btn.textContent = 'Evaluate Risk';
            btn.disabled = false;
        }
    });
}

// ── CSV Batch ─────────────────────────────────────────────────────────────────
const formBatch  = document.getElementById('csv-predict-form');
const fileInput  = document.getElementById('csvFile');
const resultBatch = document.getElementById('batch-result');

if (formBatch) {
    formBatch.addEventListener('submit', async e => {
        e.preventDefault();
        if (!fileInput || fileInput.files.length === 0) return;
        const btn = formBatch.querySelector('button');
        btn.textContent = 'Uploading…';
        btn.disabled = true;
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        try {
            const res    = await fetch(`${API_BASE}/predict/csv`, { method: 'POST', body: formData });
            const result = await res.json();
            resultBatch.classList.remove('hidden', 'result-fraud');
            resultBatch.classList.add('result-safe');
            resultBatch.innerHTML = `✅ Processed ${result.summary.total_transactions} transactions. Detected ${result.summary.fraud_count} cases of fraud.`;
            fetchData();
        } catch (e) {
            resultBatch.classList.remove('hidden', 'result-safe');
            resultBatch.classList.add('result-fraud');
            resultBatch.textContent = 'Upload Error. Check console.';
        } finally {
            btn.textContent = 'Upload & Analyze Batch';
            btn.disabled = false;
            if (fileInput) fileInput.value = '';
        }
    });
}

// ── Init & Polling ─────────────────────────────────────────────────────────────
fetchData();
fetchAlerts();
setInterval(fetchData,  5000);
setInterval(fetchAlerts, 5000);
