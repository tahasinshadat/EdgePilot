const BACKEND_URL =
  (window.edgepilot && window.edgepilot.backendUrl) || 'http://127.0.0.1:8000';

const state = {
  providers: {},
  providerId: null,
  chats: [],
  activeChat: null,
  metricsMode: 'live',
  metricsTimer: null,
  metricsLastSnapshot: null,
  metricsErrorCount: 0,
  isThinking: false,
  currentMode: 'ask',
  viewMode: 'chat',
  jobs: [],
  jobsScope: 'chat',
  jobsTimer: null,
  jobsLoading: false,
  settings: null,
  monitorStatus: null
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
const viewTabButtons = Array.from(document.querySelectorAll('.view-tab'));
const jobsPanelEl = document.getElementById('jobs-panel');
const jobsContainerEl = document.getElementById('jobs-container');
const jobsScopeSelect = document.getElementById('jobs-scope');
const jobsRefreshBtn = document.getElementById('jobs-refresh-btn');
const settingsPanelEl = document.getElementById('settings-panel');
const usageAlertsToggle = document.getElementById('usage-alerts-toggle');
const alertThresholdsEl = document.getElementById('alert-thresholds');
const cpuThresholdInput = document.getElementById('cpu-threshold');
const memoryThresholdInput = document.getElementById('memory-threshold');
const diskThresholdInput = document.getElementById('disk-threshold');
const checkIntervalInput = document.getElementById('check-interval');
const saveThresholdsBtn = document.getElementById('save-thresholds-btn');
const monitorStatusText = document.getElementById('monitor-status-text');
const autoStartSettingEl = document.getElementById('auto-start-setting');
const autoStartToggle = document.getElementById('auto-start-toggle');
const autoStartStatusText = document.getElementById('auto-start-status');
const emailAlertsSectionEl = document.getElementById('email-alerts-section');
const emailAlertsToggle = document.getElementById('email-alerts-toggle');
const emailConfigEl = document.getElementById('email-config');
const emailAddressInput = document.getElementById('email-address');
const smtpUsernameInput = document.getElementById('smtp-username');
const smtpPasswordInput = document.getElementById('smtp-password');
const saveEmailConfigBtn = document.getElementById('save-email-config-btn');

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
    updateJobsScopeControl();
    if (state.viewMode === 'jobs') {
      loadJobs().catch(() => {});
    }
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
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code>$1</code>')
      .replace(/^\s*[\*-]\s+/gm, '• ')
      .replace(/\n/g, '<br />');
    messagesEl.appendChild(bubble);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Update token counter with more details
  const tokens = state.activeChat.tokens_used ?? 0;
  const messages = state.activeChat.messages.length;
  tokenCounterEl.textContent = `${messages} messages • ${tokens.toLocaleString()} tokens`;
};

const formatTimestamp = (value) => {
  if (!value) return '—';
  const date = new Date(value * 1000);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

const formatDuration = (start, end) => {
  if (!start || !end) return null;
  const seconds = end - start;
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  return `${(seconds / 60).toFixed(1)} min`;
};

const describeJobTarget = (job) => {
  if (job.target) return job.target;
  if (job.metadata?.app_name) return job.metadata.app_name;
  if (job.metadata?.cwd) return job.metadata.cwd;
  if (job.metadata?.identifier) return job.metadata.identifier;
  if (job.metadata?.args?.length) return job.metadata.args.join(' ');
  return '';
};

const renderJobs = () => {
  if (!jobsContainerEl) return;

  jobsContainerEl.innerHTML = '';

  if (state.jobsLoading) {
    jobsContainerEl.innerHTML = '<div class="empty-state">Loading jobs...</div>';
    return;
  }

  if (state.jobsScope === 'chat' && !state.activeChat) {
    jobsContainerEl.innerHTML = '<div class="empty-state">Select a chat to view its jobs.</div>';
    return;
  }

  if (!state.jobs.length) {
    jobsContainerEl.innerHTML = '<div class="empty-state">No jobs found.</div>';
    return;
  }

  state.jobs.forEach((job) => {
    const card = document.createElement('article');
    card.className = 'job-card';

    const header = document.createElement('div');
    header.className = 'job-card-header';

    const titleWrap = document.createElement('div');
    const title = document.createElement('div');
    title.className = 'job-title';
    title.textContent = job.action?.replace(/_/g, ' ') || 'task';
    const target = describeJobTarget(job);
    if (target) {
      const targetEl = document.createElement('div');
      targetEl.className = 'job-target';
      targetEl.textContent = target;
      titleWrap.appendChild(targetEl);
    }
    titleWrap.prepend(title);

    const status = document.createElement('span');
    const statusLabel = (job.status || 'unknown').replace(/_/g, ' ');
    status.className = `job-status ${job.status || 'unknown'}`;
    status.textContent = statusLabel;

    header.appendChild(titleWrap);
    header.appendChild(status);
    card.appendChild(header);

    const meta = document.createElement('div');
    meta.className = 'job-meta';
    const rows = [
      `Task ID: ${job.task_id}`,
      `Scheduled: ${formatTimestamp(job.scheduled_for)}`,
      `Started: ${formatTimestamp(job.started_at)}`,
      `Finished: ${formatTimestamp(job.finished_at)}`
    ];
    const duration = formatDuration(job.started_at, job.finished_at);
    if (duration) {
      rows.push(`Duration: ${duration}`);
    }
    if (job.metadata?.chat_id && state.jobsScope === 'all') {
      rows.push(`Chat: ${job.metadata.chat_id.slice(0, 8)}…`);
    }
    rows.forEach((value) => {
      const span = document.createElement('span');
      span.textContent = value;
      meta.appendChild(span);
    });
    card.appendChild(meta);

    if (job.error) {
      const errorEl = document.createElement('div');
      errorEl.className = 'job-error';
      errorEl.textContent = `Error: ${job.error}`;
      card.appendChild(errorEl);
    } else if (job.result?.stdout) {
      const output = document.createElement('pre');
      output.className = 'job-output';
      output.textContent = job.result.stdout.trim();
      card.appendChild(output);
    }

    jobsContainerEl.appendChild(card);
  });
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

const updateJobsScopeControl = () => {
  if (!jobsScopeSelect) return;
  const chatOption = Array.from(jobsScopeSelect.options).find(opt => opt.value === 'chat');
  if (chatOption) {
    chatOption.disabled = !state.activeChat;
  }
  if (!state.activeChat && state.jobsScope === 'chat') {
    state.jobsScope = 'all';
  }
  jobsScopeSelect.value = state.jobsScope;
};

const loadJobs = async (quiet = false) => {
  if (!jobsPanelEl || state.viewMode !== 'jobs') return;
  if (state.jobsScope === 'chat' && !state.activeChat) {
    state.jobs = [];
    state.jobsLoading = false;
    renderJobs();
    return;
  }
  state.jobsLoading = true;
  renderJobs();
  try {
    const params = new URLSearchParams({ limit: '200' });
    if (state.jobsScope === 'chat' && state.activeChat) {
      params.append('chat_id', state.activeChat.id);
    }
    const data = await fetchJSON(`/api/tasks?${params.toString()}`);
    state.jobs = data.tasks || [];
    renderJobs();
  } catch (error) {
    if (!quiet) {
      setStatus(`Jobs unavailable: ${error.message}`, true);
    }
  } finally {
    state.jobsLoading = false;
    renderJobs();
  }
};

const startJobsPolling = () => {
  if (state.jobsTimer) return;
  state.jobsTimer = setInterval(() => {
    loadJobs(true).catch(() => {});
  }, 4000);
};

const stopJobsPolling = () => {
  if (state.jobsTimer) {
    clearInterval(state.jobsTimer);
    state.jobsTimer = null;
  }
};

const setJobsScope = (scope) => {
  state.jobsScope = scope;
  updateJobsScopeControl();
  loadJobs().catch(() => {});
};

const setViewMode = (mode) => {
  state.viewMode = mode;
  viewTabButtons.forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.view === mode);
  });

  // Hide all panels first
  messagesEl.classList.add('hidden');
  jobsPanelEl.classList.add('hidden');
  settingsPanelEl.classList.add('hidden');

  if (mode === 'jobs') {
    jobsPanelEl.classList.remove('hidden');
    updateJobsScopeControl();
    loadJobs().catch(() => {});
    startJobsPolling();
  } else if (mode === 'settings') {
    settingsPanelEl.classList.remove('hidden');
    loadSettings().catch(() => {});
    stopJobsPolling();
  } else {
    messagesEl.classList.remove('hidden');
    stopJobsPolling();
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
  updateJobsScopeControl();
};

const loadMetrics = async (quiet = false, retryCount = 0) => {
  if (state.metricsMode !== 'live') {
    return;
  }
  try {
    const metrics = await fetchJSON('/api/metrics');
    state.metricsLastSnapshot = metrics;
    state.metricsErrorCount = 0; // Reset error count on success
    renderMetrics(metrics);
  } catch (error) {
    // Track consecutive errors
    state.metricsErrorCount = (state.metricsErrorCount || 0) + 1;

    // Retry up to 3 times with exponential backoff
    if (retryCount < 3) {
      const backoffDelay = Math.min(1000 * Math.pow(2, retryCount), 5000);
      setTimeout(() => {
        loadMetrics(true, retryCount + 1);
      }, backoffDelay);
      return;
    }

    // After retries fail, show error message
    if (!quiet) {
      setStatus(`Metrics unavailable: ${error.message}`, true);
    }

    // Show error state in metrics panel after multiple failures
    if (state.metricsErrorCount >= 5) {
      metricGridEl.innerHTML = '<div class="metric-empty" style="color: var(--error);">Unable to load metrics. Check if the backend is running.</div>';
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
  updateJobsScopeControl();
  if (state.viewMode === 'jobs' && state.jobsScope === 'chat') {
    loadJobs().catch(() => {});
  }

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
    const response = await fetch(`${BACKEND_URL}/api/chats/${state.activeChat.id}/messages/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: finalPrompt,
        provider: state.providerId
      })
    });

    if (!response.ok) {
      throw new Error(`Stream failed: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    let finalLatencyMs = null;
    let wasCached = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split('\n\n');
      buffer = blocks.pop(); // keep incomplete chunk

      for (const block of blocks) {
        if (!block.trim()) continue;

        let eventType = 'message';
        let eventData = '';

        for (const line of block.split('\n')) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7);
          } else if (line.startsWith('data: ')) {
            eventData = line.slice(6);
          }
        }

        let payload = {};
        try {
          payload = JSON.parse(eventData);
        } catch (e) {
          payload = eventData;
        }

        if (eventType === 'status') {
          setStatus(payload.text);
        } else if (eventType === 'tool') {
          setStatus(`Ran tool: ${payload.name}`);
        } else if (eventType === 'cache_hit') {
          wasCached = true;
          setStatus('Semantic cache found (instant response)');
        } else if (eventType === 'done') {
          finalLatencyMs = payload.latency_ms;
        } else if (eventType === 'error') {
          throw new Error(payload.detail || 'Streaming error');
        }
      }
    }

    // Stream finished successfully, fetch the updated chat state
    const updatedChat = await fetchJSON(`/api/chats/${state.activeChat.id}`);

    hideThinking();

    state.activeChat = updatedChat;
    const idx = state.chats.findIndex((chat) => chat.id === updatedChat.id);
    if (idx !== -1) {
      state.chats[idx] = updatedChat;
    }
    chatTitleEl.textContent = updatedChat.title;
    renderChats();
    renderMessages();

    // Update session metrics if visible
    if (state.metricsMode === 'session') {
      renderMetrics(null);
    }
    if (state.viewMode === 'jobs') {
      loadJobs(true).catch(() => {});
    }

    let readyMsg = 'Ready';
    if (finalLatencyMs !== null && finalLatencyMs !== undefined) {
      const sec = (finalLatencyMs / 1000).toFixed(2);
      readyMsg = `Ready (took ${sec}s${wasCached ? ' - Cache Found' : ''})`;
    } else if (wasCached) {
      readyMsg = 'Ready (Cache Found)';
    }
    setStatus(readyMsg);
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

viewTabButtons.forEach((tab) => {
  tab.addEventListener('click', () => {
    setViewMode(tab.dataset.view);
  });
});

if (jobsScopeSelect) {
  jobsScopeSelect.addEventListener('change', (event) => {
    setJobsScope(event.target.value);
  });
}

if (jobsRefreshBtn) {
  jobsRefreshBtn.addEventListener('click', () => {
    loadJobs().catch(() => {});
  });
}

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

// ===========================
// Settings Management
// ===========================

const loadSettings = async () => {
  try {
    const settings = await fetchJSON('/api/settings');
    state.settings = settings;

    // Update usage alerts UI
    usageAlertsToggle.checked = settings.usage_alerts_enabled || false;

    const thresholds = settings.alert_thresholds || {};
    cpuThresholdInput.value = thresholds.cpu_percent || 85;
    memoryThresholdInput.value = thresholds.memory_percent || 85;
    diskThresholdInput.value = thresholds.disk_percent || 90;
    checkIntervalInput.value = settings.check_interval_seconds || 30;

    // Show/hide thresholds and auto-start based on toggle
    if (settings.usage_alerts_enabled) {
      alertThresholdsEl.classList.remove('hidden');
      emailAlertsSectionEl.classList.remove('hidden');
      autoStartSettingEl.style.display = 'block';
    } else {
      alertThresholdsEl.classList.add('hidden');
      emailAlertsSectionEl.classList.add('hidden');
      autoStartSettingEl.style.display = 'none';
    }

    // Update email alerts UI
    emailAlertsToggle.checked = settings.email_alerts_enabled || false;
    emailAddressInput.value = settings.email_address || '';
    smtpUsernameInput.value = settings.smtp_username || '';
    smtpPasswordInput.value = settings.smtp_password || '';

    // Show/hide email config based on toggle
    if (settings.email_alerts_enabled) {
      emailConfigEl.classList.remove('hidden');
    } else {
      emailConfigEl.classList.add('hidden');
    }

    // Load monitor and auto-start status
    await loadMonitorStatus();
    await loadAutoStartStatus();
  } catch (error) {
    console.error('Failed to load settings:', error);
  }
};

const loadMonitorStatus = async () => {
  try {
    const status = await fetchJSON('/api/settings/monitor-status');
    state.monitorStatus = status;

    if (status.running) {
      monitorStatusText.textContent = `Monitor running (PID: ${status.pid})`;
      monitorStatusText.className = 'status-badge running';
    } else {
      monitorStatusText.textContent = 'Monitor stopped';
      monitorStatusText.className = 'status-badge stopped';
    }
  } catch (error) {
    monitorStatusText.textContent = 'Error checking status';
    monitorStatusText.className = 'status-badge error';
  }
};

const loadAutoStartStatus = async () => {
  try {
    const status = await fetchJSON('/api/settings/auto-start/status');

    autoStartToggle.checked = status.installed || false;

    if (status.installed) {
      autoStartStatusText.textContent = '✓ Installed - will start on boot';
      autoStartStatusText.style.color = 'var(--accent)';
    } else {
      autoStartStatusText.textContent = '✗ Not installed';
      autoStartStatusText.style.color = 'var(--text-secondary)';
    }
  } catch (error) {
    console.error('Failed to load auto-start status:', error);
    autoStartStatusText.textContent = 'Error checking status';
    autoStartStatusText.style.color = 'var(--text-secondary)';
  }
};

const saveSettings = async (updates) => {
  try {
    const settings = await fetchJSON('/api/settings', {
      method: 'POST',
      body: JSON.stringify(updates)
    });
    state.settings = settings;
    setStatus('Settings saved');

    // Reload monitor status after a delay
    setTimeout(loadMonitorStatus, 1000);
  } catch (error) {
    setStatus(`Failed to save settings: ${error.message}`, true);
  }
};

const setupSettingsEventListeners = () => {
  // Event: Toggle usage alerts
  if (usageAlertsToggle) {
    usageAlertsToggle.addEventListener('change', async (e) => {
      const enabled = e.target.checked;

      // Show/hide thresholds, email section, and auto-start
      if (enabled) {
        alertThresholdsEl.classList.remove('hidden');
        emailAlertsSectionEl.classList.remove('hidden');
        autoStartSettingEl.style.display = 'block';

        // Auto-enable auto-start when usage alerts are enabled
        await loadAutoStartStatus();
        if (!autoStartToggle.checked) {
          autoStartStatusText.textContent = 'Installing auto-start...';
          autoStartStatusText.style.color = 'var(--text-secondary)';

          try {
            const result = await fetchJSON('/api/settings/auto-start/install', { method: 'POST' });
            if (result.success) {
              autoStartToggle.checked = true;
              autoStartStatusText.textContent = '✓ Installed - will start on boot';
              autoStartStatusText.style.color = 'var(--accent)';
            } else {
              autoStartStatusText.textContent = '✗ Failed to install';
              autoStartStatusText.style.color = 'var(--text-secondary)';
            }
          } catch (error) {
            autoStartStatusText.textContent = '✗ Error installing';
            autoStartStatusText.style.color = 'var(--text-secondary)';
          }
        }
      } else {
        alertThresholdsEl.classList.add('hidden');
        emailAlertsSectionEl.classList.add('hidden');
        autoStartSettingEl.style.display = 'none';
      }

      // Save to backend
      await saveSettings({ usage_alerts_enabled: enabled });
    });
  }

  // Event: Toggle auto-start
  if (autoStartToggle) {
    autoStartToggle.addEventListener('change', async (e) => {
      const enabled = e.target.checked;

      autoStartStatusText.textContent = enabled ? 'Installing...' : 'Uninstalling...';
      autoStartStatusText.style.color = 'var(--text-secondary)';

      try {
        const endpoint = enabled ? '/api/settings/auto-start/install' : '/api/settings/auto-start/uninstall';
        const result = await fetchJSON(endpoint, { method: 'POST' });

        if (result.success) {
          if (enabled) {
            autoStartStatusText.textContent = '✓ Installed - will start on boot';
            autoStartStatusText.style.color = 'var(--accent)';
            setStatus('Auto-start installed successfully');
          } else {
            autoStartStatusText.textContent = '✗ Not installed';
            autoStartStatusText.style.color = 'var(--text-secondary)';
            setStatus('Auto-start removed successfully');
          }
        } else {
          autoStartToggle.checked = !enabled; // Revert toggle
          autoStartStatusText.textContent = enabled ? '✗ Failed to install' : '✗ Failed to uninstall';
          autoStartStatusText.style.color = 'var(--text-secondary)';
          setStatus(result.error || 'Failed to update auto-start', true);
        }
      } catch (error) {
        autoStartToggle.checked = !enabled; // Revert toggle
        autoStartStatusText.textContent = '✗ Error';
        autoStartStatusText.style.color = 'var(--text-secondary)';
        setStatus(`Error: ${error.message}`, true);
      }
    });
  }

  // Event: Save thresholds
  if (saveThresholdsBtn) {
    saveThresholdsBtn.addEventListener('click', async () => {
      const updates = {
        alert_thresholds: {
          cpu_percent: parseFloat(cpuThresholdInput.value),
          memory_percent: parseFloat(memoryThresholdInput.value),
          disk_percent: parseFloat(diskThresholdInput.value)
        },
        check_interval_seconds: parseInt(checkIntervalInput.value, 10)
      };

      await saveSettings(updates);
    });
  }

  // Event: Toggle email alerts
  if (emailAlertsToggle) {
    emailAlertsToggle.addEventListener('change', async (e) => {
      const enabled = e.target.checked;

      // Show/hide email config
      if (enabled) {
        emailConfigEl.classList.remove('hidden');
      } else {
        emailConfigEl.classList.add('hidden');
      }

      // Save to backend
      await saveSettings({ email_alerts_enabled: enabled });
    });
  }

  // Event: Save email configuration
  if (saveEmailConfigBtn) {
    saveEmailConfigBtn.addEventListener('click', async () => {
      // Validate email address is provided if email alerts are enabled
      const emailAddress = emailAddressInput.value.trim();
      if (emailAlertsToggle.checked && !emailAddress) {
        setStatus('Please enter your email address or disable email alerts', true);
        emailAddressInput.focus();
        return;
      }

      const updates = {
        email_address: emailAddress,
        smtp_username: smtpUsernameInput.value.trim(),
        smtp_password: smtpPasswordInput.value
      };

      await saveSettings(updates);
    });
  }
};

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
  setViewMode(state.viewMode);
  setupSettingsEventListeners();
  init();
});
