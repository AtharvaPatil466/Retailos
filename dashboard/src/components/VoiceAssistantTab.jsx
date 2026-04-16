import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Send, Volume2, VolumeX, Trash2, Bot, User, Loader2, Navigation } from 'lucide-react';
import { authHeaders } from '../api';

const API_BASE = '';

export default function VoiceAssistantTab() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Namaste! I\'m your RetailOS assistant. Ask me anything about your store — inventory, sales, suppliers, or just say "How\'s my store doing today?" You can type or use the mic button to speak.',
      timestamp: Date.now(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [conversationId, setConversationId] = useState('');
  const [language, setLanguage] = useState('en');
  const [status, setStatus] = useState(null);

  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const synthRef = useRef(window.speechSynthesis);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Fetch assistant status
  useEffect(() => {
    fetch(`${API_BASE}/api/assistant/status`, { headers: authHeaders() })
      .then((r) => r.json())
      .then(setStatus)
      .catch(() => {});
  }, []);

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = language === 'hi' ? 'hi-IN' : 'en-IN';

    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((r) => r[0].transcript)
        .join('');
      setInput(transcript);

      // Auto-send on final result
      if (event.results[event.results.length - 1].isFinal) {
        setIsListening(false);
        if (transcript.trim()) {
          sendMessage(transcript.trim());
        }
      }
    };

    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;

    return () => {
      recognition.abort();
    };
  }, [language]);

  const toggleListening = useCallback(() => {
    if (!recognitionRef.current) return;

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      recognitionRef.current.lang = language === 'hi' ? 'hi-IN' : 'en-IN';
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch {
        // Already started
      }
    }
  }, [isListening, language]);

  const speak = useCallback((text) => {
    if (!ttsEnabled || !synthRef.current) return;

    synthRef.current.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language === 'hi' ? 'hi-IN' : 'en-IN';
    utterance.rate = 0.95;
    utterance.onstart = () => setIsSpeaking(true);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    synthRef.current.speak(utterance);
  }, [ttsEnabled, language]);

  const sendMessage = useCallback(async (text) => {
    if (!text?.trim() || isLoading) return;

    const userMsg = { role: 'user', content: text.trim(), timestamp: Date.now() };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      const res = await fetch(`${API_BASE}/api/assistant/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
        body: JSON.stringify({
          text: text.trim(),
          language,
          conversation_id: conversationId,
        }),
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Sorry, I could not reach the assistant right now.');
      }

      const assistantMsg = {
        role: 'assistant',
        content: data.response || data.detail || 'Sorry, I could not process that.',
        actions: data.actions || [],
        mode: data.mode,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }

      // Speak the response
      speak(data.response || '');
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: err?.message || 'Sorry, I\'m having trouble connecting. Please try again.',
          timestamp: Date.now(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, language, conversationId, speak]);

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const clearChat = () => {
    setMessages([
      {
        role: 'assistant',
        content: 'Chat cleared. How can I help you?',
        timestamp: Date.now(),
      },
    ]);
    setConversationId('');
  };

  const handleAction = (action) => {
    if (action.type === 'navigate' && action.target) {
      window.dispatchEvent(new CustomEvent('retailos:navigate', { detail: { tab: action.target } }));
    }
  };

  const quickPrompts = [
    { label: "Today's summary", text: "How's my store doing today?" },
    { label: 'Low stock', text: 'Which items are running low?' },
    { label: 'Best supplier', text: 'Who is my most reliable supplier?' },
    { label: 'Pending approvals', text: 'Do I have any pending approvals?' },
    { label: 'Udhaar status', text: 'How much credit is outstanding?' },
    { label: 'Top products', text: 'What are my top selling products today?' },
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-260px)] max-h-[800px]">
      {/* Header */}
      <div className="flex items-center justify-between rounded-t-[20px] border border-b-0 border-black/5 bg-gradient-to-r from-teal-50 to-amber-50 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-600 to-teal-800 text-white">
            <Bot size={20} />
          </div>
          <div>
            <h3 className="font-display text-lg font-bold text-stone-900">Store Assistant</h3>
            <p className="text-xs text-stone-500">
              {status?.mode === 'gemini' ? 'AI-powered' : 'Basic mode'} &middot; {language === 'hi' ? 'Hindi' : 'English'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setLanguage(language === 'en' ? 'hi' : 'en')}
            className="rounded-full border border-black/5 bg-white px-3 py-1.5 text-xs font-semibold text-stone-600 hover:bg-stone-50"
          >
            {language === 'en' ? 'EN' : 'HI'}
          </button>
          <button
            onClick={() => { setTtsEnabled(!ttsEnabled); synthRef.current?.cancel(); }}
            className={`rounded-full border border-black/5 p-2 ${ttsEnabled ? 'bg-white text-stone-600' : 'bg-stone-200 text-stone-400'}`}
            title={ttsEnabled ? 'Mute voice' : 'Enable voice'}
          >
            {ttsEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </button>
          <button
            onClick={clearChat}
            className="rounded-full border border-black/5 bg-white p-2 text-stone-400 hover:text-red-500"
            title="Clear chat"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto border-x border-black/5 bg-white/40 px-4 py-4 space-y-4">
        {/* Quick prompts */}
        {messages.length <= 1 && (
          <div className="flex flex-wrap gap-2 pb-2">
            {quickPrompts.map((p) => (
              <button
                key={p.text}
                onClick={() => sendMessage(p.text)}
                className="rounded-full border border-black/5 bg-white px-3 py-1.5 text-xs font-medium text-stone-600 shadow-sm hover:bg-stone-50 hover:shadow transition-all"
              >
                {p.label}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-teal-100 text-teal-700">
                <Bot size={14} />
              </div>
            )}
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-stone-900 text-white'
                  : 'border border-black/5 bg-white text-stone-800 shadow-sm'
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.actions?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {msg.actions.map((a, j) => (
                    <button
                      key={j}
                      onClick={() => handleAction(a)}
                      className="flex items-center gap-1 rounded-full bg-teal-50 px-2.5 py-1 text-xs font-medium text-teal-700 hover:bg-teal-100 transition-colors"
                    >
                      <Navigation size={10} />
                      {a.label}
                    </button>
                  ))}
                </div>
              )}
              {msg.mode === 'fallback' && msg.role === 'assistant' && (
                <p className="mt-1 text-[10px] text-stone-400">Basic mode — configure GEMINI_API_KEY for AI responses</p>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-stone-200 text-stone-600">
                <User size={14} />
              </div>
            )}
          </div>
        ))}

        {isLoading && (
          <div className="flex gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-teal-100 text-teal-700">
              <Bot size={14} />
            </div>
            <div className="flex items-center gap-2 rounded-2xl border border-black/5 bg-white px-4 py-3 shadow-sm">
              <Loader2 size={14} className="animate-spin text-teal-600" />
              <span className="text-sm text-stone-400">Thinking...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form
        onSubmit={handleSubmit}
        className="flex items-center gap-2 rounded-b-[20px] border border-t-0 border-black/5 bg-white px-4 py-3"
      >
        <button
          type="button"
          onClick={toggleListening}
          className={`flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full transition-all ${
            isListening
              ? 'bg-red-500 text-white shadow-lg shadow-red-200 animate-pulse'
              : 'bg-stone-100 text-stone-500 hover:bg-stone-200'
          }`}
          title={isListening ? 'Stop listening' : 'Start voice input'}
        >
          {isListening ? <MicOff size={18} /> : <Mic size={18} />}
        </button>

        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={isListening ? 'Listening...' : language === 'hi' ? 'कुछ भी पूछें...' : 'Ask anything about your store...'}
          className="flex-1 rounded-full border border-black/5 bg-stone-50 px-4 py-2.5 text-sm text-stone-900 placeholder:text-stone-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-teal-500/20"
          disabled={isLoading}
        />

        <button
          type="submit"
          disabled={!input.trim() || isLoading}
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-teal-700 text-white transition-all hover:bg-teal-800 disabled:opacity-30"
        >
          <Send size={16} />
        </button>
      </form>

      {/* Speaking indicator */}
      {isSpeaking && (
        <div className="mt-2 flex items-center justify-center gap-2 text-xs text-teal-600">
          <Volume2 size={12} className="animate-pulse" />
          Speaking...
        </div>
      )}
    </div>
  );
}
