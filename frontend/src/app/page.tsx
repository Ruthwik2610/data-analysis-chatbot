"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { flushSync } from "react-dom";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { AuthScreen } from "@/components/AuthScreen";
import { ProjectDialog } from "@/components/ProjectDialog";
import { MessageList } from "@/components/MessageList";
import { InputBar } from "@/components/InputBar";
import { StreamingBar } from "@/components/StreamingBar";
import { SourcePreviewDrawer } from "@/components/SourcePreviewDrawer";
import { useKeyboardShortcuts } from "@/lib/useKeyboardShortcuts";
import { api, clearAuthToken, getAuthToken, streamQuery } from "@/lib/api";
import { displaySourceName } from "@/lib/displayNames";
import { formatArchiveSkippedNote } from "@/lib/uploadMessages";
import type { ChatSummary, Source, SourceMeta, Message, ResultPayload, Pending, Project, ModelMode } from "@/lib/types";

const URL_RE = /\bhttps?:\/\/[^\s,;]+/i;

export default function Home() {
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [chatTitle, setChatTitle] = useState("New chat");
  const [loading, setLoading] = useState(false);
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [projectDialogOpen, setProjectDialogOpen] = useState(false);
  const [modelMode, setModelMode] = useState<ModelMode>("flash");
  const [chatsReady, setChatsReady] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [user, setUser] = useState<{ id: string; email: string } | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const connectorClickRef = useRef<() => void>(() => {});
  const queryAbortRef = useRef<AbortController | null>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);

  const refreshSources = useCallback(async () => {
    if (!user) return;
    try { setSources(await api.listSources(currentProjectId)); } catch {}
  }, [currentProjectId, user]);
  const refreshChats = useCallback(async () => {
    if (!user) return;
    try { setChats(await api.listChats(currentProjectId)); } catch {}
    finally { setChatsReady(true); }
  }, [currentProjectId, user]);
  const refreshProjects = useCallback(async () => {
    if (!user) return;
    try { setProjects(await api.listProjects()); } catch {}
  }, [user]);

  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      setAuthReady(true);
      return;
    }
    api.me()
      .then(({ user }) => setUser(user))
      .catch(() => clearAuthToken())
      .finally(() => setAuthReady(true));
  }, []);

  useEffect(() => { refreshSources(); refreshChats(); refreshProjects(); }, [refreshSources, refreshChats, refreshProjects]);

  useEffect(() => {
    setSelectedSourceIds((prev) => {
      const known = new Set(sources.map((s) => s.id));
      const kept = prev.filter((id) => known.has(id));
      if (kept.length > 0) return kept;
      const fallback = sources.find((s) => s.active) || sources.find((s) => s.kind === "mcp");
      return fallback ? [fallback.id] : [];
    });
  }, [sources]);

  useEffect(() => {
    const handler = () => refreshSources();
    window.addEventListener("data-chat:sources-changed", handler as EventListener);
    return () => window.removeEventListener("data-chat:sources-changed", handler as EventListener);
  }, [refreshSources]);

  const selectedSources = sources.filter((s) => selectedSourceIds.includes(s.id));
  const activeSource = selectedSources[0] || sources.find((s) => s.active);

  const addMessage = useCallback((m: Message) => setMessages((prev) => [...prev, m]), []);
  const updateMessage = useCallback((id: string, patch: Partial<Message>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? ({ ...m, ...patch } as Message) : m)));
  }, []);

  // -------- file pick: upload, show pending question if needed --------
  const handlePickFile = useCallback(
    async (file: File) => {
      const placeholderId = `local_${Date.now()}`;
      const sizeMB = Math.round(file.size / (1024 * 1024));
      const sizeNote = sizeMB > 50 ? ` (${sizeMB} MB — this can take a moment)` : "";
      addMessage({
        id: placeholderId,
        role: "assistant",
        content: "",
        thinking: `Uploading ${displaySourceName(file.name)}${sizeNote}`,
        progress: 0,
      });
      uploadAbortRef.current?.abort();
      uploadAbortRef.current = new AbortController();
      setLoading(true);
      try {
        const res = await api.uploadFile(
          file,
          (pct) => updateMessage(placeholderId, {
            // Drop the progress bar once the bytes are sent — the server still has work to do
            // (parsing/caching), so keep the dot animation alive but stop showing 100%.
            progress: pct < 100 ? pct : null,
            thinking: pct < 100 ? `Uploading ${displaySourceName(file.name)}` : `Reading ${displaySourceName(file.name)} on the server (this can take a minute for large files)`,
          }),
          uploadAbortRef.current.signal,
        );
        updateMessage(placeholderId, { progress: null });
        if ("pending" in res && res.pending) {
          const p = res.pending;
          if (p.kind === "sheet_pick" && p.sheets) {
            updateMessage(placeholderId, {
              thinking: null,
              content: `Got **${displaySourceName(p.file_name)}**. It has ${p.sheets.length} sheets — which one should I read?`,
              pending: {
                resolver: "sheet_pick",
                hint: "Pick a sheet",
                options: p.sheets.map((s) => ({ label: s, value: s })),
                args: { upload_id: p.upload_id },
              },
            });
          } else if (p.kind === "table_pick" && p.tables) {
            updateMessage(placeholderId, {
              thinking: null,
              content: `Got **${displaySourceName(p.file_name)}**. It has ${p.tables.length} tables — which one should I open?`,
              pending: {
                resolver: "table_pick",
                hint: "Pick a table",
                options: p.tables.map((t) => ({ label: t, value: t })),
                args: { upload_id: p.upload_id },
              },
            });
          } else if (p.kind === "ingest_pick") {
            updateMessage(placeholderId, {
              thinking: null,
              content: `**${displaySourceName(p.file_name)}** is ${p.size_mb} MB. How should I load it?`,
              pending: {
                resolver: "ingest_pick",
                hint: "Pick how to load",
                options: [
                  { label: "Query directly (uses RAM)", value: "direct" },
                  { label: "Build a cache (faster later)", value: "sql" },
                ],
                args: { upload_id: p.upload_id },
              },
            });
          }
        } else if (res.sources?.length) {
          const ids = res.sources.map((source) => source.id);
          setSelectedSourceIds((currentIds) => Array.from(new Set([...currentIds, ...ids])));
          const skippedNote = formatArchiveSkippedNote(res.skipped);
          updateMessage(placeholderId, {
            thinking: null,
            progress: null,
            content: `Got **${res.sources.length} PDF${res.sources.length === 1 ? "" : "s"}** from **${displaySourceName(file.name)}**.${skippedNote} Ask me anything about them.`,
          });
          refreshSources();
        } else if ("id" in res && res.id) {
          setSelectedSourceIds((ids) => Array.from(new Set([...ids, res.id as string])));
          const firstClarification = res.clarifications?.[0];
          if (firstClarification) {
            updateMessage(placeholderId, {
              thinking: null,
              progress: null,
              content: `**${displaySourceName(res.name)}** is ready.\n\n${firstClarification.question}`,
              pending: {
                resolver: "source_clarification",
                hint: "Set file meaning",
                options: firstClarification.options,
                args: { source_id: res.id, clarification_id: firstClarification.id, source_name: res.name, rows: res.rows },
              },
            });
          } else {
            updateMessage(placeholderId, {
              thinking: null,
              progress: null,
              content: `**${displaySourceName(res.name)}** is ready. Ask me anything about it.`,
            });
          }
          refreshSources();
        }
      } catch (e: any) {
        if (e?.name === "AbortError") {
          updateMessage(placeholderId, { thinking: null, progress: null, content: `Upload of ${displaySourceName(file.name)} was stopped.` });
        } else {
          updateMessage(placeholderId, {
            thinking: null,
            progress: null,
            content: `Couldn't load ${displaySourceName(file.name)}: ${e?.message || "unknown error"}`,
            error: true,
          });
        }
      } finally {
        setLoading(false);
        uploadAbortRef.current = null;
      }
    },
    [addMessage, updateMessage, refreshSources],
  );

  // -------- pending choice: resolve via backend --------
  const handlePendingChoice = useCallback(
    async (messageId: string, value: string) => {
      const msg = messages.find((m) => m.id === messageId);
      if (!msg || msg.role !== "assistant" || !msg.pending) return;
      const pending = msg.pending;

      if (pending.resolver === "connect_url") {
        if (value === "connect") {
          updateMessage(messageId, { resolved: true, content: `${msg.content}\n\nConnecting…`, thinking: "Connecting" });
          try {
            const src = await api.attachAPI(pending.args.url, null, false);
            setSelectedSourceIds((ids) => Array.from(new Set([...ids, src.id])));
            updateMessage(messageId, {
              thinking: null,
              content: `Connected to **${displaySourceName(src.name)}**. Ask away.`,
            });
            refreshSources();
          } catch (e: any) {
            updateMessage(messageId, { thinking: null, content: `Couldn't connect: ${e?.message || "unknown error"}`, error: true });
          }
        } else {
          updateMessage(messageId, { resolved: true, content: msg.content + "\n\nOK, I'll send it as a question." });
          handleSend(pending.args.original);
        }
        return;
      }

      if (pending.resolver === "source_pick") {
        const sourceMeta = (pending.args.sources as SourceMeta[]).find((s) => s.id === value);
        if (sourceMeta) {
          setSelectedSourceIds([value]);
          await api.activateSource(value).catch(() => {});
          refreshSources();
        }
        updateMessage(messageId, { resolved: true, content: `OK, using **${sourceMeta?.name ?? value}** for this conversation.`, pending: undefined });
        return;
      }

      if (pending.resolver === "clarify_text") {
        updateMessage(messageId, { resolved: true, content: `${msg.content}\n\n${value}` });
        handleSend(`${pending.args.original}\n\nClarification: ${value}`);
        return;
      }

      if (pending.resolver === "source_clarification") {
        updateMessage(messageId, { resolved: true, thinking: "Saving file rules", content: `${msg.content}\n\n${value}` });
        try {
          await api.applySourceClarifications(pending.args.source_id, { [pending.args.clarification_id]: value });
          updateMessage(messageId, {
            thinking: null,
            content: `**${displaySourceName(pending.args.source_name)}** is ready. I saved that file meaning for more accurate answers.`,
          });
          refreshSources();
        } catch (e: any) {
          updateMessage(messageId, { thinking: null, content: `I loaded the file, but couldn't save that rule: ${e?.message || "unknown"}`, error: true });
        }
        return;
      }

      // sheet_pick / table_pick / ingest_pick → resolve_pending
      updateMessage(messageId, { resolved: true, thinking: "Loading", content: msg.content });
      try {
        const src = await api.resolvePending(pending.args.upload_id, value);
        setSelectedSourceIds((ids) => Array.from(new Set([...ids, src.id])));
        const firstClarification = src.clarifications?.[0];
        if (firstClarification) {
          updateMessage(messageId, {
            resolved: false,
            thinking: null,
            content: `**${displaySourceName(src.name)}** is ready.\n\n${firstClarification.question}`,
            pending: {
              resolver: "source_clarification",
              hint: "Set file meaning",
              options: firstClarification.options,
              args: { source_id: src.id, clarification_id: firstClarification.id, source_name: src.name, rows: src.rows },
            },
          });
        } else {
          updateMessage(messageId, {
            thinking: null,
            content: `**${displaySourceName(src.name)}** is ready. Ask me anything about it.`,
          });
        }
        refreshSources();
      } catch (e: any) {
        updateMessage(messageId, { thinking: null, content: `Couldn't finish loading: ${e?.message || "unknown"}`, error: true });
      }
    },
    [messages, updateMessage, refreshSources],
  );

  // -------- send: NL detection, then SSE query --------
  const handleSend = useCallback(
    async (question: string) => {
      const urlMatch = question.match(URL_RE);

      // URL with no active source → propose connect
      if (urlMatch && selectedSourceIds.length === 0) {
        const url = urlMatch[0];
        addMessage({ id: `local_u_${Date.now()}`, role: "user", content: question });
        addMessage({
          id: `local_a_${Date.now() + 1}`,
          role: "assistant",
          content: `Looks like you want to connect to ${url}. Want me to?`,
          pending: {
            resolver: "connect_url",
            hint: "I'll fetch the JSON and use it as a data source.",
            options: [
              { label: "Connect this API", value: "connect" },
              { label: "Just send it as a question", value: "question" },
            ],
            args: { url, original: question },
          },
        });
        return;
      }

      // Plain question — needs an active source
      if (selectedSourceIds.length === 0) {
        addMessage({ id: `local_u_${Date.now()}`, role: "user", content: question });
        addMessage({
          id: `local_a_${Date.now() + 1}`,
          role: "assistant",
          content: "I'll need a source first. Drop a file, paste a URL, or connect an MCP bridge.",
        });
        return;
      }

      // Send as query
      const userMsg: Message = { id: `local_u_${Date.now()}`, role: "user", content: question };
      const assistantId = `local_a_${Date.now() + 1}`;
      const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", streaming: true, thinking: "Thinking" };
      setMessages((m) => [...m, userMsg, assistantMsg]);
      setLoading(true);
      queryAbortRef.current?.abort();
      queryAbortRef.current = new AbortController();

      let fullText = "";
      try {
        for await (const ev of streamQuery({ 
          chat_id: currentChatId, 
          question, 
          source_ids: selectedSourceIds,
          project_id: currentProjectId,
          model_mode: modelMode,
        }, queryAbortRef.current.signal)) {
          // flushSync forces React to commit before the next await — without this,
          // updates inside async iteration get batched until the loop finishes,
          // and the user sees "Thinking…" until the entire stream completes.
          flushSync(() => {
            if (ev.event === "meta") {
              if (ev.data.chat_id !== currentChatId) {
                // If it's a new chat and we have a project selected, link it
                if (!currentChatId && currentProjectId) {
                   api.updateChatProject(ev.data.chat_id, currentProjectId).catch(() => {});
                }
                setCurrentChatId(ev.data.chat_id);
              }
              updateMessage(assistantId, { source: ev.data.source });
            } else if (ev.event === "thinking") {
              updateMessage(assistantId, { thinking: ev.data.step });
            } else if (ev.event === "result") {
              updateMessage(assistantId, { result: ev.data as ResultPayload, thinking: null });
              setLoading(false);
            } else if (ev.event === "text") {
              fullText += ev.data.delta;
              const snapshot = fullText;
              updateMessage(assistantId, { content: snapshot, thinking: null });
            } else if (ev.event === "clarify") {
              updateMessage(assistantId, {
                content: ev.data.content,
                thinking: null,
                pending: {
                  resolver: "clarify_text",
                  hint: "Add the missing detail",
                  options: [
                    { label: "Revenue", value: "Use revenue as the metric" },
                    { label: "Monthly", value: "Group it by month" },
                    { label: "Top 10", value: "Show the top 10 results" },
                  ],
                  args: { original: question },
                },
              });
              setLoading(false);
            } else if (ev.event === "error") {
              updateMessage(assistantId, { content: ev.data.message, error: true, thinking: null });
              setLoading(false);
            } else if (ev.event === "notice") {
              updateMessage(assistantId, { notice: ev.data });
            } else if (ev.event === "done") {
              updateMessage(assistantId, { id: ev.data.message_id || assistantId, streaming: false, thinking: null });
              if (ev.data.chat_id) setCurrentChatId(ev.data.chat_id);
            }
          });
          if (ev.event === "done") refreshChats();
        }
      } catch (e: any) {
        if (e?.name === "AbortError") {
          updateMessage(assistantId, {
            content: fullText ? `${fullText}\n\n_(stopped)_` : "_(stopped)_",
            streaming: false,
            thinking: null,
          });
        } else {
          updateMessage(assistantId, { content: e?.message || "Network error", error: true, streaming: false, thinking: null });
        }
      } finally {
        setLoading(false);
        queryAbortRef.current = null;
      }
    },
    [selectedSourceIds, currentChatId, currentProjectId, modelMode, addMessage, updateMessage, refreshChats],
  );

  const handleStop = useCallback(() => {
    queryAbortRef.current?.abort();
    uploadAbortRef.current?.abort();
  }, []);

  const abortInFlight = useCallback(() => {
    queryAbortRef.current?.abort();
    uploadAbortRef.current?.abort();
    setLoading(false);
  }, []);

  const handleLogout = useCallback(() => {
    abortInFlight();
    clearAuthToken();
    setUser(null);
    setChats([]);
    setSources([]);
    setProjects([]);
    setMessages([]);
    setCurrentChatId(null);
    setCurrentProjectId(null);
    setSelectedSourceIds([]);
    setSidebarOpen(false);
  }, [abortInFlight]);

  const handleNewChat = useCallback(() => {
    abortInFlight();
    setMessages([]);
    setCurrentChatId(null);
    setChatTitle("New chat");
    // If we have a current project, ensure the new chat could be linked to it
    // but usually new chat starts fresh.
  }, [abortInFlight]);

  const handleNewProject = useCallback(async () => {
    const title = prompt("Project Title:");
    if (!title) return;
    try {
      const p = await api.createProject(title);
      refreshProjects();
      abortInFlight();
      setCurrentProjectId(p.id);
      setMessages([]);
      setCurrentChatId(null);
      setChatTitle("New chat");
      setSelectedSourceIds([]);
      setProjectDialogOpen(true);
    } catch {}
  }, [abortInFlight, refreshProjects]);

  const handleSelectProject = useCallback((id: string) => {
    if (currentProjectId === id) {
      setProjectDialogOpen(true);
    } else {
      abortInFlight();
      setCurrentProjectId(id);
      setMessages([]);
      setCurrentChatId(null);
      setChatTitle("New chat");
      setSelectedSourceIds([]);
    }
  }, [abortInFlight, currentProjectId]);

  const handleDeleteProject = useCallback(async (id: string) => {
    if (!confirm("Delete this project? Chats will remain but context links will be removed.")) return;
    try {
      await api.deleteProject(id);
      if (currentProjectId === id) {
        abortInFlight();
        setCurrentProjectId(null);
        setMessages([]);
        setCurrentChatId(null);
        setChatTitle("New chat");
        setSelectedSourceIds([]);
      }
      refreshProjects();
    } catch {}
  }, [abortInFlight, currentProjectId, refreshProjects]);

  const handleSelectChat = useCallback(async (id: string) => {
    abortInFlight();
    try {
      const chat = await api.getChat(id);
      const restored: Message[] = chat.messages.map((m: any) => {
        if (m.role === "user") return { id: m.id, role: "user", content: m.content };
        const isError = m.payload?.kind === "error";
        return {
          id: m.id,
          role: "assistant",
          content: m.content,
          result: m.payload?.result,
          error: isError || undefined,
        };
      });
      setCurrentChatId(id);
      setMessages(restored);
      setChatTitle(chat.title || "Chat");
      setCurrentProjectId(chat.project_id || null);

      // Auto-restore sources used in this chat
      const chatSources: SourceMeta[] = chat.sources || [];
      const chatSourceIds: string[] = chat.source_ids || [];

      if (chatSourceIds.length === 0) {
        // No source info stored (older chat) — leave current selection unchanged
      } else if (chatSourceIds.length === 1) {
        // Single source — activate silently
        setSelectedSourceIds(chatSourceIds);
        await api.activateSource(chatSourceIds[0]).catch(() => {});
        refreshSources();
      } else {
        // Multiple sources — ask the user which one to use
        setSelectedSourceIds(chatSourceIds);
        refreshSources();
        const clarifyId = `local_src_pick_${Date.now()}`;
        const nameList = chatSources.map((s) => s.name).join(", ");
        setMessages((prev) => [
          ...prev,
          {
            id: clarifyId,
            role: "assistant" as const,
            content: `This chat used multiple sources: **${nameList}**. Which one would you like to query next?`,
            pending: {
              resolver: "source_pick" as const,
              hint: "Pick a source",
              options: chatSources.map((s) => ({ label: s.name, value: s.id })),
              args: { sources: chatSources },
            },
          },
        ]);
      }
    } catch {}
  }, [abortInFlight, refreshSources]);

  useEffect(() => {
    if (!user) return;
    const chatId = new URLSearchParams(window.location.search).get("chat_id");
    if (chatId && chatId !== currentChatId) {
      handleSelectChat(chatId);
    }
  }, [user, currentChatId, handleSelectChat]);

  const handleDeleteChat = useCallback(async (id: string) => {
    await api.deleteChat(id);
    if (id === currentChatId) {
      abortInFlight();
      setMessages([]);
      setCurrentChatId(null);
    }
    refreshChats();
  }, [currentChatId, refreshChats, abortInFlight]);

  const handleToggleSource = useCallback(async (id: string) => {
    setSelectedSourceIds((prev) => (
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    ));
    if (id !== "mcp") {
      await api.activateSource(id).catch(() => {});
      refreshSources();
    }
  }, [refreshSources]);

  const handleDeleteSource = useCallback(async (id: string) => {
    await api.deleteSource(id);
    setSelectedSourceIds((prev) => prev.filter((x) => x !== id));
    refreshSources();
  }, [refreshSources]);

  const handleAttachedFromInput = useCallback((s: Source) => {
    setSelectedSourceIds((ids) => Array.from(new Set([...ids, s.id])));
    addMessage({
      id: `local_${Date.now()}`,
      role: "assistant",
      content: `Connected to **${displaySourceName(s.name)}**. Ask away.`,
    });
    refreshSources();
  }, [addMessage, refreshSources]);

  const handleSaveProjectNote = useCallback(async (message: Extract<Message, { role: "assistant" }>) => {
    if (!currentProjectId) return;
    const title = message.result?.title || message.content.split(/\n+/)[0]?.replace(/[#*_`]/g, "").slice(0, 60) || "Saved analysis";
    const content = message.content.trim();
    try {
      await api.createProjectNote(currentProjectId, {
        title,
        content,
        source_message_id: message.id,
      });
      setProjectDialogOpen(true);
    } catch (e: any) {
      addMessage({
        id: `local_${Date.now()}`,
        role: "assistant",
        content: `Couldn't save that note: ${e?.message || "unknown error"}`,
        error: true,
      });
    }
  }, [currentProjectId, addMessage]);

  const handleFeedback = useCallback(async (message: Extract<Message, { role: "assistant" }>, rating: number, category: string) => {
    const comment = category === "bug" ? window.prompt("What went wrong with this answer?") || "" : "";
    try {
      await api.postFeedback({
        chat_id: currentChatId,
        message_id: message.id,
        rating,
        category,
        comment: comment.trim() || undefined,
      });
      addMessage({
        id: `local_feedback_${Date.now()}`,
        role: "assistant",
        content: category === "bug" ? "Reported. I added this to the admin review inbox." : "Feedback saved.",
      });
    } catch (e: any) {
      addMessage({
        id: `local_feedback_err_${Date.now()}`,
        role: "assistant",
        content: `Couldn't save feedback: ${e?.message || "unknown error"}`,
        error: true,
      });
    }
  }, [currentChatId, addMessage]);

  useEffect(() => {
    if (!currentChatId) {
      setChatTitle("New chat");
      return;
    }
    const c = chats.find((x) => x.id === currentChatId);
    if (c) setChatTitle(c.title || "New chat");
  }, [currentChatId, chats]);

  // Greeting card "Connect" button delegates to InputBar's connector flyout
  // by triggering a click on the InputBar's plug button via a ref.
  // For simplicity: the greeting just toggles a state that nudges InputBar.
  // (Cheap workaround: simulate by opening the popover via hash or local storage)
  // Simpler approach: emit a custom event that InputBar listens for.
  useEffect(() => {
    connectorClickRef.current = () => {
      const evt = new CustomEvent("data-chat:open-connector");
      window.dispatchEvent(evt);
    };
  }, []);

  const [previewSourceId, setPreviewSourceId] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const handlePreviewSource = useCallback(async (id: string) => {
    setPreviewSourceId(id);
    setPreviewLoading(true);
    try {
      const data = await api.previewSource(id);
      setPreviewData(data);
    } catch (err) {
      console.error(err);
      setPreviewData(null);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  useKeyboardShortcuts({
    onNewChat: handleNewChat,
    onStop: handleStop,
    loading,
  });

  if (!authReady) {
    return <div className="flex min-h-[100dvh] items-center justify-center text-[13px]" style={{ color: "var(--color-text-tertiary)" }}>Loading workspace...</div>;
  }

  if (!user) {
    return <AuthScreen onAuthenticated={(nextUser) => setUser(nextUser)} />;
  }

  return (
    <div className="flex h-[100dvh] w-screen overflow-hidden relative">
      {sidebarOpen && <button className="fixed inset-0 z-30 bg-black/20 lg:hidden" aria-label="Close sidebar" onClick={() => setSidebarOpen(false)} />}
      <div className={`fixed inset-y-0 left-0 z-40 transition-transform duration-200 lg:static lg:translate-x-0 ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:hidden"}`}>
        <Sidebar
          chats={chats}
          currentChatId={currentChatId}
          sources={sources}
          selectedSourceIds={selectedSourceIds}
          onNewChat={() => { handleNewChat(); }}
          onSelectChat={(id) => { handleSelectChat(id); }}
          onDeleteChat={handleDeleteChat}
          onToggleSource={handleToggleSource}
          onDeleteSource={handleDeleteSource}
          onPreviewSource={handlePreviewSource}
          projects={projects}
          currentProjectId={currentProjectId}
          onSelectProject={(id) => { handleSelectProject(id); }}
          onNewProject={handleNewProject}
          onDeleteProject={handleDeleteProject}
          chatLoading={!chatsReady}
          userEmail={user.email}
          onToggleCollapse={() => setSidebarOpen(false)}
        />
      </div>
      <main className="flex flex-col flex-1 min-w-0 min-h-0 relative" style={{ background: "var(--color-background-primary)" }}>
        <StreamingBar visible={loading} />
        <Topbar  
          title={chatTitle} 
          activeSource={activeSource} 
          selectedSources={selectedSources}
          projectName={projects.find(p => p.id === currentProjectId)?.title}
          userEmail={user.email}
          onLogout={handleLogout}
          onOpenSidebar={() => setSidebarOpen(true)}
          sidebarOpen={sidebarOpen}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <MessageList
          messages={messages}
          loading={loading}
          onPendingChoice={handlePendingChoice}
          onPickFile={handlePickFile}
          onConnectClick={() => connectorClickRef.current()}
          currentProjectId={currentProjectId}
          onSaveProjectNote={handleSaveProjectNote}
          onAskFollowUp={(prompt) => handleSend(prompt)}
          onFeedback={handleFeedback}
        />
        <InputBar
          onSend={handleSend}
          onStop={handleStop}
          onPickFile={handlePickFile}
          onAttached={handleAttachedFromInput}
          loading={loading}
          disabled={false}
          placeholder={selectedSources.length ? "Ask across the selected sources, or paste a URL…" : "Drop a file, paste a URL, or connect an MCP bridge…"}
          currentProjectId={currentProjectId}
          selectedSources={selectedSources}
          modelMode={modelMode}
          onModelModeChange={setModelMode}
        />
      </main>
      {projectDialogOpen && currentProjectId && (
        <ProjectDialog
          projectId={currentProjectId}
          onClose={() => setProjectDialogOpen(false)}
          onUpdate={() => { refreshProjects(); refreshSources(); }}
        />
      )}
      <SourcePreviewDrawer
        open={previewSourceId !== null}
        onClose={() => {
          setPreviewSourceId(null);
          setPreviewData(null);
        }}
        data={previewData}
        loading={previewLoading}
      />
      {settingsOpen && (
        <SettingsPanel
          modelMode={modelMode}
          onModelModeChange={setModelMode}
          onClose={() => setSettingsOpen(false)}
          onClearChat={handleNewChat}
        />
      )}
    </div>
  );
}

function SettingsPanel({
  modelMode,
  onModelModeChange,
  onClose,
  onClearChat,
}: {
  modelMode: ModelMode;
  onModelModeChange: (mode: ModelMode) => void;
  onClose: () => void;
  onClearChat: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 px-4" role="dialog" aria-modal="true" aria-label="Workspace settings">
      <div className="w-full max-w-md rounded-[18px] p-5 glass shadow-2xl" style={{ background: "var(--color-background-elevated)" }}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold" style={{ color: "var(--color-text-primary)" }}>Settings</h2>
          <button type="button" onClick={onClose} className="rounded-[8px] px-2 py-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>Close</button>
        </div>
        <div className="mt-5 flex flex-col gap-4">
          <label className="flex items-center justify-between gap-4 text-sm" style={{ color: "var(--color-text-secondary)" }}>
            Default query model
            <select
              aria-label="Default query model"
              value={modelMode}
              onChange={(e) => onModelModeChange(e.target.value as ModelMode)}
              className="rounded-[10px] px-3 py-2"
              style={{ background: "var(--color-background-secondary)", color: "var(--color-text-primary)", border: "1px solid var(--color-border-secondary)" }}
            >
              <option value="flash">Flash</option>
              <option value="pro">Pro</option>
            </select>
          </label>
          <button type="button" onClick={() => { onClearChat(); onClose(); }} className="rounded-[10px] px-3 py-2 text-left text-sm" style={{ border: "1px solid var(--color-border-secondary)", color: "var(--color-text-primary)" }}>
            Clear current screen
          </button>
          <a href="/admin/feedback" className="rounded-[10px] px-3 py-2 text-sm" style={{ border: "1px solid var(--color-border-secondary)", color: "var(--color-text-primary)" }}>
            Open feedback inbox
          </a>
        </div>
      </div>
    </div>
  );
}
