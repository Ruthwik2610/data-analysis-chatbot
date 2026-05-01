"use client";

import { useState, useEffect } from "react";
import { X, Plus, Trash2, FileText, Database, Server, Save } from "lucide-react";
import { api } from "@/lib/api";
import type { MCPConnector, Project, Source } from "@/lib/types";

interface ProjectDialogProps {
  projectId: string;
  onClose: () => void;
  onUpdate: () => void;
}

export function ProjectDialog({ projectId, onClose, onUpdate }: ProjectDialogProps) {
  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [mcpConnectors, setMcpConnectors] = useState<MCPConnector[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [selectedMcpId, setSelectedMcpId] = useState("");
  const [loading, setLoading] = useState(true);
  const [titleDraft, setTitleDraft] = useState("");
  const [savingTitle, setSavingTitle] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [projData, sourcesData, mcpData] = await Promise.all([
        api.getProject(projectId),
        api.listSources(projectId),
        api.listMCPConnectors(),
      ]);
      setProject(projData);
      setTitleDraft(projData.title);
      setSources(sourcesData);
      setMcpConnectors(mcpData);
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

  const linkedMCPs = mcpConnectors.filter((c) => c.project_ids?.includes(projectId));
  const availableMCPs = mcpConnectors.filter((c) => !c.project_ids?.includes(projectId));

  if (!project && loading) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md flex flex-col max-h-[85vh] overflow-hidden border border-gray-200">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <div className="min-w-0 flex-1 pr-3">
            <h2 className="text-lg font-semibold text-gray-800 truncate">
              Project sandbox
            </h2>
            <p className="text-xs text-gray-500 truncate">
              Ask inside this saved context, then come back to add or remove sources.
            </p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded-lg transition-colors">
            <X size={20} className="text-gray-500" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto flex-1 space-y-6">
          <div>
            <label htmlFor="project-name" className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2 block">
              Project name
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
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all"
              />
              <button
                onClick={handleRenameProject}
                disabled={savingTitle || !titleDraft.trim() || titleDraft.trim() === project?.title}
                className="px-3 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-all flex items-center gap-2"
                aria-label="Save project name"
                title="Save project name"
              >
                <Save size={15} />
                <span className="hidden sm:inline">{savingTitle ? "Saving" : "Save"}</span>
              </button>
            </div>
          </div>

          <div>
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
              Linked Context
            </h3>
            {project?.files.length === 0 ? (
              linkedMCPs.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No context linked to this project yet.</p>
              ) : null
            ) : (
              <div className="space-y-2">
                {project?.files.map((file) => (
                  <div key={file.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl border border-gray-100 group">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-blue-50 rounded-lg">
                        {file.source_id ? (
                          <Database size={16} className="text-indigo-500" />
                        ) : (
                          <FileText size={16} className="text-blue-500" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate" title={file.file_path || file.source_name || ""}>
                          {file.source_id ? (file.source_name || `Source: ${file.source_id}`) : (file.file_path?.split("/").pop() || "Unknown File")}
                        </p>
                        {file.sheet_name && (
                          <p className="text-[10px] text-gray-400">Sheet: {file.sheet_name}</p>
                        )}
                        {file.source_id && (
                          <p className="text-[10px] text-indigo-400 font-medium">From Knowledge Base</p>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => handleRemoveFile(file.id)}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            {linkedMCPs.length > 0 && (
              <div className="space-y-2 mt-2">
                {linkedMCPs.map((connector) => (
                  <div key={connector.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl border border-gray-100 group">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="p-2 bg-emerald-50 rounded-lg">
                        <Server size={16} className="text-emerald-600" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-700 truncate" title={connector.name}>
                          {connector.name}
                        </p>
                        <p className="text-[10px] text-gray-400 truncate" title={connector.generated_description || connector.description || ""}>
                          {connector.generated_description || connector.description || `${connector.tools.length} tools`}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleUnbindMCP(connector.id)}
                      className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all opacity-0 group-hover:opacity-100"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="pt-4 border-t border-gray-100">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
              Add from Knowledge Base
            </h3>
            <p className="text-[11px] text-gray-500 mb-3">
              Select a file or database from your Knowledge Base to use as context in this project.
            </p>
            <div className="flex gap-2">
              <select
                value={selectedSourceId}
                onChange={(e) => setSelectedSourceId(e.target.value)}
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all bg-white"
              >
                <option value="">Select a source...</option>
                {sources.filter(s => !project?.files.some(f => f.source_id === s.id)).map(s => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.kind})
                  </option>
                ))}
              </select>
              <button
                onClick={handleTransferSource}
                disabled={!selectedSourceId}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-all flex items-center gap-2"
              >
                <Plus size={16} />
                Add
              </button>
            </div>
          </div>

          <div className="pt-4 border-t border-gray-100">
            <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3">
              Add Database Context
            </h3>
            <div className="flex gap-2">
              <select
                aria-label="Add database context"
                value={selectedMcpId}
                onChange={(e) => setSelectedMcpId(e.target.value)}
                className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none transition-all bg-white"
              >
                <option value="">Select a database...</option>
                {availableMCPs.map((connector) => (
                  <option key={connector.id} value={connector.id}>
                    {connector.name} ({connector.tools.length} tools)
                  </option>
                ))}
              </select>
              <button
                onClick={handleBindMCP}
                disabled={!selectedMcpId}
                className="px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-all flex items-center gap-2"
              >
                <Plus size={16} />
                Add database
              </button>
            </div>
          </div>
        </div>

        <div className="p-4 bg-gray-50 border-t border-gray-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
