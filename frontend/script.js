const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : '/api';

const ErrorMessages = {
    CHAT_LOAD: 'Failed to load chats',
    CHAT_CREATE: 'Failed to create chat',
    CHAT_DELETE: 'Failed to delete chat',
    MESSAGES_LOAD: 'Failed to load messages',
    DOCUMENTS_LOAD: 'Failed to load documents',
    DOCUMENT_UPLOAD: 'Failed to upload document',
    DOCUMENT_DELETE: 'Failed to delete document',
    DOCUMENT_REPROCESS: 'Failed to reprocess document',
    DOCUMENT_UPDATE: 'Failed to update document',
    QUERY_PREPARE: 'Failed to prepare chat',
    QUERY_RESPONSE: 'Failed to get response',
    NO_DOCUMENTS: 'No active documents selected for querying',
    NETWORK: 'Network error - please check your connection',
    SERVER: 'Server error - please try again later'
};

const CACHE_KEYS = {
    DOCUMENTS: 'rag_documents_cache',
    DOCUMENTS_TIMESTAMP: 'rag_documents_timestamp'
};

const CACHE_DURATION = 5 * 60 * 1000;
const POLL_INTERVAL = 10000;  // 10s statt 3s → reduziert DB-Last
const MAX_POLL_ATTEMPTS = 60;  // 60 * 10s = 10min max

let currentChatId = null;
let chats = [];
let documents = [];
let documentPollers = new Map();
let uploadProgressElement = null;

const chatList = document.getElementById('chatList');
const messagesContainer = document.getElementById('messagesContainer');
const queryInput = document.getElementById('queryInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');
const chatTitle = document.getElementById('chatTitle');
const deleteChatBtn = document.getElementById('deleteChatBtn');
const documentsList = document.getElementById('documentsList');
const refreshDocsBtn = document.getElementById('refreshDocsBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');
const toast = document.getElementById('toast');
const processingIndicator = document.getElementById('processingIndicator');
const processingCount = document.getElementById('processingCount');

document.addEventListener('DOMContentLoaded', async () => {
    initializeDocumentCache();
    setupEventListeners();
    await Promise.all([loadChats(), loadDocuments()]).catch(console.error);
    startDocumentPolling();
});

function setupEventListeners() {
    newChatBtn.addEventListener('click', createNewChat);
    sendBtn.addEventListener('click', sendQuery);
    uploadBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileUpload);
    deleteChatBtn.addEventListener('click', deleteCurrentChat);
    refreshDocsBtn.addEventListener('click', () => loadDocuments(true));

    queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendQuery().then();
        }
    });
}

class ApiError extends Error {
    constructor(message, status, detail) {
        super(message);
        this.status = status;
        this.detail = detail;
    }
}

async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    let response;
    try {
        response = await fetch(`${API_BASE}${endpoint}`, options);
    } catch (networkError) {
        throw new ApiError(ErrorMessages.NETWORK, 0, networkError.message);
    }

    if (!response.ok) {
        let detail = 'Request failed';
        try {
            const errorBody = await response.json();
            detail = errorBody.detail || detail;
        } catch (parseError) {}

        if (response.status >= 500) {
            throw new ApiError(ErrorMessages.SERVER, response.status, detail);
        }
        throw new ApiError(detail, response.status, detail);
    }

    return response.json();
}

function initializeDocumentCache() {
    const cached = getDocumentsFromCache();
    if (cached) {
        documents = cached;
        renderDocuments();
    }
}

function getDocumentsFromCache() {
    try {
        const timestamp = localStorage.getItem(CACHE_KEYS.DOCUMENTS_TIMESTAMP);
        if (!timestamp || Date.now() - parseInt(timestamp) > CACHE_DURATION) {
            return null;
        }

        const cached = localStorage.getItem(CACHE_KEYS.DOCUMENTS);
        return cached ? JSON.parse(cached) : null;
    } catch {
        return null;
    }
}

function saveDocumentsToCache(docs) {
    try {
        localStorage.setItem(CACHE_KEYS.DOCUMENTS, JSON.stringify(docs));
        localStorage.setItem(CACHE_KEYS.DOCUMENTS_TIMESTAMP, Date.now().toString());
    } catch (error) {
        console.warn('Failed to cache documents:', error);
    }
}

function clearDocumentsCache() {
    try {
        localStorage.removeItem(CACHE_KEYS.DOCUMENTS);
        localStorage.removeItem(CACHE_KEYS.DOCUMENTS_TIMESTAMP);
    } catch {}
}

async function loadChats() {
    try {
        chats = await apiCall('/chats');
        renderChats();

        if (!currentChatId && chats.length > 0) {
            await selectChat(chats[0].id);
        }
    } catch (error) {
        showToast(`${ErrorMessages.CHAT_LOAD}: ${error.detail || error.message}`, 'error');
        console.error(error);
    }
}

function renderChats() {
    chatList.innerHTML = '';

    if (chats.length === 0) {
        chatList.innerHTML = '<div class="empty-state">No chats yet</div>';
        return;
    }

    chats.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.className = 'chat-item';
        if (chat.id === currentChatId) {
            chatItem.classList.add('active');
        }

        const date = new Date(chat.updated_at);
        const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

        chatItem.innerHTML = `
            <div class="chat-item-title">${escapeHtml(chat.title)}</div>
            <div class="chat-item-date">${dateStr}</div>
        `;

        chatItem.addEventListener('click', () => selectChat(chat.id));
        chatList.appendChild(chatItem);
    });
}

async function createNewChat() {
    const title = prompt('Enter chat title:', 'New Chat');
    if (!title) return;

    try {
        showLoading('Creating chat...');
        const chat = await apiCall('/chats', 'POST', { title });
        chats.unshift(chat);
        renderChats();
        await selectChat(chat.id);
        showToast('Chat created successfully', 'success');
    } catch (error) {
        showToast(`${ErrorMessages.CHAT_CREATE}: ${error.detail || error.message}`, 'error');
        console.error(error);
    } finally {
        hideLoading();
    }
}

async function selectChat(chatId) {
    currentChatId = chatId;
    const chat = chats.find(c => c.id === chatId);

    if (chat) {
        chatTitle.textContent = chat.title;
        deleteChatBtn.style.display = 'block';
    }

    renderChats();
    await loadMessages(chatId);

    queryInput.disabled = false;
    sendBtn.disabled = false;
}

async function ensureActiveChat() {
    if (currentChatId) return currentChatId;

    if (chats.length > 0) {
        await selectChat(chats[0].id);
        return currentChatId;
    }

    try {
        showLoading('Creating chat...');
        const chat = await apiCall('/chats', 'POST', { title: `Chat ${chats.length + 1}` });
        chats.unshift(chat);
        renderChats();
        await selectChat(chat.id);
        showToast('New chat created', 'success');
        return chat.id;
    } finally {
        hideLoading();
    }
}

async function loadMessages(chatId) {
    try {
        showLoading('Loading messages...');
        const messages = await apiCall(`/chats/${chatId}/messages`);
        renderMessages(messages);
    } catch (error) {
        showToast(`${ErrorMessages.MESSAGES_LOAD}: ${error.detail || error.message}`, 'error');
        console.error(error);
    } finally {
        hideLoading();
    }
}

function renderMessages(messages) {
    messagesContainer.innerHTML = '';

    if (messages.length === 0) {
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <h2>Start asking questions!</h2>
                <p>Ask questions about your uploaded documents.</p>
            </div>
        `;
        return;
    }

    messages.forEach(message => {
        const elements = createMessageElement(message.role, message.content, {
            timestamp: message.created_at
        });
        messagesContainer.appendChild(elements.messageDiv);
    });

    scrollToBottom();
}

async function sendQuery() {
    if (!queryInput.value.trim()) return;

    try {
        await ensureActiveChat();
    } catch (error) {
        showToast(`${ErrorMessages.QUERY_PREPARE}: ${error.detail || error.message}`, 'error');
        console.error(error);
        return;
    }

    const query = queryInput.value.trim();
    queryInput.value = '';

    const userElements = createMessageElement('user', query);
    messagesContainer.appendChild(userElements.messageDiv);

    const assistantElements = createMessageElement('assistant', '');
    messagesContainer.appendChild(assistantElements.messageDiv);

    scrollToBottom();

    try {
        await streamQuery(query, assistantElements);
        await loadChats();
    } catch (error) {
        assistantElements.contentDiv.innerHTML = `<span class="error-message">Error: ${error.detail || error.message}</span>`;
        showToast(`${ErrorMessages.QUERY_RESPONSE}: ${error.detail || error.message}`, 'error');
        console.error(error);
    }
}

async function deleteCurrentChat() {
    if (!currentChatId) return;
    if (!confirm('Are you sure you want to delete this chat?')) return;

    try {
        showLoading('Deleting chat...');
        await apiCall(`/chats/${currentChatId}`, 'DELETE');

        chats = chats.filter(c => c.id !== currentChatId);
        currentChatId = null;

        chatTitle.textContent = 'Select a chat or create a new one';
        deleteChatBtn.style.display = 'none';
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <h2>Welcome to RAG Chat System</h2>
                <p>Upload documents and ask questions about them!</p>
            </div>
        `;

        queryInput.disabled = false;
        sendBtn.disabled = false;

        renderChats();
        showToast('Chat deleted successfully', 'success');
    } catch (error) {
        showToast(`${ErrorMessages.CHAT_DELETE}: ${error.detail || error.message}`, 'error');
        console.error(error);
    } finally {
        hideLoading();
    }
}

async function loadDocuments(forceRefresh = false) {
    if (forceRefresh) {
        clearDocumentsCache();
    }

    try {
        documents = await apiCall('/documents');
        saveDocumentsToCache(documents);

        // Start polling first, then render to show processing status correctly
        documents.forEach(doc => {
            if (!doc.processed) {
                startPollingDocument(doc.id);
            }
        });

        renderDocuments();
    } catch (error) {
        showToast(`${ErrorMessages.DOCUMENTS_LOAD}: ${error.detail || error.message}`, 'error');
        console.error(error);
    }
}

function renderDocuments() {
    documentsList.innerHTML = '';

    if (documents.length === 0) {
        documentsList.innerHTML = '<div class="empty-state">No documents uploaded</div>';
        updateProcessingIndicator();
        return;
    }

    documents.forEach(doc => {
        const docItem = document.createElement('div');
        docItem.className = 'document-item';
        docItem.id = `doc-${doc.id}`;

        const date = new Date(doc.uploaded_at).toLocaleDateString();
        const isProcessed = doc.processed;
        const isActivelyProcessing = doc.is_actively_processing || false;
        const isQueued = !isProcessed && !isActivelyProcessing && documentPollers.has(doc.id);

        let statusContent;
        if (isActivelyProcessing) {
            statusContent = `
                <div class="document-status processing">
                    <span class="status-spinner"></span>
                    <span>Processing...</span>
                </div>
            `;
        } else if (isQueued) {
            statusContent = `
                <div class="document-status queued">
                    <span class="status-icon">⏳</span>
                    <span>Queued</span>
                </div>
            `;
        } else if (isProcessed) {
            // Successfully processed
            statusContent = `
                <div class="document-status processed">
                    <span class="status-icon">✓</span>
                    <span>${doc.num_chunks} chunks</span>
                </div>
            `;
        } else {
            // Not processed and not queued
            statusContent = `
                <div class="document-status unprocessed">
                    <span class="status-icon">⚠</span>
                    <span>Not processed</span>
                </div>
            `;
        }

        const queryPillClass = doc.query_enabled ? 'query-pill active' : 'query-pill inactive';

        docItem.innerHTML = `
            <div class="document-name">${escapeHtml(doc.filename)}</div>
            <div class="document-info-row">
                <span>${date}</span>
                <span class="document-collection">${escapeHtml(doc.collection_name)}</span>
            </div>
            <div class="document-status-row">
                ${statusContent}
                <div class="${queryPillClass}">${doc.query_enabled ? 'Query on' : 'Query off'}</div>
            </div>
            <div class="document-actions">
                ${!isProcessed && !isActivelyProcessing && !isQueued ? `<button class="btn-reprocess" data-id="${doc.id}">Reprocess</button>` : ''}
                ${isProcessed ? `<button class="doc-toggle ${doc.query_enabled ? 'active' : ''}" data-id="${doc.id}" aria-pressed="${doc.query_enabled}">${doc.query_enabled ? 'ON' : 'OFF'}</button>` : ''}
                <button class="btn-delete-doc" data-id="${doc.id}">Delete</button>
            </div>
        `;

        const reprocessBtn = docItem.querySelector('.btn-reprocess');
        if (reprocessBtn) {
            reprocessBtn.addEventListener('click', () => reprocessDocument(doc.id));
        }

        const toggleBtn = docItem.querySelector('.doc-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => toggleDocumentQuery(doc.id, doc.query_enabled));
        }

        const deleteBtn = docItem.querySelector('.btn-delete-doc');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => deleteDocument(doc.id));
        }

        documentsList.appendChild(docItem);
    });

    updateProcessingIndicator();
}

function updateProcessingIndicator() {
    // Only count actively processing documents (not queued)
    const processingDocs = documents.filter(doc => doc.is_actively_processing === true);
    const count = processingDocs.length;

    if (count > 0) {
        processingCount.textContent = ""+count;
        processingIndicator.style.display = 'flex';
    } else {
        processingIndicator.style.display = 'none';
    }
}


 async function reprocessDocument(docId) {
      try {
          await apiCall(`/documents/${docId}/reprocess`, 'POST');
          await startPollingDocument(docId);
          await loadDocuments();
          showToast('Document reprocessing started', 'success');
      } catch (error) {
          showToast(`${ErrorMessages.DOCUMENT_REPROCESS}:
          ${error.detail || error.message}`, 'error');
          console.error(error);
     }
}



async function deleteDocument(docId) {
    if (!confirm('Are you sure you want to delete this document?')) return;

    try {
        showLoading('Deleting document...');

        stopPollingDocument(docId);

        await apiCall(`/documents/${docId}`, 'DELETE');
        await loadDocuments(true);

        showToast('Document deleted successfully', 'success');
    } catch (error) {
        showToast(`${ErrorMessages.DOCUMENT_DELETE}: ${error.detail || error.message}`, 'error');
        console.error(error);
    } finally {
        hideLoading();
    }
}

async function toggleDocumentQuery(docId, currentState) {
    try {
        const nextState = !currentState;
        await apiCall(`/documents/${docId}/preferences`, 'PATCH', { query_enabled: nextState });

        const doc = documents.find(d => d.id === docId);
        if (doc) {
            doc.query_enabled = nextState;
            saveDocumentsToCache(documents);
        }

        renderDocuments();
        showToast(nextState ? 'Document enabled for queries' : 'Document excluded from queries', 'success');
    } catch (error) {
        showToast(`${ErrorMessages.DOCUMENT_UPDATE}: ${error.detail || error.message}`, 'error');
        console.error(error);
    }
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        createUploadProgress(file.name);

        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                updateUploadProgress(percentComplete, 'Uploading...');
            }
        });

        xhr.addEventListener('load', async () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const doc = JSON.parse(xhr.responseText);

                    updateUploadProgress(100, 'Processing document...');

                    documents.unshift(doc);
                    saveDocumentsToCache(documents);
                    renderDocuments();

                    startPollingDocument(doc.id);

                    setTimeout(() => {
                        removeUploadProgress();
                        showToast('Document uploaded successfully', 'success');
                    }, 1000);
                } catch (error) {
                    removeUploadProgress();
                    showToast('Upload succeeded but failed to parse response', 'error');
                }
            } else {
                removeUploadProgress();
                let detail = 'Upload failed';
                try {
                    const errorBody = JSON.parse(xhr.responseText);
                    detail = errorBody.detail || detail;
                } catch {}
                showToast(`${ErrorMessages.DOCUMENT_UPLOAD}: ${detail}`, 'error');
            }
        });

        xhr.addEventListener('error', () => {
            removeUploadProgress();
            showToast(`${ErrorMessages.DOCUMENT_UPLOAD}: ${ErrorMessages.NETWORK}`, 'error');
        });

        xhr.open('POST', `${API_BASE}/documents`);
        xhr.send(formData);

    } catch (error) {
        removeUploadProgress();
        showToast(`${ErrorMessages.DOCUMENT_UPLOAD}: ${error.message}`, 'error');
        console.error(error);
    } finally {
        fileInput.value = '';
    }
}

function createUploadProgress(filename) {
    uploadProgressElement = document.createElement('div');
    uploadProgressElement.className = 'upload-progress-card';
    uploadProgressElement.innerHTML = `
        <div class="upload-filename">${escapeHtml(filename)}</div>
        <div class="upload-progress-bar">
            <div class="upload-progress-fill" style="width: 0"></div>
        </div>
        <div class="upload-status">Preparing upload...</div>
    `;

    documentsList.insertBefore(uploadProgressElement, documentsList.firstChild);
}

function updateUploadProgress(percent, statusText) {
    if (!uploadProgressElement) return;

    const fill = uploadProgressElement.querySelector('.upload-progress-fill');
    const status = uploadProgressElement.querySelector('.upload-status');

    if (fill) {
        fill.style.width = `${Math.min(percent, 100)}%`;
    }

    if (status) {
        status.textContent = statusText || `${Math.round(percent)}%`;
    }
}

function removeUploadProgress() {
    if (uploadProgressElement) {
        uploadProgressElement.remove();
        uploadProgressElement = null;
    }
}

function startDocumentPolling() {
    documents.forEach(doc => {
        if (!doc.processed) {
            startPollingDocument(doc.id);
        }
    });
}

async function startPollingDocument(docId) {
    if (documentPollers.has(docId)) {
        return;
    }

    // Use SSE for real-time progress
    try {
        const eventSource = new EventSource(`${API_BASE}/documents/${docId}/processing-stream`);

        eventSource.addEventListener('waiting', (event) => {
            const status = JSON.parse(event.data);
            updateDocumentProgress(docId, status);
        });

        eventSource.addEventListener('progress', (event) => {
            const status = JSON.parse(event.data);
            updateDocumentProgress(docId, status);
        });

        eventSource.addEventListener('complete', (event) => {
            const status = JSON.parse(event.data);
            updateDocumentProgress(docId, status);
            eventSource.close();
            documentPollers.delete(docId);

            setTimeout(() => {
                loadDocuments(true);
                showToast(`Document processed: ${status.num_chunks} chunks created`, 'success');
            }, 1000);
        });

        eventSource.addEventListener('timeout', () => {
            console.warn('Processing timeout for document', docId);
            eventSource.close();
            documentPollers.delete(docId);
            showToast('Document processing timeout', 'warning');
        });

        eventSource.addEventListener('error', (event) => {
            console.error('SSE error for document', docId, event);
            eventSource.close();
            documentPollers.delete(docId);

            startLegacyPolling(docId);
        });

        documentPollers.set(docId, eventSource);
        renderDocuments();

    } catch (error) {
        console.error('Failed to start SSE, falling back to polling:', error);
        await startLegacyPolling(docId);
    }
}

function updateDocumentProgress(docId, status) {
    const docItem = document.getElementById(`doc-${docId}`);
    if (!docItem) return;

    const statusRow = docItem.querySelector('.document-status-row');
    if (!statusRow) return;

    const progressPercent = Math.round(status.progress * 100);
    const stageEmoji = {
        'starting': '🚀',
        'extraction': '📄',
        'metadata': '📋',
        'chunking': '✂️',
        'embedding': '🔢',
        'storing': '💾',
        'finalizing': '⚡',
        'complete': '✅',
        'queued': '⏳',
        'error': '❌'
    };

    const emoji = stageEmoji[status.stage] || '🔄';

    statusRow.innerHTML = `
        <div class="document-status processing">
            <div class="progress-container">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progressPercent}%"></div>
                </div>
                <span class="progress-text">${emoji} ${status.message} (${progressPercent}%)</span>
            </div>
        </div>
    `;
}

async function startLegacyPolling(docId) {
    if (documentPollers.has(docId))
        return;

    let attempts = 0;

    const pollerId = setInterval(async () => {
        attempts++;

        if (attempts > MAX_POLL_ATTEMPTS) {
            stopPollingDocument(docId);
            showToast('Document processing timeout', 'warning');
            renderDocuments();
            return;
        }

        try {
            const doc = await apiCall(`/documents/${docId}`);

            const index = documents.findIndex(d => d.id === docId);
            if (index !== -1)
                documents[index] = doc;

            if (doc.processed) {
                stopPollingDocument(docId);
                saveDocumentsToCache(documents);
                renderDocuments();
                showToast(`Document processed: ${doc.filename}`, 'success');
            }
        } catch (error) {
            console.error(`Polling error for doc ${docId}:`, error);

            if (error.status >= 400) {
                stopPollingDocument(docId);

                documents = documents.filter(d => d.id !== docId);
                saveDocumentsToCache(documents);
                renderDocuments();

                console.warn(`Stopped polling for deleted/invalid document ${docId}`);
            }
        }
    }, POLL_INTERVAL);

    documentPollers.set(docId, pollerId);

    renderDocuments();
}

function stopPollingDocument(docId) {
    const poller = documentPollers.get(docId);
    if (poller)
        if (poller.close && typeof poller.close === 'function')
            poller.close();
        else
            clearInterval(poller);
        documentPollers.delete(docId);
}

function showLoading(text = 'Loading...') {
    loadingText.textContent = text;
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

function showToast(message, type = 'info') {
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 4000);
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function throttle(func, delay) {
    let timeoutId;
    let lastRan;
    return function(...args) {
        if (!lastRan) {
            func.apply(this, args);
            lastRan = Date.now();
        } else {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => {
                if ((Date.now() - lastRan) >= delay) {
                    func.apply(this, args);
                    lastRan = Date.now();
                }
            }, delay - (Date.now() - lastRan));
        }
    };
}

const throttledScroll = throttle(scrollToBottom, 100);

function createMessageElement(role, content, options = {}) {
    const { sources = null, timestamp = null } = options;
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    let thinkingContainer = null;
    if (role === 'assistant') {
        thinkingContainer = document.createElement('details');
        thinkingContainer.className = 'thinking-container';

        const thinkingSummary = document.createElement('summary');
        thinkingSummary.textContent = 'Thinking...';
        thinkingContainer.appendChild(thinkingSummary);

        const thinkingContent = document.createElement('div');
        thinkingContent.className = 'thinking-content';
        thinkingContainer.appendChild(thinkingContent);

        messageDiv.appendChild(thinkingContainer);
    }

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = renderMarkdown(content);

    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    const date = timestamp ? new Date(timestamp) : new Date();
    timeDiv.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    messageDiv.appendChild(contentDiv);
    messageDiv.appendChild(timeDiv);

    let sourcesContainer = null;
    if (sources && sources.length > 0) {
        sourcesContainer = buildSourcesElement(sources);
        messageDiv.appendChild(sourcesContainer);
    }

    return { messageDiv, contentDiv, sourcesContainer, timeDiv, thinkingContainer };
}

function buildSourcesElement(sources) {
    const container = document.createElement('div');
    container.className = 'message-sources';

    const title = document.createElement('strong');
    title.textContent = 'Sources:';
    container.appendChild(title);

    sources.forEach((source, index) => {
        const isObject = source && typeof source === 'object';
        const label = isObject ? (source.label || `Source ${index + 1}`) : String(source);
        const contentText = isObject ? (source.content || '') : '';

        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = label;
        details.appendChild(summary);

        const content = document.createElement('pre');
        content.textContent = contentText;
        if (contentText) {
            details.appendChild(content);
        }

        container.appendChild(details);
    });

    return container;
}

function renderMarkdown(text = '') {
    if (!text) return '';
    const html = marked.parse(text, { breaks: true });
    return DOMPurify.sanitize(html);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function streamQuery(query, assistantElements) {
    let response;
    try {
        response = await fetch(`${API_BASE}/query/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: currentChatId, query }),
        });
    } catch (networkError) {
        throw new ApiError(ErrorMessages.NETWORK, 0, networkError.message);
    }

    if (!response.ok || !response.body) {
        let detail = 'Streaming request failed';
        try {
            const errorPayload = await response.json();
            detail = errorPayload.detail || detail;
        } catch (parseError) {}
        throw new ApiError(detail, response.status, detail);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let accumulated = '';
    let thinkingSteps = [];

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let separatorIndex;
        while ((separatorIndex = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, separatorIndex).trim();
            buffer = buffer.slice(separatorIndex + 2);

            if (!rawEvent.startsWith('data:')) continue;

            const dataString = rawEvent.replace(/^data:\s*/, '');
            if (!dataString) continue;

            let payload;
            try {
                payload = JSON.parse(dataString);
            } catch (err) {
                console.error('Failed to parse SSE payload', err);
                continue;
            }

            if (payload.type === 'thinking') {
                thinkingSteps.push(payload.step);
                updateThinkingDisplay(assistantElements, thinkingSteps);
                throttledScroll();
            } else if (payload.type === 'chunk') {
                if (payload.content) {
                    accumulated += payload.content;
                    assistantElements.contentDiv.textContent = accumulated;
                    throttledScroll();
                }
            } else if (payload.type === 'end') {
                accumulated = payload.content || accumulated;
                assistantElements.contentDiv.innerHTML = renderMarkdown(accumulated);
                finalizeThinkingDisplay(assistantElements, thinkingSteps);
                if (payload.sources?.length > 0) {
                    if (assistantElements.sourcesContainer) {
                        assistantElements.sourcesContainer.remove();
                    }
                    assistantElements.sourcesContainer = buildSourcesElement(payload.sources);
                    assistantElements.messageDiv.appendChild(assistantElements.sourcesContainer);
                }
                scrollToBottom();
            } else if (payload.type === 'error') {
                throw new ApiError(payload.message || 'Streaming error', 500, payload.message);
            }
        }
    }
}

function updateThinkingDisplay(assistantElements, thinkingSteps) {
    if (!assistantElements.thinkingContainer) return;

    const thinkingContent = assistantElements.thinkingContainer.querySelector('.thinking-content');
    if (!thinkingContent) return;

    const summary = assistantElements.thinkingContainer.querySelector('summary');
    const lastStep = thinkingSteps[thinkingSteps.length - 1];
    if (lastStep && summary) {
        summary.textContent = lastStep.message;
    }

    let stepsList = thinkingContent.querySelector('.thinking-steps');
    if (!stepsList) {
        stepsList = document.createElement('ul');
        stepsList.className = 'thinking-steps';
        thinkingContent.appendChild(stepsList);
    }

    const step = lastStep;
    const icon = getThinkingIcon(step.type);

    const li = document.createElement('li');
    li.className = `thinking-step ${step.type}`;

    const iconSpan = document.createElement('span');
    iconSpan.className = 'step-icon';
    iconSpan.textContent = icon;
    li.appendChild(iconSpan);

    const messageSpan = document.createElement('span');
    messageSpan.className = 'step-message';
    messageSpan.textContent = step.message;
    li.appendChild(messageSpan);

    if (step.details && Array.isArray(step.details)) {
        const detailsList = document.createElement('ul');
        detailsList.className = 'step-details';

        step.details.forEach(detail => {
            const detailLi = document.createElement('li');
            if (typeof detail === 'string') {
                detailLi.textContent = detail;
            } else if (detail.text && detail.score !== undefined) {
                const scoreSpan = document.createElement('span');
                scoreSpan.className = 'score';
                scoreSpan.textContent = `[${detail.score.toFixed(3)}]`;
                detailLi.appendChild(scoreSpan);
                detailLi.appendChild(document.createTextNode(` ${detail.text}`));
            } else {
                detailLi.textContent = JSON.stringify(detail);
            }
            detailsList.appendChild(detailLi);
        });

        li.appendChild(detailsList);
    }

    stepsList.appendChild(li);
}

function finalizeThinkingDisplay(assistantElements, thinkingSteps) {
    if (!assistantElements.thinkingContainer) return;

    const summary = assistantElements.thinkingContainer.querySelector('summary');
    if (summary) {
        summary.textContent = `Thinking (${thinkingSteps.length} steps) - click to expand`;
    }

    assistantElements.thinkingContainer.removeAttribute('open');
}

function getThinkingIcon(stepType) {
    const icons = {
        'start': '>',
        'round1_start': '1',
        'round2_start': '2',
        'round3_start': '3',
        'generating_queries': 'Q',
        'queries_generated': 'Q',
        'searching': 'S',
        'search_complete': 'S',
        'deduplication': 'D',
        'round1_dedup': 'D',
        'round2_dedup': 'D',
        'round3_dedup': 'D',
        'round1_reranking': 'R',
        'round2_reranking': 'R',
        'round3_reranking': 'R',
        'reranking': 'R',
        'rerank_complete': 'R',
        'round1_score': '#',
        'round2_score': '#',
        'round3_score': '#',
        'round1_success': '+',
        'round2_success': '+',
        'round1_acceptable': '+',
        'round2_final': '!',
        'round1_no_results': 'X',
        'no_results_final': 'X',
        'loading_parents': 'P',
        'complete': '*',
        'no_results': 'X',
        'no_documents': '!',
        'metadata_injection': 'M'
    };
    return icons[stepType] || '-';
}

async function syncFromZotero() {
    try {
        showLoading('Syncing from Zotero...');

        const statusResponse = await fetch(`${API_BASE}/zotero/status`);
        const statusData = await statusResponse.json();

        if (!statusData.enabled) {
            showToast('Zotero not configured', 'error');
            hideLoading();
            return;
        }

        showToast(`Found ${statusData.pdf_attachments} PDFs in Zotero`, 'info');

        const syncResponse = await fetch(`${API_BASE}/zotero/sync/new`, {
            method: 'POST'
        });

        const syncData = await syncResponse.json();

        if (syncData.status === 'started') {
            showToast('Zotero sync started - documents will appear shortly', 'success');

            startDocumentPolling();

            setTimeout(() => {
                loadDocuments(true);
            }, 5000);
        } else {
            showToast(`${syncData.message}`, 'error');
        }

    } catch (error) {
        showToast(`Zotero sync error: ${error.message}`, 'error');
        console.error(error);
    } finally {
        hideLoading();
    }
}

const zoteroSyncBtn = document.createElement('button');
zoteroSyncBtn.id = 'zoteroSyncBtn';
zoteroSyncBtn.className = 'btn-secondary';
zoteroSyncBtn.textContent = '📚 Sync from Zotero';
zoteroSyncBtn.style.marginTop = '8px';
zoteroSyncBtn.addEventListener('click', syncFromZotero);

const sidebarFooter = document.querySelector('.sidebar-footer');
sidebarFooter.appendChild(zoteroSyncBtn);

