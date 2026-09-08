/**
 * Personal Finance Tracker Web Application Client Engine
 */

// Global State
const state = {
  currentMonth: new Date().toISOString().slice(0, 7),
  transactions: [],
  summary: null,
  budgets: [],
  alerts: [],
  categories: [],
  filters: {
    type: 'ALL',
    category: 'ALL',
    search: '',
  }
};

// API Helper
async function apiCall(endpoint, options = {}) {
  try {
    const response = await fetch(endpoint, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'An API error occurred.');
    }
    return data;
  } catch (err) {
    showToast(err.message, 'error');
    throw err;
  }
}

// Toast Notifications
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `alert-banner ${type === 'error' ? 'exceeded' : 'warning'}`;
  toast.style.position = 'fixed';
  toast.style.bottom = '24px';
  toast.style.right = '24px';
  toast.style.zIndex = '2000';
  toast.style.minWidth = '300px';
  toast.innerHTML = `
    <div class="alert-content">
      <span class="alert-icon">${type === 'error' ? '⚠️' : 'ℹ️'}</span>
      <span>${message}</span>
    </div>
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Initialize Application
document.addEventListener('DOMContentLoaded', () => {
  const monthInput = document.getElementById('selectedMonth');
  if (monthInput) {
    monthInput.value = state.currentMonth;
    monthInput.addEventListener('change', (e) => {
      state.currentMonth = e.target.value;
      refreshAll();
    });
  }

  // Setup Event Listeners
  setupEventListeners();
  
  // Initial Data Load
  refreshAll();
});

function setupEventListeners() {
  // Add Transaction Modal Toggle
  const addTxBtn = document.getElementById('openAddTxBtn');
  if (addTxBtn) addTxBtn.addEventListener('click', () => openModal('txModal'));

  const closeTxBtn = document.getElementById('closeTxBtn');
  if (closeTxBtn) closeTxBtn.addEventListener('click', () => closeModal('txModal'));

  // Add Budget Modal Toggle
  const openBudgetBtn = document.getElementById('openBudgetBtn');
  if (openBudgetBtn) openBudgetBtn.addEventListener('click', () => openModal('budgetModal'));

  const closeBudgetBtn = document.getElementById('closeBudgetBtn');
  if (closeBudgetBtn) closeBudgetBtn.addEventListener('click', () => closeModal('budgetModal'));

  // Export Modal Toggle
  const openExportBtn = document.getElementById('openExportBtn');
  if (openExportBtn) openExportBtn.addEventListener('click', handleOpenExport);

  const closeExportBtn = document.getElementById('closeExportBtn');
  if (closeExportBtn) closeExportBtn.addEventListener('click', () => closeModal('exportModal'));

  // Import Modal Toggle
  const openImportBtn = document.getElementById('openImportBtn');
  if (openImportBtn) openImportBtn.addEventListener('click', () => openModal('importModal'));

  const closeImportBtn = document.getElementById('closeImportBtn');
  if (closeImportBtn) closeImportBtn.addEventListener('click', () => closeModal('importModal'));

  const importForm = document.getElementById('importForm');
  if (importForm) importForm.addEventListener('submit', handleImportStatement);

  const loadSampleBtn = document.getElementById('loadSampleBtn');
  if (loadSampleBtn) loadSampleBtn.addEventListener('click', handleLoadSampleStatement);

  // Import Format Selector Tabs
  const importTabs = document.querySelectorAll('.import-tab');
  importTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      importTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const targetTab = tab.getAttribute('data-tab');
      const fileLabel = document.getElementById('importFileLabel');
      const fileInput = document.getElementById('importFile');

      if (!fileLabel || !fileInput) return;

      if (targetTab === 'csv') {
        fileLabel.textContent = 'Choose CSV File (.csv, .txt)';
        fileInput.accept = '.csv,.txt';
      } else if (targetTab === 'pdf') {
        fileLabel.textContent = 'Choose PDF Bank Statement (.pdf)';
        fileInput.accept = '.pdf';
      } else if (targetTab === 'image') {
        fileLabel.textContent = 'Choose Image / Screenshot (.png, .jpg, .jpeg, .webp)';
        fileInput.accept = 'image/*';
      } else if (targetTab === 'text') {
        fileLabel.textContent = 'Paste Raw Statement Text Below';
      }
    });
  });

  // Transaction Form Submit
  const txForm = document.getElementById('txForm');
  if (txForm) txForm.addEventListener('submit', handleAddTransaction);

  // Budget Form Submit
  const budgetForm = document.getElementById('budgetForm');
  if (budgetForm) budgetForm.addEventListener('submit', handleSetBudget);

  // Filters
  const filterType = document.getElementById('filterType');
  if (filterType) filterType.addEventListener('change', (e) => {
    state.filters.type = e.target.value;
    renderTransactionsTable();
  });

  const filterCat = document.getElementById('filterCategory');
  if (filterCat) filterCat.addEventListener('change', (e) => {
    state.filters.category = e.target.value;
    renderTransactionsTable();
  });

  const filterSearch = document.getElementById('filterSearch');
  if (filterSearch) filterSearch.addEventListener('input', (e) => {
    state.filters.search = e.target.value.toLowerCase();
    renderTransactionsTable();
  });

  // Type change in modal dynamically populates categories
  const txTypeSelect = document.getElementById('txType');
  if (txTypeSelect) {
    txTypeSelect.addEventListener('change', (e) => populateCategoryDropdowns(e.target.value));
  }

  // Delete Button Event Delegation
  document.addEventListener('click', async (e) => {
    const target = e.target.closest('.btn-delete-tx');
    if (target) {
      const id = target.getAttribute('data-id');
      if (id) {
        target.disabled = true;
        target.textContent = 'Deleting...';
        try {
          await apiCall(`/api/transactions/${id}`, { method: 'DELETE' });
          showToast('Transaction deleted successfully!');
          await refreshAll();
        } catch (err) {
          showToast(err.message, 'error');
          target.disabled = false;
          target.textContent = 'Delete';
        }
      }
    }
  });
}

// Modal Helpers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('active');
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove('active');
}

// Data Refresh Controller
async function refreshAll() {
  await Promise.all([
    loadSummary(),
    loadTransactions(),
    loadBudgets(),
    loadCategories(),
  ]);
}

// API Loaders
async function loadSummary() {
  const data = await apiCall(`/api/summary?month=${state.currentMonth}`);
  state.summary = data;
  renderMetrics();
  renderCategoryBreakdown();
}

async function loadTransactions() {
  const data = await apiCall(`/api/transactions?month=${state.currentMonth}`);
  state.transactions = data;
  renderTransactionsTable();
}

async function loadBudgets() {
  const data = await apiCall(`/api/budgets?month=${state.currentMonth}`);
  state.budgets = data.budgets || [];
  state.alerts = data.alerts || [];
  renderAlerts();
  renderBudgetsList();
}

async function loadCategories() {
  const data = await apiCall('/api/categories');
  state.categories = data;
  populateCategoryDropdowns();
}

// Render Executive Metric Cards
function renderMetrics() {
  if (!state.summary) return;
  
  const incomeEl = document.getElementById('metricIncome');
  const expenseEl = document.getElementById('metricExpense');
  const netEl = document.getElementById('metricNet');

  if (incomeEl) incomeEl.textContent = `$${state.summary.total_income}`;
  if (expenseEl) expenseEl.textContent = `$${state.summary.total_expense}`;
  if (netEl) {
    netEl.textContent = `$${state.summary.net_cash_flow}`;
    if (parseFloat(state.summary.net_cash_flow) >= 0) {
      netEl.style.color = 'var(--income-light)';
    } else {
      netEl.style.color = 'var(--expense-light)';
    }
  }
}

// Render Alerts Banner
function renderAlerts() {
  const container = document.getElementById('alertsBanner');
  if (!container) return;

  if (!state.alerts || state.alerts.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = state.alerts.map(a => `
    <div class="alert-banner ${a.is_exceeded ? 'exceeded' : 'warning'}">
      <div class="alert-content">
        <span class="alert-icon">${a.is_exceeded ? '🔴' : '⚠️'}</span>
        <span>
          <strong>${a.is_exceeded ? 'BUDGET EXCEEDED' : 'BUDGET WARNING'}:</strong> 
          Category <u>${a.category}</u> spent $${a.current_spent} of $${a.limit_amount} cap.
          ${a.is_exceeded ? `(Over by $${a.exceeded_by})` : '(>= 90% Limit Reached)'}
        </span>
      </div>
    </div>
  `).join('');
}

// Render Category Spending Progress Bars & Donut Chart
function renderCategoryBreakdown() {
  const container = document.getElementById('categoryBreakdown');
  if (!container || !state.summary) return;

  const breakdown = state.summary.category_breakdown;
  if (!breakdown || breakdown.length === 0) {
    container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No expense transactions recorded for this month.</p>';
    renderDonutChart([]);
    return;
  }

  container.innerHTML = breakdown.map(cat => `
    <div class="progress-item">
      <div class="progress-header">
        <span>${cat.category}</span>
        <span>$${cat.total_amount} (${cat.percentage}%)</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill expense" style="width: ${cat.percentage}%"></div>
      </div>
    </div>
  `).join('');

  renderDonutChart(breakdown);
}

// Render SVG Donut Chart
function renderDonutChart(breakdown) {
  const svg = document.getElementById('donutChart');
  if (!svg) return;

  if (!breakdown || breakdown.length === 0) {
    svg.innerHTML = '<circle cx="100" cy="100" r="70" fill="none" stroke="rgba(255,255,255,0.05)" stroke-width="20"/>';
    return;
  }

  const colors = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#3b82f6', '#14b8a6'];
  let strokeDashoffset = 0;
  const radius = 70;
  const circumference = 2 * Math.PI * radius;

  let circles = '';
  breakdown.forEach((item, idx) => {
    const pct = parseFloat(item.percentage) / 100;
    const strokeDasharray = `${pct * circumference} ${circumference}`;
    const color = colors[idx % colors.length];

    circles += `
      <circle 
        cx="100" cy="100" r="${radius}" 
        fill="none" 
        stroke="${color}" 
        stroke-width="20" 
        stroke-dasharray="${strokeDasharray}" 
        stroke-dashoffset="-${strokeDashoffset}"
        style="transition: all 0.6s ease;"
      />
    `;
    strokeDashoffset += pct * circumference;
  });

  svg.innerHTML = circles;
}

// Render Transactions Table
function renderTransactionsTable() {
  const tbody = document.getElementById('txTableBody');
  if (!tbody) return;

  let filtered = [...state.transactions];

  if (state.filters.type !== 'ALL') {
    filtered = filtered.filter(t => t.type === state.filters.type);
  }

  if (state.filters.category !== 'ALL') {
    filtered = filtered.filter(t => t.category.toLowerCase() === state.filters.category.toLowerCase());
  }

  if (state.filters.search) {
    filtered = filtered.filter(t => 
      t.description.toLowerCase().includes(state.filters.search) ||
      t.category.toLowerCase().includes(state.filters.search)
    );
  }

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">
          No transactions found for the selected filters.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = filtered.map(t => `
    <tr>
      <td><code>${t.transaction_id.slice(0, 8)}...</code></td>
      <td>${new Date(t.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
      <td><span class="type-badge ${t.type.toLowerCase()}">${t.type}</span></td>
      <td><strong>${t.category}</strong></td>
      <td class="amount-text ${t.type.toLowerCase()}">${t.type === 'INCOME' ? '+' : '-'}$${t.amount}</td>
      <td>${t.payment_method}</td>
      <td>${t.description || '-'}</td>
      <td>
        <button class="btn btn-danger btn-delete-tx" data-id="${t.transaction_id}">Delete</button>
      </td>
    </tr>
  `).join('');
}

// Render Budgets Progress List
function renderBudgetsList() {
  const container = document.getElementById('budgetsList');
  if (!container) return;

  if (!state.budgets || state.budgets.length === 0) {
    container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">No budget limits configured for this month.</p>';
    return;
  }

  container.innerHTML = state.budgets.map(b => {
    const pct = Math.min(parseFloat(b.percentage), 100);
    const fillClass = b.status === 'EXCEEDED' ? 'exceeded' : (b.status === 'WARNING' ? 'warning' : 'expense');
    return `
      <div class="progress-item">
        <div class="progress-header">
          <span><strong>${b.category}</strong></span>
          <span>$${b.current_spent} / $${b.limit_amount} (${b.percentage}%)</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${fillClass}" style="width: ${pct}%"></div>
        </div>
      </div>
    `;
  }).join('');
}

// Populate Category Dropdowns
function populateCategoryDropdowns(selectedType = 'EXPENSE') {
  const selects = [
    document.getElementById('txCategory'),
    document.getElementById('budgetCategory'),
    document.getElementById('filterCategory')
  ];

  selects.forEach(select => {
    if (!select) return;
    const isFilter = select.id === 'filterCategory';
    const currentVal = select.value;
    
    let html = isFilter ? '<option value="ALL">All Categories</option>' : '';
    state.categories.forEach(cat => {
      html += `<option value="${cat}">${cat}</option>`;
    });
    select.innerHTML = html;
    if (currentVal) select.value = currentVal;
  });
}

// Handlers
async function handleAddTransaction(e) {
  e.preventDefault();
  const rawDate = document.getElementById('txDate').value;
  const timestamp = rawDate ? new Date(rawDate).toISOString() : new Date().toISOString();

  const payload = {
    type: document.getElementById('txType').value,
    category: document.getElementById('txCategory').value,
    amount: document.getElementById('txAmount').value,
    payment_method: document.getElementById('txPaymentMethod').value,
    description: document.getElementById('txDescription').value,
    timestamp: timestamp,
  };

  try {
    const res = await apiCall('/api/transactions', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    showToast('Transaction recorded successfully!');
    closeModal('txModal');
    document.getElementById('txForm').reset();
    refreshAll();
  } catch (err) {
    // Handled by apiCall
  }
}

async function handleSetBudget(e) {
  e.preventDefault();
  const payload = {
    category: document.getElementById('budgetCategory').value,
    month: state.currentMonth,
    limit_amount: document.getElementById('budgetAmount').value,
  };

  try {
    await apiCall('/api/budgets', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    showToast('Budget cap set successfully!');
    closeModal('budgetModal');
    document.getElementById('budgetForm').reset();
    refreshAll();
  } catch (err) {
    // Handled by apiCall
  }
}

async function handleDeleteTx(id) {
  if (!confirm('Are you sure you want to delete this transaction?')) return;
  try {
    await apiCall(`/api/transactions/${id}`, { method: 'DELETE' });
    showToast('Transaction deleted.');
    refreshAll();
  } catch (err) {
    // Handled
  }
}
window.handleDeleteTx = handleDeleteTx;

async function handleOpenExport() {
  try {
    const data = await apiCall(`/api/export?month=${state.currentMonth}&format=markdown`);
    const preview = document.getElementById('exportPreview');
    if (preview) preview.textContent = data.content;
    openModal('exportModal');
  } catch (err) {
    // Handled
  }
}

async function handleImportStatement(e) {
  e.preventDefault();
  const fileInput = document.getElementById('importFile');
  const textInput = document.getElementById('importText');
  let content = textInput ? textInput.value.trim() : '';

  if (fileInput && fileInput.files.length > 0) {
    const file = fileInput.files[0];
    if (file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf') {
      content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    } else {
      content = await file.text();
    }
  }

  if (!content) {
    showToast('Please select a statement document file or paste text.', 'error');
    return;
  }

  try {
    const res = await apiCall('/api/import-statement', {
      method: 'POST',
      body: JSON.stringify({ content }),
    });

    showToast(`Successfully imported ${res.imported_count} transaction(s)! (Skipped ${res.skipped_duplicates} duplicates)`);
    closeModal('importModal');
    document.getElementById('importForm').reset();
    refreshAll();
  } catch (err) {
    // Handled by apiCall
  }
}

function handleLoadSampleStatement() {
  const textInput = document.getElementById('importText');
  if (textInput) {
    textInput.value = `Account transactions from 5 July 2026 to 8 September 2026
Date Description Money out Money in Balance
20-Jul-2026 Google Pay top-up by *4971 €1.00 €1.00
11-Aug-2026 To EUR Flexible Cash Funds €1.00 €0.00
11-Aug-2026 From EUR Flexible Cash Funds €1.00 €1.00
24-Aug-2026 Google Pay top-up by *4971 €150.00 €151.00
26-Aug-2026 Google Pay top-up by *4971 €300.00 €451.00
26-Aug-2026 To Rambabu Jampana €407.79 €43.21
26-Aug-2026 Transfer to LOKESH VARMA JAMPANA €40.00 €3.21
18-Jul-2026 Payment from SARITHA RAYEENI €1.00`;
  }
}
