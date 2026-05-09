"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { FlaskConical, Play, Plus, History, CheckCircle, ListTodo, Activity, X, ChevronLeft, ChevronRight, BarChart3, LayoutGrid } from "lucide-react";
import TestInputPane from "@/components/admin/TestInputPane";
import GradingInterface from "@/components/admin/GradingInterface";
import TestingDashboard from "@/components/admin/TestingDashboard";

export default function TestingPage() {
  const [suites, setSuites] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInputPane, setShowInputPane] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  
  // Selected state
  const [selectedSuiteId, setSelectedSuiteId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [isStartingRun, setIsStartingRun] = useState(false);

  const selectedSuite = suites.find(s => s.id === selectedSuiteId);

  useEffect(() => {
    loadSuites();
  }, []);

  useEffect(() => {
    if (selectedSuiteId) {
      loadRuns(selectedSuiteId);
    }
  }, [selectedSuiteId]);

  const loadSuites = async () => {
    try {
      const data = await api.listTestSuites();
      setSuites(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadRuns = async (suiteId: string) => {
    setRunsLoading(true);
    try {
      const data = await api.listTestRuns(suiteId);
      setRuns(data);
    } catch (err) {
      console.error(err);
    } finally {
      setRunsLoading(false);
    }
  };

  const handleCreateSuite = async (name: string, queries: any[]) => {
    setIsSaving(true);
    try {
      const suite = await api.createTestSuite(name);
      await api.addTestQueriesBulk(suite.id, queries);
      await loadSuites();
      setSelectedSuiteId(suite.id);
      setShowInputPane(false);
    } catch (err) {
      console.error(err);
      alert("Failed to create suite.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleStartRun = async () => {
    if (!selectedSuiteId) return;
    setIsStartingRun(true);
    try {
      await api.startTestRun(selectedSuiteId);
      // Give it a moment then refresh runs
      setTimeout(() => loadRuns(selectedSuiteId), 1000);
    } catch (err) {
      console.error(err);
      alert("Failed to start run.");
    } finally {
      setIsStartingRun(false);
    }
  };

  return (
    <div className="flex-1 overflow-hidden flex flex-col p-8 max-w-7xl mx-auto w-full">
         <div className="flex items-end justify-between mb-8">
            <div className="animate-in fade-in slide-in-from-left-4 duration-700">
                <h1 className="text-3xl font-bold tracking-tight mb-2" style={{ color: "var(--color-text-primary)" }}>CI/CD Testing Gateway</h1>
                <p className="text-sm" style={{ color: "var(--color-text-tertiary)" }}>Manage test suites, run bulk evaluations, and grade model performance.</p>
            </div>
            <button 
                onClick={() => {
                    setShowInputPane(true);
                    setShowDashboard(false);
                    setSelectedRunId(null);
                }}
                className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg shadow-blue-500/20 active:scale-95"
            >
                <Plus size={18} /> New Test Suite
            </button>
         </div>

         <div className="grid grid-cols-1 md:grid-cols-3 gap-8 flex-1 overflow-hidden">
            {/* Suites List */}
            <div className="flex flex-col gap-4 overflow-hidden">
                <h2 className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2 px-2" style={{ color: "var(--color-text-tertiary)" }}>
                    <LayoutGrid size={12} /> Test Suites
                </h2>
                
                <div className="flex-1 overflow-y-auto pr-2 flex flex-col gap-3 custom-scrollbar">
                    {loading ? (
                        [1,2,3].map(i => (
                            <div key={i} className="h-20 w-full rounded-2xl animate-pulse" style={{ background: "var(--color-background-secondary)" }} />
                        ))
                    ) : suites.length > 0 ? (
                        suites.map((s, i) => (
                            <div 
                                key={s.id} 
                                onClick={() => {
                                    setSelectedSuiteId(s.id);
                                    setSelectedRunId(null);
                                    setShowInputPane(false);
                                    setShowDashboard(false);
                                }}
                                className={`p-5 rounded-2xl cursor-pointer transition-all border group animate-in fade-in slide-in-from-bottom-2 duration-500 ${selectedSuiteId === s.id ? "bg-blue-600 border-blue-500 shadow-xl shadow-blue-500/20" : "bg-white/[0.03] border-transparent hover:border-blue-500/30"}`}
                                style={{ animationDelay: `${i * 100}ms` }}
                            >
                                <div className="flex justify-between items-start mb-2">
                                    <div className={`font-semibold transition-colors ${selectedSuiteId === s.id ? "text-white" : "group-hover:text-blue-500"}`}>{s.name}</div>
                                    <Activity size={14} className={selectedSuiteId === s.id ? "text-white" : "text-blue-500 opacity-0 group-hover:opacity-100 transition-opacity"} />
                                </div>
                                <div className={`text-[11px] flex items-center gap-3 transition-colors ${selectedSuiteId === s.id ? "text-white/70" : ""}`} style={{ color: selectedSuiteId === s.id ? undefined : "var(--color-text-tertiary)" }}>
                                    <span className="flex items-center gap-1"><ListTodo size={12} /> {s.query_count || 0} queries</span>
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="text-sm text-center py-12" style={{ color: "var(--color-text-tertiary)" }}>
                            No test suites found. Create one to get started.
                        </div>
                    )}
                </div>
            </div>

            {/* Main Content Area */}
            <div className="md:col-span-2 flex flex-col gap-6 overflow-hidden animate-in fade-in slide-in-from-right-4 duration-1000">
                {showInputPane ? (
                    <div className="flex-1 rounded-[32px] p-12 border flex flex-col gap-6 overflow-y-auto custom-scrollbar" 
                        style={{ 
                            background: "var(--color-background-secondary)", 
                            borderColor: "var(--color-border-tertiary)",
                        }}>
                        <div className="flex items-center justify-between mb-2">
                            <h3 className="text-xl font-bold">Configure New Suite</h3>
                            <button 
                                onClick={() => setShowInputPane(false)}
                                className="p-2 rounded-full hover:bg-white/5 transition-colors"
                            >
                                <X size={20} />
                            </button>
                        </div>
                        <TestInputPane 
                            onSave={handleCreateSuite} 
                            onCancel={() => setShowInputPane(false)}
                            isSaving={isSaving}
                        />
                    </div>
                ) : selectedRunId ? (
                    <div className="flex-1 rounded-[32px] p-12 border flex flex-col gap-6 overflow-hidden" 
                        style={{ 
                            background: "var(--color-background-secondary)", 
                            borderColor: "var(--color-border-tertiary)",
                        }}>
                        <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-4">
                                <button 
                                    onClick={() => setSelectedRunId(null)}
                                    className="p-2 rounded-full hover:bg-white/5 transition-colors"
                                >
                                    <ChevronLeft size={20} />
                                </button>
                                <div>
                                    <h3 className="text-xl font-bold">Grading Run</h3>
                                    <p className="text-[10px] font-bold uppercase tracking-widest opacity-30">
                                        ID: {selectedRunId.substring(0, 8)}... • {runs.find(r => r.id === selectedRunId)?.status}
                                    </p>
                                </div>
                            </div>
                        </div>
                        <GradingInterface runId={selectedRunId} onClose={() => setSelectedRunId(null)} />
                    </div>
                ) : selectedSuiteId ? (
                    <div className="flex-1 rounded-[32px] p-12 border flex flex-col gap-8 overflow-y-auto custom-scrollbar" 
                        style={{ 
                            background: "var(--color-background-secondary)", 
                            borderColor: "var(--color-border-tertiary)",
                        }}>
                        <div className="flex items-start justify-between">
                            <div>
                                <h3 className="text-2xl font-bold mb-1">{selectedSuite?.name}</h3>
                                <div className="text-xs opacity-40 uppercase tracking-widest font-bold flex items-center gap-4">
                                    <span className="flex items-center gap-1.5"><ListTodo size={14} /> {selectedSuite?.query_count} Queries</span>
                                    <span className="flex items-center gap-1.5"><History size={14} /> {runs.length} Runs</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <button 
                                    onClick={() => setShowDashboard(!showDashboard)}
                                    className={`p-2.5 rounded-xl border transition-all ${showDashboard ? "bg-blue-600 text-white border-blue-600" : "bg-white/5 border-white/10 hover:bg-white/10"}`}
                                    title="Toggle Analytics"
                                >
                                    <BarChart3 size={18} />
                                </button>
                                <button 
                                    onClick={handleStartRun}
                                    disabled={isStartingRun}
                                    className="flex items-center gap-2 bg-white text-black hover:bg-white/90 disabled:opacity-50 px-6 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest transition-all shadow-xl active:scale-95"
                                >
                                    {isStartingRun ? (
                                        <div className="w-4 h-4 border-2 border-black/10 border-t-black rounded-full animate-spin" />
                                    ) : (
                                        <Play size={14} fill="currentColor" />
                                    )}
                                    Trigger Run
                                </button>
                            </div>
                        </div>

                        {showDashboard ? (
                            <TestingDashboard runs={runs} />
                        ) : (
                            <div className="flex flex-col gap-4">
                                <h4 className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2 px-1" style={{ color: "var(--color-text-tertiary)" }}>
                                    <History size={12} /> Run History
                                </h4>
                                
                                <div className="grid grid-cols-1 gap-3">
                                    {runsLoading ? (
                                        [1,2].map(i => (
                                            <div key={i} className="h-24 w-full rounded-2xl animate-pulse bg-white/5" />
                                        ))
                                    ) : runs.length > 0 ? (
                                        runs.map((r, i) => (
                                            <div 
                                                key={r.id}
                                                onClick={() => setSelectedRunId(r.id)}
                                                className="p-6 rounded-2xl bg-white/[0.02] border border-white/5 hover:border-blue-500/30 hover:bg-white/[0.04] transition-all cursor-pointer group flex items-center justify-between"
                                            >
                                                <div className="flex items-center gap-6">
                                                    <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400">
                                                        <FlaskConical size={20} />
                                                    </div>
                                                    <div className="flex flex-col gap-1">
                                                        <div className="font-semibold flex items-center gap-2">
                                                            Run {new Date(r.created_at * 1000).toLocaleString()}
                                                            {r.status === "completed" ? (
                                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-500 uppercase tracking-tighter font-bold">Finished</span>
                                                            ) : (
                                                                <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500 uppercase tracking-tighter font-bold animate-pulse">{r.status}</span>
                                                            )}
                                                        </div>
                                                        <div className="text-[10px] uppercase tracking-widest opacity-30 font-bold flex items-center gap-3">
                                                            <span>ID: {r.id.substring(0, 8)}</span>
                                                            <span>•</span>
                                                            <span>{r.completed_count || 0} / {r.total_count || selectedSuite?.query_count || 0} Processed</span>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-4">
                                                    <div className="flex items-center gap-1">
                                                        {r.status === "completed" && (
                                                            <div className="flex items-center gap-1.5 pr-4 border-r border-white/5 mr-4">
                                                                <div className="flex flex-col items-center">
                                                                    <span className="text-[10px] font-bold text-green-500">{r.stats?.pass || 0}</span>
                                                                    <span className="text-[8px] uppercase tracking-tighter opacity-30">Pass</span>
                                                                </div>
                                                                <div className="flex flex-col items-center">
                                                                    <span className="text-[10px] font-bold text-red-500">{r.stats?.fail || 0}</span>
                                                                    <span className="text-[8px] uppercase tracking-tighter opacity-30">Fail</span>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <ChevronRight size={16} className="opacity-20 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="py-12 border-2 border-dashed border-white/5 rounded-[32px] flex flex-col items-center justify-center text-center gap-4">
                                            <div className="p-4 rounded-full bg-white/5 text-white/20">
                                                <Play size={24} />
                                            </div>
                                            <div className="max-w-xs">
                                                <p className="text-sm opacity-40">No runs yet. Trigger a run to begin evaluation of this suite.</p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="flex-1 rounded-[32px] p-12 border flex flex-col items-center justify-center text-center gap-6" 
                        style={{ 
                            background: "var(--color-background-secondary)", 
                            borderColor: "var(--color-border-tertiary)",
                            boxShadow: "inset 0 0 40px rgba(0,0,0,0.02)"
                        }}>
                        <div className="relative">
                            <div className="absolute inset-0 bg-blue-500 blur-3xl opacity-10 animate-pulse"></div>
                            <div className="relative p-8 rounded-full bg-blue-500/5 text-blue-500 border border-blue-500/10">
                                <FlaskConical size={64} strokeWidth={1.5} />
                            </div>
                        </div>
                        <div className="max-w-sm">
                            <h3 className="text-xl font-bold mb-3">Cockpit Standby</h3>
                            <p className="text-sm leading-relaxed" style={{ color: "var(--color-text-tertiary)" }}>
                                Select a test suite from the sidebar to manage queries, trigger evaluation runs, and compare version snapshots.
                            </p>
                        </div>
                        <div className="flex gap-4 mt-4">
                            <div className="px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest flex items-center gap-2" style={{ background: "var(--color-background-primary)", color: "var(--color-text-tertiary)" }}>
                                <CheckCircle size={12} className="text-green-500" /> 100% Reliable
                            </div>
                            <div className="px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-widest flex items-center gap-2" style={{ background: "var(--color-background-primary)", color: "var(--color-text-tertiary)" }}>
                                <Activity size={12} className="text-blue-500" /> Version Control
                            </div>
                        </div>
                    </div>
                )}
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
            background: var(--color-border-tertiary);
            border-radius: 10px;
            }
        `}</style>
    </div>
  );
}
