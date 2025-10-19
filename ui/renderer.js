const BACKEND_URL =
  (window.edgepilot && window.edgepilot.backendUrl) || 'http://127.0.0.1:8000';

const MODE_CONFIG = {
  ask: {
    label: 'Ask a question',
    placeholder: 'Ask about capacity, bottlenecks, or scheduling...'
  },
  schedule: {
    label: 'Schedule a task',
    placeholder: 'Describe the task you want to schedule...'
  },
  shutdown: {
    label: 'Shut down a run',
    placeholder: 'Which run should we shut down? Provide details...'
  }
};

const state = {
  providers: {},
  providerId: null,
  chats: [],
  activeChat: null,
  composerMode: 'ask',
  metricsMode: 'live',
  metricsTimer: null
};

const providerSelectEl = document.getElementById('provider-select');
const providerStatusEl = document.getElementById('provider-status');
const chatListEl = document.getElementById('chat-items');
const newChatBtn = document.getElementById('new-chat-btn');
const chatTitleEl = document.getElementById('active-chat-title');
const tokenCounterEl = document.getElementById('token-counter');
const messagesEl = document.getElementById('messages');
const metricGridEl = document.getElementById('metric-grid');
const metricsTabs = Array.from(document.querySelectorAll('.metrics-tab'));
const modeButton = document.getElementById('mode-button');
const modeLabel = document.getElementById('mode-label');
const modeMenu = document.getElementById('mode-menu');
const promptInputEl = document.getElementById('prompt-input');
const chatForm = document.getElementById('chat-form');
const statusBarEl = document.getElementById('status-bar');

const setStatus = (message, isError = false) => {
  statusBarEl.textContent = message || '';
  statusBarEl.classList.toggle('error', isError);
};

const fetchJSON = async (path, options = {}) => {
  const response = await fetch(`${BACKEND_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      if (payload && payload.detail) {
        detail = Array.isArray(payload.detail)
          ? payload.detail.map((item) => item.msg || item.detail || '').join('; ')
          : payload.detail;
      }
    } catch (error) {
      /* ignore */
    }
    throw new Error(detail || 'Request failed');
  }
  return response.json();
};

const updatePromptPlaceholder = () => {
  const providerName = state.providers[state.providerId]?.name || 'EdgePilot';
  const config = MODE_CONFIG[state.composerMode] || MODE_CONFIG.ask;
  promptInputEl.placeholder =
    state.composerMode === 'ask' ? `Ask ${providerName}` : config.placeholder;
  modeLabel.textContent = config.label;
};

const renderProviders = () => {
  providerSelectEl.innerHTML = '';
  const entries = Object.entries(state.providers);
  entries.forEach(([id, meta]) => {
    const option = document.createElement('option');
    option.value = id;
    option.textContent = meta.name;
    option.disabled = !meta.configured;
    providerSelectEl.appendChild(option);
  });

  const configured = entries.filter(([, meta]) => meta.configured);
  if (!configured.length) {
    providerSelectEl.value = '';
    providerSelectEl.disabled = true;
    providerSelectEl.classList.add('locked');
    providerStatusEl.textContent = 'Set API keys in env/.env to enable providers.';
  } else {
    if (!state.providerId || !state.providers[state.providerId]?.configured) {
      state.providerId = configured[0][0];
    }
    providerSelectEl.disabled = configured.length === 0;
    providerSelectEl.classList.toggle('locked', configured.length === 0);
    providerSelectEl.value = state.providerId;
    providerStatusEl.textContent = state.providers[state.providerId]?.note || '';
  }
  updatePromptPlaceholder();
};

const renderChats = () => {
  chatListEl.innerHTML = '';
  if (!state.chats.length) {
    const empty = document.createElement('li');
    empty.textContent = 'No chats yet';
    empty.classList.add('empty');
    chatListEl.appendChild(empty);
    return;
  }

  state.chats.forEach((chat) => {
    const item = document.createElement('li');
    item.textContent = chat.title || 'Quick chat';
    item.dataset.chatId = chat.id;
    if (state.activeChat && chat.id === state.activeChat.id) {
      item.classList.add('active');
    }
    item.addEventListener('click', () => selectChat(chat.id));
    chatListEl.appendChild(item);
  });
};

const formatTimestampTitle = () => {
  const now = new Date();
  return `Chat ${now.toLocaleTimeString()}`;
};

const renderMessages = () => {
  messagesEl.innerHTML = '';
  if (!state.activeChat || !state.activeChat.messages.length) {
    messagesEl.innerHTML = '<div class="empty-state">Create or select a chat to begin.</div>';
    tokenCounterEl.textContent = '';
    return;
  }

  state.activeChat.messages.forEach((msg) => {
    const bubble = document.createElement('div');
    bubble.classList.add('message', msg.role);
    bubble.innerHTML = (msg.content || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br />');
    messagesEl.appendChild(bubble);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;
  tokenCounterEl.textContent = `Tokens used: ${state.activeChat.tokens_used ?? 0}`;
};

const renderMetrics = (metrics) => {
  metricGridEl.innerHTML = '';
  if (state.metricsMode !== 'live') {
    metricGridEl.innerHTML = '<div class="metric-empty">Session metrics coming soon.</div>';
    return;
  }
  if (!metrics) {
    metricGridEl.innerHTML = '<div class="metric-empty">Metrics unavailable right now.</div>';
    return;
  }

  const cards = [
    { label: 'CPU %', value: metrics.cpu?.percent?.toFixed(1) ?? '0' },
    {
      label: 'Mem Used',
      value: metrics.memory?.used ? `${(metrics.memory.used / 1_073_741_824).toFixed(1)} GB` : '0 GB'
    },
    {
      label: 'Disk Read',
      value: metrics.disk?.read_bytes ? `${(metrics.disk.read_bytes / 1_000_000).toFixed(1)} MB` : '0 MB'
    },
    {
      label: 'Disk Write',
      value: metrics.disk?.write_bytes ? `${(metrics.disk.write_bytes / 1_000_000).toFixed(1)} MB` : '0 MB'
    },
    {
      label: 'Net Sent',
      value: metrics.network?.bytes_sent ? `${(metrics.network.bytes_sent / 1_000_000).toFixed(1)} MB` : '0 MB'
    },
    {
      label: 'Net Recv',
      value: metrics.network?.bytes_recv ? `${(metrics.network.bytes_recv / 1_000_000).toFixed(1)} MB` : '0 MB'
    }
  ];

  cards.forEach((cardData) => {
    const card = document.createElement('div');
    card.classList.add('metric-card');
    const label = document.createElement('span');
    label.textContent = cardData.label;
    const value = document.createElement('div');
    value.classList.add('metric-value');
    value.textContent = cardData.value;
    card.append(label, value);
    metricGridEl.appendChild(card);
  });
};

const setMetricsMode = (mode) => {
  state.metricsMode = mode;
  metricsTabs.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.mode === mode);
  });
  renderMetrics(state.metricsLastSnapshot);
};

const loadProviders = async () => {
  const data = await fetchJSON('/api/providers');
  state.providers = data;
  renderProviders();
};

const loadChats = async () => {
  const chats = await fetchJSON('/api/chats');
  state.chats = chats;
  renderChats();
  if (!state.activeChat && chats.length) {
    await selectChat(chats[0].id);
  }
};

const loadMetrics = async (quiet = false) => {
  if (state.metricsMode !== 'live') {
    renderMetrics(null);
    return;
  }
  try {
    const metrics = await fetchJSON('/api/metrics');
    state.metricsLastSnapshot = metrics;
    renderMetrics(metrics);
  } catch (error) {
    if (!quiet) {
      setStatus(`Metrics unavailable: ${error.message}`, true);
    }
  }
};

const createChat = async () => {
  const chat = await fetchJSON('/api/chats', {
    method: 'POST',
    body: JSON.stringify({})
  });
  await loadChats();
  await selectChat(chat.id);
};

const selectChat = async (chatId) => {
  const detail = await fetchJSON(`/api/chats/${chatId}`);
  state.activeChat = detail;
  chatTitleEl.textContent = detail.title || formatTimestampTitle();
  renderChats();
  renderMessages();
};

const formatPromptForMode = (prompt) => {
  const trimmed = prompt.trim();
  if (!trimmed) return trimmed;
  if (state.composerMode === 'ask') {
    return trimmed;
  }
  if (state.composerMode === 'schedule') {
    return `Schedule task request:\n${trimmed}`;
  }
  if (state.composerMode === 'shutdown') {
    return `Shut down run request:\n${trimmed}`;
  }
  return trimmed;
};

const sendMessage = async (prompt) => {
  if (!state.activeChat) {
    await createChat();
  }
  if (!state.providerId) {
    setStatus('Select a provider before sending.', true);
    return;
  }

  setStatus('Sending...');
  try {
    const response = await fetchJSON(`/api/chats/${state.activeChat.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        prompt: formatPromptForMode(prompt),
        provider: state.providerId
      })
    });
    state.activeChat = response.chat;
    const idx = state.chats.findIndex((chat) => chat.id === response.chat.id);
    if (idx !== -1) {
      state.chats[idx] = response.chat;
    }
    chatTitleEl.textContent = response.chat.title;
    renderChats();
    renderMessages();
    setStatus('Ready');
  } catch (error) {
    setStatus(`Send failed: ${error.message}`, true);
  }
};

// Event wiring
newChatBtn.addEventListener('click', () => {
  createChat().catch((error) => setStatus(`Unable to create chat: ${error.message}`, true));
});

chatForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const prompt = promptInputEl.value.trim();
  if (!prompt) return;
  promptInputEl.value = '';
  await sendMessage(prompt);
});

promptInputEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

providerSelectEl.addEventListener('change', (event) => {
  const selected = event.target.value;
  if (state.providers[selected]?.configured) {
    state.providerId = selected;
    providerStatusEl.textContent = state.providers[state.providerId]?.note || '';
  } else {
    setStatus('Configure API key for this provider before use.', true);
    event.target.value = state.providerId || '';
  }
  updatePromptPlaceholder();
});

metricsTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    metricsTabs.forEach((btn) => btn.classList.remove('active'));
    tab.classList.add('active');
    setMetricsMode(tab.dataset.mode);
  });
});

modeButton.addEventListener('click', () => {
  const expanded = modeButton.getAttribute('aria-expanded') === 'true';
  modeButton.setAttribute('aria-expanded', String(!expanded));
  modeMenu.classList.toggle('hidden', expanded);
});

modeMenu.addEventListener('click', (event) => {
  const option = event.target.closest('.mode-option');
  if (!option) return;
  state.composerMode = option.dataset.mode;
  modeButton.setAttribute('aria-expanded', 'false');
  modeMenu.classList.add('hidden');
  updatePromptPlaceholder();
});

document.addEventListener('click', (event) => {
  if (!modeMenu.contains(event.target) && event.target !== modeButton) {
    modeButton.setAttribute('aria-expanded', 'false');
    modeMenu.classList.add('hidden');
  }
});

const init = async () => {
  setStatus('Loading…');
  try {
    await loadProviders();
    await Promise.all([loadChats(), loadMetrics()]);
    setStatus('Ready');
    if (state.metricsTimer) {
      clearInterval(state.metricsTimer);
    }
    state.metricsTimer = setInterval(() => {
      loadMetrics(true).catch(() => {});
    }, 1000);
  } catch (error) {
    setStatus(`Init failed: ${error.message}`, true);
  }
};

window.addEventListener('DOMContentLoaded', () => {
  init();
});
