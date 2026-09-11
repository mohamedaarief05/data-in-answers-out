/**
 * Chat Manager: Handles Chat Interaction, Rendering Messages,
 * Grounded Status Indicators, Cypher Inspection, and Database Results.
 */

class ChatManager {
  constructor({ apiService, getActiveDatasetId }) {
    this.apiService = apiService;
    this.getActiveDatasetId = getActiveDatasetId;
    this.isProcessing = false;

    this.cacheDOMElements();
    this.bindEvents();
  }

  cacheDOMElements() {
    this.messagesContainer = document.getElementById('chat-messages');
    this.chatInput = document.getElementById('chat-input');
    this.sendBtn = document.getElementById('send-btn');
    this.clearChatBtn = document.getElementById('clear-chat-btn');
    this.welcomeState = document.getElementById('chat-welcome');
  }

  bindEvents() {
    this.sendBtn.addEventListener('click', () => {
      this.sendMessage();
    });

    this.chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    this.clearChatBtn.addEventListener('click', () => {
      this.clearConversation();
    });

    // Delegate suggestion chip clicks
    document.querySelectorAll('.chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const text = btn.getAttribute('data-query') || btn.textContent.trim();
        this.chatInput.value = text;
        this.sendMessage();
      });
    });
  }

  async sendMessage() {
    const question = this.chatInput.value.trim();
    if (!question || this.isProcessing) return;

    // Hide welcome state
    if (this.welcomeState) {
      this.welcomeState.style.display = 'none';
    }

    // 1. Render User Message
    this.appendUserMessage(question);
    this.chatInput.value = '';
    this.setProcessing(true);

    // 2. Render Temporary Typing Skeleton
    const typingIndicator = this.appendTypingIndicator();

    try {
      const datasetId = this.getActiveDatasetId ? this.getActiveDatasetId() : null;
      const response = await this.apiService.askQuestion(question, datasetId);

      // Remove typing indicator and render Assistant Message
      typingIndicator.remove();
      this.appendAssistantMessage(response);
    } catch (err) {
      typingIndicator.remove();
      this.appendAssistantMessage({
        answer: `Error connecting to chatbot service: ${err.message}`,
        grounded: false,
      });
    } finally {
      this.setProcessing(false);
      this.scrollToBottom();
    }
  }

  appendUserMessage(text) {
    const row = document.createElement('div');
    row.className = 'chat-row user-row';

    const avatar = document.createElement('div');
    avatar.className = 'chat-avatar user-avatar';
    avatar.textContent = 'U';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;

    row.appendChild(avatar);
    row.appendChild(bubble);
    this.messagesContainer.appendChild(row);
    this.scrollToBottom();
  }

  appendAssistantMessage(data) {
    const row = document.createElement('div');
    row.className = 'chat-row assistant-row';

    const avatar = document.createElement('div');
    avatar.className = 'chat-avatar bot-avatar';
    avatar.textContent = 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // 1. Grounded Indicator Badge
    const badge = document.createElement('div');
    badge.className = `grounded-badge ${data.grounded ? 'grounded-true' : 'grounded-false'}`;
    badge.innerHTML = data.grounded
      ? `<span>●</span> Grounded in Neo4j`
      : `<span>▲</span> Ungrounded / Not in Data`;
    bubble.appendChild(badge);

    // 2. Answer text
    const textEl = document.createElement('div');
    textEl.style.fontSize = '0.95rem';
    textEl.textContent = data.answer || "I don't have that in the data.";
    bubble.appendChild(textEl);

    // 3. Cypher Query Block (if present)
    if (data.cypher && window.ResultRenderer) {
      const cypherEl = window.ResultRenderer.createCypherBlock(data.cypher);
      bubble.appendChild(cypherEl);
    }

    // 4. Result Visualizer (if present)
    if (data.result !== undefined && data.result !== null && window.ResultRenderer) {
      const resultEl = window.ResultRenderer.createResultVisualizer(data.result);
      if (resultEl) {
        bubble.appendChild(resultEl);
      }
    }

    row.appendChild(avatar);
    row.appendChild(bubble);
    this.messagesContainer.appendChild(row);
    this.scrollToBottom();
  }

  appendTypingIndicator() {
    const row = document.createElement('div');
    row.className = 'chat-row assistant-row';

    const avatar = document.createElement('div');
    avatar.className = 'chat-avatar bot-avatar';
    avatar.textContent = 'AI';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    const typing = document.createElement('div');
    typing.className = 'typing-indicator';
    typing.innerHTML = `
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
      <div class="typing-dot"></div>
    `;

    bubble.appendChild(typing);
    row.appendChild(avatar);
    row.appendChild(bubble);
    this.messagesContainer.appendChild(row);
    this.scrollToBottom();
    return row;
  }

  clearConversation() {
    this.messagesContainer.innerHTML = '';
    if (this.welcomeState) {
      this.messagesContainer.appendChild(this.welcomeState);
      this.welcomeState.style.display = 'flex';
    }
  }

  setProcessing(isBusy) {
    this.isProcessing = isBusy;
    this.sendBtn.disabled = isBusy;
    this.chatInput.disabled = isBusy;
    if (isBusy) {
      this.sendBtn.textContent = '...';
    } else {
      this.sendBtn.textContent = 'Send';
      this.chatInput.focus();
    }
  }

  scrollToBottom() {
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ChatManager };
} else {
  window.ChatManager = ChatManager;
}
