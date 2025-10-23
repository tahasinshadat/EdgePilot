const BACKEND_URL =
  (window.edgepilot && window.edgepilot.backendUrl) || 'http://127.0.0.1:8000';

const state = {
  providers: {},
  providerId: null,
  chats: [],
  activeChat: null,
  metricsMode: 'live',
  metricsTimer: null,
  isThinking: false,
  currentMode: 'ask'
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
const promptInputEl = document.getElementById('prompt-input');
const chatForm = document.getElementById('chat-form');
const statusBarEl = document.getElementById('status-bar');
const modeButtonEl = document.getElementById('mode-button');
const modeLabelEl = document.getElementById('mode-label');
const modeMenuEl = document.getElementById('mode-menu');
const modeOptions = Array.from(document.querySelectorAll('.mode-option'));

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

const MODE_CONFIG = {
  ask: {
    label: 'Ask a question',
    placeholder: 'Ask me anything...',
    promptPrefix: null
  },
  schedule: {
    label: 'Schedule a task',
    placeholder: 'e.g., "Launch Minecraft in 30 seconds"',
    promptPrefix: 'I need to schedule a task: '
  },
  shutdown: {
    label: 'Shut down a run',
    placeholder: 'e.g., "Close all Chrome processes"',
    promptPrefix: 'I need to shut down: '
  }
};

const updatePromptPlaceholder = () => {
  const providerName = state.providers[state.providerId]?.name || 'EdgePilot';
  const modeConfig = MODE_CONFIG[state.currentMode];
  promptInputEl.placeholder = modeConfig.placeholder;
};

const setMode = (mode) => {
  state.currentMode = mode;
  const config = MODE_CONFIG[mode];

  // Update button label
  modeLabelEl.textContent = config.label;

  // Update placeholder
  updatePromptPlaceholder();

  // Update active state on menu options
  modeOptions.forEach(option => {
    option.classList.toggle('active', option.dataset.mode === mode);
  });

  // Close menu
  modeMenuEl.classList.add('hidden');
  modeButtonEl.setAttribute('aria-expanded', 'false');
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
    providerStatusEl.textContent = 'Set API keys in env/.env';
  } else {
    if (!state.providerId || !state.providers[state.providerId]?.configured) {
      state.providerId = configured[0][0];
    }
    providerSelectEl.disabled = false;
    providerSelectEl.value = state.providerId;
    providerStatusEl.textContent = state.providers[state.providerId]?.note || '';
  }
  updatePromptPlaceholder();
};

const deleteChat = async (chatId, event) => {
  event?.stopPropagation();
  if (!confirm('Delete this chat?')) return;

  try {
    await fetchJSON(`/api/chats/${chatId}`, { method: 'DELETE' });
    if (state.activeChat && state.activeChat.id === chatId) {
      state.activeChat = null;
      chatTitleEl.textContent = 'Select a chat';
      messagesEl.innerHTML = '<div class="empty-state">Create or select a chat to begin</div>';
      tokenCounterEl.textContent = '';
    }
    await loadChats();
    setStatus('Chat deleted');
  } catch (error) {
    setStatus(`Delete failed: ${error.message}`, true);
  }
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
    const titleSpan = document.createElement('span');
    titleSpan.textContent = chat.title || 'Conversation';
    titleSpan.className = 'chat-title-text';

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = '×';
    deleteBtn.className = 'delete-chat-btn';
    deleteBtn.setAttribute('title', 'Delete chat');
    deleteBtn.onclick = (e) => deleteChat(chat.id, e);

    item.dataset.chatId = chat.id;
    if (state.activeChat && chat.id === state.activeChat.id) {
      item.classList.add('active');
    }

    item.appendChild(titleSpan);
    item.appendChild(deleteBtn);
    item.addEventListener('click', () => selectChat(chat.id));
    chatListEl.appendChild(item);
  });
};

const createThinkingIndicator = () => {
  const indicator = document.createElement('div');
  indicator.className = 'thinking-indicator';
  indicator.id = 'thinking-indicator';
  for (let i = 0; i < 3; i++) {
    const dot = document.createElement('div');
    dot.className = 'thinking-dot';
    indicator.appendChild(dot);
  }
  return indicator;
};

const showThinking = () => {
  if (state.isThinking) return;
  state.isThinking = true;
  const indicator = createThinkingIndicator();
  messagesEl.appendChild(indicator);
  messagesEl.scrollTop = messagesEl.scrollHeight;
};

const hideThinking = () => {
  if (!state.isThinking) return;
  state.isThinking = false;
  const indicator = document.getElementById('thinking-indicator');
  if (indicator) {
    indicator.remove();
  }
};

const renderMessages = () => {
  messagesEl.innerHTML = '';
  if (!state.activeChat || !state.activeChat.messages.length) {
    messagesEl.innerHTML = '<div class="empty-state">Create or select a chat to begin</div>';
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

  // Update token counter with more details
  const tokens = state.activeChat.tokens_used ?? 0;
  const messages = state.activeChat.messages.length;
  tokenCounterEl.textContent = `${messages} messages • ${tokens.toLocaleString()} tokens`;
};

const calculateSessionMetrics = (chat) => {
  if (!chat || !chat.messages) return null;

  const totalMessages = chat.messages.length;
  const userMessages = chat.messages.filter(m => m.role === 'user').length;
  const assistantMessages = chat.messages.filter(m => m.role === 'assistant').length;
  const totalTokens = chat.tokens_used || 0;
  const toolCalls = chat.tool_calls_count || 0;

  // Estimate context usage (assuming ~4 chars per token, 8k context window)
  const estimatedChars = totalTokens * 4;
  const contextWindow = 8000 * 4; // 8k tokens * 4 chars
  const contextUsedPercent = Math.min(100, (estimatedChars / contextWindow) * 100);

  return {
    totalMessages,
    userMessages,
    assistantMessages,
    totalTokens,
    contextUsedPercent,
    toolCalls
  };
};

const renderMetrics = (metrics) => {
  metricGridEl.innerHTML = '';

  if (state.metricsMode === 'session') {
    if (!state.activeChat) {
      metricGridEl.innerHTML = '<div class="metric-empty">Select a chat to view session metrics</div>';
      return;
    }

    const sessionMetrics = calculateSessionMetrics(state.activeChat);
    if (!sessionMetrics) {
      metricGridEl.innerHTML = '<div class="metric-empty">No session data available</div>';
      return;
    }

    const cards = [
      { label: 'Messages', value: sessionMetrics.totalMessages },
      { label: 'Tokens Used', value: sessionMetrics.totalTokens.toLocaleString() },
      { label: 'Context', value: `${sessionMetrics.contextUsedPercent.toFixed(1)}%` },
      { label: 'Tool Calls', value: sessionMetrics.toolCalls },
      { label: 'User', value: sessionMetrics.userMessages },
      { label: 'Assistant', value: sessionMetrics.assistantMessages },
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

    return;
  }

  // Live metrics
  if (!metrics) {
    metricGridEl.innerHTML = '<div class="metric-empty">Metrics unavailable</div>';
    return;
  }

  const cards = [
    { label: 'CPU', value: `${metrics.cpu?.percent?.toFixed(1) ?? '0'}%` },
    { label: 'Memory', value: metrics.memory?.used ? `${(metrics.memory.used / 1_073_741_824).toFixed(1)} GB` : '0 GB' },
    { label: 'Disk R', value: metrics.disk?.read_bytes ? `${(metrics.disk.read_bytes / 1_000_000).toFixed(0)} MB` : '0 MB' },
    { label: 'Disk W', value: metrics.disk?.write_bytes ? `${(metrics.disk.write_bytes / 1_000_000).toFixed(0)} MB` : '0 MB' },
    { label: 'Net Sent', value: metrics.network?.bytes_sent ? `${(metrics.network.bytes_sent / 1_000_000).toFixed(0)} MB` : '0 MB' },
    { label: 'Net Recv', value: metrics.network?.bytes_recv ? `${(metrics.network.bytes_recv / 1_000_000).toFixed(0)} MB` : '0 MB' },
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
  if (mode === 'session') {
    renderMetrics(null); // Trigger session metrics render
  } else {
    renderMetrics(state.metricsLastSnapshot);
  }
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
  chatTitleEl.textContent = detail.title || 'Conversation';
  renderChats();
  renderMessages();

  // Update session metrics if in session mode
  if (state.metricsMode === 'session') {
    renderMetrics(null);
  }
};

const sendMessage = async (prompt) => {
  if (!state.activeChat) {
    await createChat();
  }
  if (!state.providerId) {
    setStatus('Select a provider before sending', true);
    return;
  }

  // Apply mode prefix if applicable
  const modeConfig = MODE_CONFIG[state.currentMode];
  let finalPrompt = prompt.trim();

  if (modeConfig.promptPrefix && !prompt.toLowerCase().startsWith(modeConfig.promptPrefix.toLowerCase())) {
    finalPrompt = modeConfig.promptPrefix + prompt.trim();
  }

  // Add user message immediately (show the original prompt, not the prefixed one)
  const userMessage = {
    role: 'user',
    content: prompt.trim(),
    created_at: Date.now() / 1000
  };

  if (!state.activeChat.messages) {
    state.activeChat.messages = [];
  }
  state.activeChat.messages.push(userMessage);
  renderMessages();

  // Show thinking indicator
  showThinking();
  setStatus('Sending...');

  try {
    const response = await fetchJSON(`/api/chats/${state.activeChat.id}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        prompt: finalPrompt,
        provider: state.providerId
      })
    });

    hideThinking();

    state.activeChat = response.chat;
    const idx = state.chats.findIndex((chat) => chat.id === response.chat.id);
    if (idx !== -1) {
      state.chats[idx] = response.chat;
    }
    chatTitleEl.textContent = response.chat.title;
    renderChats();
    renderMessages();

    // Update session metrics if visible
    if (state.metricsMode === 'session') {
      renderMetrics(null);
    }

    setStatus('Ready');
  } catch (error) {
    hideThinking();
    // Remove the user message we added optimistically
    state.activeChat.messages.pop();
    renderMessages();
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
  promptInputEl.style.height = 'auto'; // Reset height
  await sendMessage(prompt);
});

promptInputEl.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

// Auto-resize textarea
promptInputEl.addEventListener('input', () => {
  promptInputEl.style.height = 'auto';
  promptInputEl.style.height = promptInputEl.scrollHeight + 'px';
});

providerSelectEl.addEventListener('change', (event) => {
  const selected = event.target.value;
  if (state.providers[selected]?.configured) {
    state.providerId = selected;
    providerStatusEl.textContent = state.providers[state.providerId]?.note || '';
  } else {
    setStatus('Configure API key for this provider before use', true);
    event.target.value = state.providerId || '';
  }
  updatePromptPlaceholder();
});

metricsTabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    setMetricsMode(tab.dataset.mode);
  });
});

// Mode selection
modeButtonEl.addEventListener('click', () => {
  const isExpanded = modeButtonEl.getAttribute('aria-expanded') === 'true';
  modeButtonEl.setAttribute('aria-expanded', !isExpanded);
  modeMenuEl.classList.toggle('hidden');
});

modeOptions.forEach((option) => {
  option.addEventListener('click', () => {
    setMode(option.dataset.mode);
  });
});

// Close mode menu when clicking outside
document.addEventListener('click', (e) => {
  if (!modeButtonEl.contains(e.target) && !modeMenuEl.contains(e.target)) {
    modeMenuEl.classList.add('hidden');
    modeButtonEl.setAttribute('aria-expanded', 'false');
  }
});

const init = async () => {
  setStatus('Loading...');
  try {
    await loadProviders();
    await Promise.all([loadChats(), loadMetrics()]);
    setStatus('Ready');
    if (state.metricsTimer) {
      clearInterval(state.metricsTimer);
    }
    state.metricsTimer = setInterval(() => {
      if (state.metricsMode === 'live') {
        loadMetrics(true).catch(() => {});
      }
    }, 1000);
  } catch (error) {
    setStatus(`Init failed: ${error.message}`, true);
  }
};

window.addEventListener('DOMContentLoaded', () => {
  init();
});
