"use client";

import { useState, useEffect } from "react";
import { X, Plus, Trash2, FileText, Database, Server, Save, StickyNote, Wand2 } from "lucide-react";
import { api } from "@/lib/api";
import type { MCPConnector, Project, ProjectNote, Source } from "@/lib/types";
import { displaySourceName } from "@/lib/displayNames";

interface ProjectDialogProps {
  projectId: string;
  onClose: () => void;
  onUpdate: () => void;
}

export function ProjectDialog({ projectId, onClose, onUpdate }: ProjectDialogProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [mcpConnectors, setMcpConnectors] = useState<MCPConnector[]>([]);
  const [notes, setNotes] = useState<ProjectNote[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [selectedMcpId, setSelectedMcpId] = useState("");
  const [projectCategory, setProjectCategory] = useState("general");
  const [projectRules, setProjectRules] = useState("");
  const [savingRules, setSavingRules] = useState(false);
  const [selectedInstructionSourceId, setSelectedInstructionSourceId] = useState("");
  const [sourceRowGrain, setSourceRowGrain] = useState("row");
  const [sourceRules, setSourceRules] = useState("");
  const [loading, setLoading] = useState(true);
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);
  const [confirmFileId, setConfirmFileId] = useState<string | null>(null);
  const projectFileLabel = (file: Project["files"][number]) => {
    if (file.source_id) return displaySourceName(file.source_name || `Source: ${file.source_id}`);
    return displaySourceName(file.file_path?.split("/").pop() || "Unknown File");
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [projData, sourcesData, mcpData, noteData, projectInstructions] = await Promise.all([
        api.getProject(projectId),
        api.listSources(projectId),
        api.listMCPConnectors(),
        api.listProjectNotes(projectId),
        api.getProjectInstructions(projectId),
      ]);
      setProject(projData);
      setTitleDraft(projData.title);
      setSources(sourcesData);
      setMcpConnectors(mcpData);
      setNotes(noteData);
      setProjectCategory(projectInstructions.instructions.category || "general");
      setProjectRules(projectInstructions.instructions.notes || "");
    } catch (err) {
      console.error("Failed to load project data", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);


  const handleRenameProject = async () => {
    const nextTitle = titleDraft.trim();
    if (!nextTitle || nextTitle === project?.title) return;
    setSavingTitle(true);
    try {
      const updated = await api.updateProject(projectId, { title: nextTitle });
      setProject(updated);
      setTitleDraft(updated.title);
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to rename project");
    } finally {
      setSavingTitle(false);
    }
  };

  const handleTransferSource = async () => {
    if (!selectedSourceId) return;
    try {
      await api.addProjectFile(projectId, undefined, undefined, selectedSourceId);
      setSelectedSourceId("");
      loadData();
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to transfer source");
    }
  };

  const handleRemoveFile = async (fileId: string) => {
    try {
      await api.removeProjectFile(projectId, fileId);
      loadData();
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to remove file");
    }
  };

  const handleBindMCP = async () => {
    if (!selectedMcpId) return;
    try {
      await api.bindProjectMCP(projectId, selectedMcpId);
      setSelectedMcpId("");
      await loadData();
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to add database context");
    }
  };

  const handleUnbindMCP = async (connectorId: string) => {
    try {
      await api.unbindProjectMCP(projectId, connectorId);
      await loadData();
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to remove database context");
    }
  };

  const handleDeleteNote = async (noteId: string) => {
    try {
      await api.deleteProjectNote(projectId, noteId);
      await loadData();
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to delete note");
    }
  };

  const handleSaveProjectRules = async () => {
    setSavingRules(true);
    try {
      await api.updateProjectInstructions(projectId, {
        category: projectCategory,
        notes: projectRules,
      });
      await api.rebuildProjectProfile(projectId);
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to save project instructions");
    } finally {
      setSavingRules(false);
    }
  };

  const loadSourceInstructions = async (sourceId: string) => {
    setSelectedInstructionSourceId(sourceId);
    if (!sourceId) {
      setSourceRowGrain("row");
      setSourceRules("");
      return;
    }
    try {
      const response = await api.getSourceInstructions(sourceId);
      setSourceRowGrain(response.instructions.row_grain || "row");
      setSourceRules(response.instructions.notes || "");
    } catch (err: any) {
      alert(err.message || "Failed to load file instructions");
    }
  };

  const handleSaveSourceRules = async () => {
    if (!selectedInstructionSourceId) return;
    try {
      const current = await api.getSourceInstructions(selectedInstructionSourceId);
      await api.updateSourceInstructions(selectedInstructionSourceId, {
        ...current.instructions,
        row_grain: sourceRowGrain,
        notes: sourceRules,
      });
      onUpdate();
    } catch (err: any) {
      alert(err.message || "Failed to save file instructions");
    }
  };

  const linkedMCPs = mcpConnectors.filter((c) => c.project_ids?.includes(projectId));
  const availableMCPs = mcpConnectors.filter((c) => !c.project_ids?.includes(projectId));

  if (!project && loading) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-[4px] animate-in fade-in duration-300">
      <div className="w-full max-w-lg flex flex-col max-h-[90vh] overflow-hidden glass rounded-[32px] shadow-2xl border border-secondary">
        <div className="flex items-center justify-between p-6 border-b border-tertiary">
          <div className="min-w-0 flex-1 pr-3">
            <h2 className="text-xl font-bold text-primary truncate">
              Project Context
            </h2>
            <p className="text-[10px] text-tertiary font-bold uppercase tracking-widest mt-1">
              Refine instructions and data sources
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-secondary rounded-full transition-colors text-secondary hover:text-primary">
            <X size={20} />
          </button>
        </div>

        <div className="p-6 overflow-y-auto flex-1 space-y-8 custom-scrollbar">
          {/* Project Name */}
          <div className="flex flex-col gap-3">
            <label htmlFor="project-name" className="text-[10px] font-bold text-blue-500 uppercase tracking-[0.2em] px-1">
              Project Identifier
            </label>
            <div className="flex gap-2">
              <input
                id="project-name"
                aria-label="Project name"
                value={titleDraft}
                onChange={(e) => setTitleDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleRenameProject();
                  }
                }}
                className="flex-1 px-4 py-2.5 text-sm bg-secondary border border-secondary rounded-xl text-primary focus:outline-none focus:border-blue-500/50 transition-all placeholder:text-tertiary"
                placeholder="Enter project title..."
              />
              <button
                onClick={handleRenameProject}
                disabled={savingTitle || !titleDraft.trim() || titleDraft.trim() === project?.title}
                aria-label="Save project name"
                className="px-4 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-blue-700 disabled:opacity-30 transition-all shadow-lg shadow-blue-500/10"
              >
                {savingTitle ? "Saving" : "Save"}
              </button>
            </div>
          </div>

          {/* Project Instructions */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between px-1">
              <h3 className="text-[10px] font-bold text-blue-500 uppercase tracking-[0.2em]">
                Strategic Directives
              </h3>
              <button
                onClick={handleSaveProjectRules}
                disabled={savingRules}
                aria-label="Save rules"
                className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-30"
              >
                <Wand2 size={12} />
                {savingRules ? "Syncing..." : "Update Rules"}
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3">
              <select
                aria-label="Project category"
                value={projectCategory}
                onChange={(e) => setProjectCategory(e.target.value)}
                className="w-full px-4 py-2.5 text-xs bg-secondary border border-secondary rounded-xl text-primary outline-none focus:border-blue-500/50 appearance-none font-bold tracking-wider"
              >
                <option value="general" className="bg-secondary">General Dataset</option>
                <option value="sales" className="bg-secondary">Sales Intelligence</option>
                <option value="finance" className="bg-secondary">Financial Reporting</option>
                <option value="inventory" className="bg-secondary">Inventory Tracking</option>
                <option value="operations" className="bg-secondary">Operational Ops</option>
                <option value="customer_support" className="bg-secondary">Customer Success</option>
              </select>
              <textarea
                aria-label="Project rules"
                value={projectRules}
                onChange={(e) => setProjectRules(e.target.value)}
                placeholder="Shared rules for this project context..."
                className="min-h-[100px] resize-none px-4 py-3 text-sm bg-secondary border border-secondary rounded-2xl text-primary focus:outline-none focus:border-blue-500/50 transition-all placeholder:text-tertiary leading-relaxed"
              />
            </div>
          </div>

          {/* Linked Context */}
          <div className="flex flex-col gap-4">
            <h3 className="text-[10px] font-bold text-blue-500 uppercase tracking-[0.2em] px-1">
              Active Knowledge Assets
            </h3>
            <div className="flex flex-col gap-2">
                {project?.files.length === 0 && linkedMCPs.length === 0 ? (
                <div className="py-8 rounded-2xl border border-dashed border-tertiary flex items-center justify-center">
                    <p className="text-[10px] text-tertiary font-bold uppercase tracking-widest">No assets connected</p>
                </div>
                ) : (
                <>
                    {project?.files.map((file) => (
                    <div key={file.id} className="flex items-center justify-between p-4 bg-secondary rounded-2xl border border-tertiary group hover:bg-tertiary transition-all">
                        <div className="flex items-center gap-4 min-w-0">
                            <div className="p-2.5 bg-blue-500/10 rounded-xl text-blue-400">
                                {file.source_id ? <Database size={16} /> : <FileText size={16} />}
                            </div>
                            <div className="min-w-0 flex flex-col">
                                <p className="text-sm font-medium text-primary truncate" title={projectFileLabel(file)}>
                                    {projectFileLabel(file)}
                                </p>
                                {file.source_id && <span className="text-[9px] font-bold uppercase tracking-widest text-blue-500/60 mt-0.5">KB Reference</span>}
                            </div>
                        </div>
                        <button
                            onClick={() => setConfirmFileId(file.id)}
                            className="p-2 text-tertiary hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        >
                            <Trash2 size={14} />
                        </button>
                        {confirmFileId === file.id && (
                            <div className="absolute right-6 z-30 w-[200px] rounded-2xl glass p-4 text-xs shadow-2xl border-red-500/20">
                            <div className="font-bold text-primary uppercase tracking-wider mb-1">Remove Asset?</div>
                            <div className="text-secondary mb-3">Remove from project context.</div>
                            <div className="flex justify-end gap-2">
                                <button className="px-2 py-1 rounded-lg text-tertiary hover:text-primary" onClick={() => setConfirmFileId(null)}>Cancel</button>
                                <button className="bg-red-500/10 text-red-500 px-3 py-1 rounded-lg font-bold hover:bg-red-500 hover:text-white" onClick={() => { setConfirmFileId(null); handleRemoveFile(file.id); }}>Remove</button>
                            </div>
                            </div>
                        )}
                    </div>
                    ))}
                    {linkedMCPs.map((connector) => (
                    <div key={connector.id} className="flex items-center justify-between p-4 bg-emerald-500/5 rounded-2xl border border-emerald-500/10 group hover:bg-emerald-500/10 transition-all">
                        <div className="flex items-center gap-4 min-w-0">
                            <div className="p-2.5 bg-emerald-500/10 rounded-xl text-emerald-400">
                                <Server size={16} />
                            </div>
                            <div className="min-w-0 flex flex-col">
                                <p className="text-sm font-medium text-primary truncate">{connector.name}</p>
                                <span className="text-[9px] font-bold uppercase tracking-widest text-emerald-500/60 mt-0.5">Live Database</span>
                                {connector.description && <p className="text-[11px] text-secondary mt-1 line-clamp-1">{connector.description}</p>}
                            </div>
                        </div>
                        <button
                            onClick={() => handleUnbindMCP(connector.id)}
                            className="p-2 text-tertiary hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                        >
                            <Trash2 size={14} />
                        </button>
                    </div>
                    ))}
                </>
                )}
            </div>
          </div>

          {/* Per-file instructions */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between px-1">
              <h3 className="text-[10px] font-bold text-blue-500 uppercase tracking-[0.2em]">
                Local overrides
              </h3>
              <button
                onClick={handleSaveSourceRules}
                disabled={!selectedInstructionSourceId}
                aria-label="Save file rules"
                className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-30"
              >
                <Save size={12} />
                Save file rules
              </button>
            </div>
            <div className="grid grid-cols-1 gap-3">
              <select
                aria-label="Instruction source"
                value={selectedInstructionSourceId}
                onChange={(e) => loadSourceInstructions(e.target.value)}
                className="w-full px-4 py-2.5 text-xs bg-secondary border border-secondary rounded-xl text-primary outline-none focus:border-blue-500/50 appearance-none font-bold tracking-wider"
              >
                <option value="" className="bg-secondary">Select file to override...</option>
                {project?.files.map((file) => (
                  <option key={file.id} value={file.source_id || ""} className="bg-secondary">
                    {projectFileLabel(file)}
                  </option>
                ))}
              </select>
              <div className="flex gap-2">
                <select
                    aria-label="Row grain"
                    value={sourceRowGrain}
                    onChange={(e) => setSourceRowGrain(e.target.value)}
                    className="flex-1 px-4 py-2 text-xs bg-secondary border border-secondary rounded-xl text-primary outline-none focus:border-blue-500/50 appearance-none font-bold tracking-wider"
                >
                    <option value="row" className="bg-secondary">Each row is a record</option>
                    <option value="line_item" className="bg-secondary">Each row is a line item</option>
                    <option value="transaction" className="bg-secondary">Each row is a transaction</option>
                </select>
              </div>
              <textarea
                aria-label="File rules"
                value={sourceRules}
                onChange={(e) => setSourceRules(e.target.value)}
                placeholder="Specific rules for this file (e.g. 'quantity' column means count)..."
                className="min-h-[80px] resize-none px-4 py-3 text-sm bg-secondary border border-secondary rounded-2xl text-primary focus:outline-none focus:border-blue-500/50 transition-all placeholder:text-tertiary leading-relaxed"
              />
            </div>
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 gap-4 pt-4 border-t border-tertiary">
                <div className="flex flex-col gap-2">
                    <h3 className="text-[10px] font-bold text-tertiary uppercase tracking-[0.2em] px-1">Import from Knowledge Base</h3>
                    <div className="flex gap-2">
                        <select
                            value={selectedSourceId}
                            onChange={(e) => setSelectedSourceId(e.target.value)}
                            className="flex-1 px-4 py-2 text-xs bg-secondary border border-secondary rounded-xl text-primary outline-none focus:border-blue-500/50 appearance-none font-bold tracking-wider"
                        >
                            <option value="" className="bg-secondary">Select source...</option>
                            {sources.filter(s => !project?.files.some(f => f.source_id === s.id)).map(s => (
                            <option key={s.id} value={s.id} className="bg-secondary">
                                {displaySourceName(s.name)}
                            </option>
                            ))}
                        </select>
                        <button
                            onClick={handleTransferSource}
                            disabled={!selectedSourceId}
                            className="px-4 py-2 bg-blue-600 text-white rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-blue-700 disabled:opacity-30 transition-all"
                        >
                            <Plus size={14} />
                        </button>
                    </div>
                </div>

                <div className="flex flex-col gap-2">
                    <h3 className="text-[10px] font-bold text-tertiary uppercase tracking-[0.2em] px-1">Attach Database Context</h3>
                    <div className="flex gap-2">
                        <select
                            aria-label="Add database context"
                            value={selectedMcpId}
                            onChange={(e) => setSelectedMcpId(e.target.value)}
                            className="flex-1 px-4 py-2 text-xs bg-secondary border border-secondary rounded-xl text-primary outline-none focus:border-blue-500/50 appearance-none font-bold tracking-wider"
                        >
                            <option value="" className="bg-secondary">Select database...</option>
                            {availableMCPs.map((connector) => (
                            <option key={connector.id} value={connector.id} className="bg-secondary">
                                {connector.name}
                            </option>
                            ))}
                        </select>
                        <button
                            onClick={handleBindMCP}
                            disabled={!selectedMcpId}
                            aria-label="Add database"
                            className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-30 transition-all"
                        >
                            <Plus size={14} />
                        </button>
                    </div>
                </div>
          </div>

          {/* Saved Notes (Compact) */}
          {notes.length > 0 && (
            <div className="flex flex-col gap-4">
                <h3 className="text-[10px] font-bold text-amber-500/60 uppercase tracking-[0.2em] px-1">Contextual Artifacts</h3>
                <div className="flex flex-col gap-2">
                    {notes.map((note) => (
                        <div key={note.id} className="p-4 bg-secondary rounded-2xl border border-tertiary group hover:bg-tertiary transition-all flex items-start justify-between gap-4">
                            <div className="min-w-0 flex flex-col gap-1">
                                <p className="text-sm font-bold text-primary truncate">{note.title}</p>
                                <p className="text-[11px] text-secondary line-clamp-2 leading-relaxed">{note.content}</p>
                            </div>
                            <button
                                onClick={() => handleDeleteNote(note.id)}
                                className="p-2 text-tertiary hover:text-red-400 transition-all opacity-0 group-hover:opacity-100"
                            >
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            </div>
          )}
        </div>

        <div className="p-6 bg-secondary border-t border-tertiary flex justify-end">
          <button
            onClick={onClose}
            className="px-8 py-2.5 bg-tertiary hover:bg-secondary text-primary rounded-xl text-[10px] font-bold uppercase tracking-[0.2em] transition-all"
          >
            Finalize Context
          </button>
        </div>
      </div>
      
      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: var(--color-border-secondary);
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
}
