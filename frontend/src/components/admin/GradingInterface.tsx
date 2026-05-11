"use client";

import React, { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { CheckCircle2, XCircle, AlertCircle, HelpCircle, ChevronRight, ChevronLeft, Save, MessageSquare, Clock, FileText, ExternalLink, Zap } from "lucide-react";

interface Evaluation {
  id: string;
  run_id: string;
  query_id: string;
  question: string;
  category: string;
  answer: string;
  grade: "pass" | "partial" | "fail" | "error" | null;
  reason: string | null;
  ai_grade: "Pass" | "Partial" | "Fail" | null;
  ai_reason: string | null;
  trace_id: string | null;
}

interface GradingInterfaceProps {
  runId: string;
  onClose: () => void;
}

export default function GradingInterface({ runId, onClose }: GradingInterfaceProps) {
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [projectName, setProjectName] = useState("data-analysis-chatbot");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [reason, setReason] = useState("");
  const [showReasonField, setShowReasonField] = useState(false);

  useEffect(() => {
    loadEvaluations();
    const timer = window.setInterval(loadEvaluations, 2500);
    return () => window.clearInterval(timer);
  }, [runId]);

  const loadEvaluations = async () => {
    try {
      const data: any = await api.listTestEvaluations(runId);
      const evals = data.evaluations || [];
      setEvaluations(evals);
      if (data.config?.phoenix_project_name) {
          setProjectName(data.config.phoenix_project_name);
      }
      if (evals.length > 0) {
        setReason(evals[0].reason || "");
        setShowReasonField(!!evals[0].reason || evals[0].grade === "partial" || evals[0].grade === "error");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const currentEval = evaluations[currentIndex];

  const handleGrade = useCallback(async (grade: "pass" | "partial" | "fail" | "error", overrideReason?: string) => {
    if (!currentEval || grading) return;
    
    setGrading(true);
    const finalReason = overrideReason !== undefined ? overrideReason : (["partial", "fail", "error"].includes(grade) ? reason : null);
    
    try {
      await api.gradeEvaluation(currentEval.id, grade, finalReason || undefined);
      
      // Update local state
      const updated = [...evaluations];
      updated[currentIndex] = { ...currentEval, grade, reason: finalReason };
      setEvaluations(updated);

      // Auto-advance if it's a "pass" or "fail" (maybe fail needs reason?)
      // For now, let's just stay on the card to allow reason entry if needed, 
      // or move to next if pass.
      if (grade === "pass" && currentIndex < evaluations.length - 1) {
        const nextIndex = currentIndex + 1;
        setCurrentIndex(nextIndex);
        setReason(evaluations[nextIndex].reason || "");
        setShowReasonField(!!evaluations[nextIndex].reason || evaluations[nextIndex].grade === "partial" || evaluations[nextIndex].grade === "error");
      }
    } catch (err) {
      console.error(err);
    } finally {
      setGrading(false);
    }
  }, [currentEval, currentIndex, evaluations, grading, reason]);

  // Hotkeys
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) return;
      
      switch (e.key) {
        case "1": handleGrade("pass"); break;
        case "2": setShowReasonField(true); handleGrade("partial"); break;
        case "3": handleGrade("fail"); break;
        case "4": setShowReasonField(true); handleGrade("error"); break;
        case "ArrowRight": 
          if (currentIndex < evaluations.length - 1) {
            const next = currentIndex + 1;
            setCurrentIndex(next);
            setReason(evaluations[next].reason || "");
            setShowReasonField(!!evaluations[next].reason || evaluations[next].grade === "partial" || evaluations[next].grade === "error");
          }
          break;
        case "ArrowLeft": 
          if (currentIndex > 0) {
            const prev = currentIndex - 1;
            setCurrentIndex(prev);
            setReason(evaluations[prev].reason || "");
            setShowReasonField(!!evaluations[prev].reason || evaluations[prev].grade === "partial" || evaluations[prev].grade === "error");
          }
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleGrade, currentIndex, evaluations]);

  if (loading) return (
    <div className="flex-1 flex flex-col items-center justify-center gap-4">
        <div className="w-12 h-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin" />
        <div className="text-sm font-bold uppercase tracking-widest opacity-40">Loading Evaluations...</div>
    </div>
  );

  if (!currentEval) return (
     <div className="flex-1 flex flex-col items-center justify-center text-center gap-6">
        <div className="p-8 rounded-full bg-blue-500/5 text-blue-500">
            <CheckCircle2 size={64} strokeWidth={1} />
        </div>
        <div>
            <h3 className="text-xl font-bold mb-2">Run Empty or Not Found</h3>
            <p className="text-sm opacity-50">No evaluations were generated for this run.</p>
        </div>
        <button onClick={onClose} className="btn btn-ghost">Go Back</button>
     </div>
  );

  const stats = {
    total: evaluations.length,
    graded: evaluations.filter(e => e.grade).length,
    pass: evaluations.filter(e => e.grade === "pass").length,
    fail: evaluations.filter(e => e.grade === "fail").length,
    partial: evaluations.filter(e => e.grade === "partial").length,
    error: evaluations.filter(e => e.grade === "error").length,
  };

  return (
    <div className="flex flex-col h-full overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-700">
      {/* Header / Progress */}
      <div className="flex items-center justify-between mb-8 px-2">
        <div className="flex flex-col gap-1">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--color-text-tertiary)" }}>
                Grading Progress
            </div>
            <div className="flex items-center gap-4">
                <div className="text-2xl font-bold">{stats.graded} <span className="text-sm opacity-30 font-medium">/ {stats.total}</span></div>
                <div className="flex gap-1 h-1.5 w-48 bg-white/5 rounded-full overflow-hidden">
                    <div className="bg-green-500 transition-all duration-500" style={{ width: `${(stats.pass / stats.total) * 100}%` }} />
                    <div className="bg-orange-500 transition-all duration-500" style={{ width: `${(stats.partial / stats.total) * 100}%` }} />
                    <div className="bg-red-500 transition-all duration-500" style={{ width: `${(stats.fail / stats.total) * 100}%` }} />
                    <div className="bg-purple-500 transition-all duration-500" style={{ width: `${(stats.error / stats.total) * 100}%` }} />
                </div>
            </div>
        </div>
        <div className="flex items-center gap-2">
            <div className="flex items-center bg-white/5 rounded-xl p-1">
                <button 
                    onClick={() => {
                        if (currentIndex > 0) {
                            const prev = currentIndex - 1;
                            setCurrentIndex(prev);
                            setReason(evaluations[prev].reason || "");
                            setShowReasonField(!!evaluations[prev].reason || evaluations[prev].grade === "partial" || evaluations[prev].grade === "error");
                        }
                    }}
                    disabled={currentIndex === 0}
                    className="p-2 rounded-lg hover:bg-white/10 disabled:opacity-20 transition-all"
                >
                    <ChevronLeft size={20} />
                </button>
                <div className="px-3 text-xs font-bold font-mono">
                    {currentIndex + 1}
                </div>
                <button 
                     onClick={() => {
                        if (currentIndex < evaluations.length - 1) {
                            const next = currentIndex + 1;
                            setCurrentIndex(next);
                            setReason(evaluations[next].reason || "");
                            setShowReasonField(!!evaluations[next].reason || evaluations[next].grade === "partial" || evaluations[next].grade === "error");
                        }
                    }}
                    disabled={currentIndex === evaluations.length - 1}
                    className="p-2 rounded-lg hover:bg-white/10 disabled:opacity-20 transition-all"
                >
                    <ChevronRight size={20} />
                </button>
            </div>
        </div>
      </div>

      {/* Card Content */}
      <div className="flex-1 overflow-y-auto pr-4 custom-scrollbar flex flex-col gap-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Left: Input */}
            <div className="flex flex-col gap-6">
                <div className="p-8 rounded-[32px] bg-white/5 border border-white/5 flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 text-[9px] font-bold uppercase tracking-wider">
                                {currentEval.category}
                            </span>
                            <span className="text-[10px] font-bold uppercase tracking-widest opacity-30">Input Query</span>
                        </div>
                        {currentEval.trace_id && (
                            <a 
                                href={`https://app.phoenix.arize.com/projects/${projectName}/traces/${currentEval.trace_id}`}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-blue-500/10 text-blue-400 text-[10px] font-bold uppercase tracking-widest hover:bg-blue-500/20 transition-all"
                            >
                                <ExternalLink size={12} /> Deep Trace
                            </a>
                        )}
                    </div>
                    <div className="text-xl font-medium leading-relaxed" style={{ color: "var(--color-text-primary)" }}>
                        {currentEval.question}
                    </div>
                </div>

                {currentEval.ai_grade && (
                    <div className="p-6 rounded-[24px] bg-blue-500/5 border border-blue-500/10 flex flex-col gap-3 animate-in fade-in slide-in-from-top-2 duration-500">
                        <div className="flex items-center justify-between">
                            <div className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2 text-blue-400">
                                <Zap size={12} /> AI Judge Verdict
                            </div>
                            <span className={`px-2 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wider ${
                                currentEval.ai_grade === 'Pass' ? 'bg-green-500/10 text-green-500' :
                                currentEval.ai_grade === 'Partial' ? 'bg-orange-500/10 text-orange-500' :
                                'bg-red-500/10 text-red-500'
                            }`}>
                                AI: {currentEval.ai_grade}
                            </span>
                        </div>
                        <p className="text-xs text-white/60 leading-relaxed italic">
                            "{currentEval.ai_reason}"
                        </p>
                    </div>
                )}

                <div className="flex flex-col gap-4">
                    <div className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
                        <Clock size={12} /> Grading Action
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <button 
                            onClick={() => handleGrade("pass")}
                            className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${currentEval.grade === "pass" ? "bg-green-500/10 border-green-500/50 text-green-500" : "bg-white/5 border-transparent hover:border-white/10"}`}
                        >
                            <div className="flex items-center gap-3">
                                <CheckCircle2 size={20} />
                                <span className="text-sm font-bold uppercase tracking-widest">Pass</span>
                            </div>
                            <span className="text-[10px] font-mono opacity-40">1</span>
                        </button>
                        <button 
                             onClick={() => { setShowReasonField(true); handleGrade("partial"); }}
                             className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${currentEval.grade === "partial" ? "bg-orange-500/10 border-orange-500/50 text-orange-500" : "bg-white/5 border-transparent hover:border-white/10"}`}
                        >
                            <div className="flex items-center gap-3">
                                <HelpCircle size={20} />
                                <span className="text-sm font-bold uppercase tracking-widest">Partial</span>
                            </div>
                            <span className="text-[10px] font-mono opacity-40">2</span>
                        </button>
                        <button 
                             onClick={() => handleGrade("fail")}
                             className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${currentEval.grade === "fail" ? "bg-red-500/10 border-red-500/50 text-red-500" : "bg-white/5 border-transparent hover:border-white/10"}`}
                        >
                            <div className="flex items-center gap-3">
                                <XCircle size={20} />
                                <span className="text-sm font-bold uppercase tracking-widest">Fail</span>
                            </div>
                            <span className="text-[10px] font-mono opacity-40">3</span>
                        </button>
                        <button 
                             onClick={() => { setShowReasonField(true); handleGrade("error"); }}
                             className={`flex items-center justify-between p-4 rounded-2xl border transition-all ${currentEval.grade === "error" ? "bg-purple-500/10 border-purple-500/50 text-purple-500" : "bg-white/5 border-transparent hover:border-white/10"}`}
                        >
                            <div className="flex items-center gap-3">
                                <AlertCircle size={20} />
                                <span className="text-sm font-bold uppercase tracking-widest">Error</span>
                            </div>
                            <span className="text-[10px] font-mono opacity-40">4</span>
                        </button>
                    </div>
                </div>

                <div className={`overflow-hidden transition-all duration-500 ${showReasonField ? "max-h-60 opacity-100" : "max-h-0 opacity-0"}`}>
                    <div className="p-6 rounded-[24px] bg-white/5 border border-white/5 flex flex-col gap-3">
                        <div className="flex items-center justify-between">
                            <label className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
                                <MessageSquare size={12} /> Evaluation Reason
                            </label>
                            {currentEval.grade && (
                                <button 
                                    onClick={() => handleGrade(currentEval.grade!, reason)}
                                    className="text-[9px] font-bold uppercase tracking-widest text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1"
                                >
                                    <Save size={10} /> Update Reason
                                </button>
                            )}
                        </div>
                        <textarea 
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="Why this grade? Provide context for model improvement..."
                            className="w-full bg-transparent text-sm focus:outline-none resize-none min-h-[80px] custom-scrollbar"
                            style={{ color: "var(--color-text-primary)" }}
                        />
                    </div>
                </div>
            </div>

            {/* Right: Output */}
            <div className="flex flex-col gap-4">
                 <div className="text-[10px] font-bold uppercase tracking-[0.2em] px-2 flex items-center gap-2" style={{ color: "var(--color-text-tertiary)" }}>
                    <FileText size={12} /> Model Response
                </div>
                <div className="flex-1 p-8 rounded-[32px] bg-white/[0.02] border border-white/5 font-mono text-sm leading-relaxed whitespace-pre-wrap overflow-y-auto custom-scrollbar min-h-[400px]" 
                    style={{ color: "var(--color-text-secondary)" }}>
                    {currentEval.answer || "No response generated."}
                </div>
            </div>
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
          background: rgba(255,255,255,0.1);
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
}
