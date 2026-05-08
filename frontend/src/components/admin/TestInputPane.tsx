"use client";

import React, { useState, useMemo } from "react";
import { Upload, Send } from "lucide-react";

interface ParsedQuery {
  category: string;
  question: string;
}

interface TestInputPaneProps {
  onSave: (name: string, queries: ParsedQuery[]) => void;
  onCancel: () => void;
  isSaving?: boolean;
}

export default function TestInputPane({ onSave, onCancel, isSaving }: TestInputPaneProps) {
  const [suiteName, setSuiteName] = useState("");
  const [rawText, setRawText] = useState("");

  const parsedQueries = useMemo(() => {
    if (!rawText.trim()) return [];

    return rawText.split("\n")
      .map(line => line.trim())
      .filter(line => line.length > 0)
      .map(line => {
        const colonIndex = line.indexOf(":");
        // Only treat as category if it's relatively short (like a tag)
        if (colonIndex > 0 && colonIndex < 30) {
          const category = line.substring(0, colonIndex).trim();
          const question = line.substring(colonIndex + 1).trim();
          if (question) return { category, question };
        }
        return { category: "Uncategorized", question: line };
      });
  }, [rawText]);

  return (
    <div className="flex flex-col gap-6 p-1 animate-in fade-in duration-500">
      <div className="flex flex-col gap-2">
        <label className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--color-text-tertiary)" }}>
          Suite Identity
        </label>
        <input 
          type="text"
          placeholder="e.g. Q2 Performance Baseline"
          value={suiteName}
          onChange={(e) => setSuiteName(e.target.value)}
          className="w-full bg-transparent border-b border-white/10 py-3 text-xl font-bold focus:outline-none focus:border-blue-500 transition-all placeholder:opacity-30"
          style={{ color: "var(--color-text-primary)" }}
        />
      </div>

      <div className="flex flex-col gap-2 relative">
        <label className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--color-text-tertiary)" }}>
          Bulk Query Input
        </label>
        <div className="relative group">
           <textarea 
            placeholder={"Paste queries here...\nFormat: category: question (optional)\ne.g. Sales: What was our revenue in March?"}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            className="w-full h-48 bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 text-sm focus:outline-none focus:border-blue-500/50 transition-all resize-none custom-scrollbar"
            style={{ color: "var(--color-text-primary)" }}
          />
          <div className="absolute top-4 right-4 flex gap-2">
            <button className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors text-white/50 hover:text-white" title="Upload CSV/TXT (Future)">
                <Upload size={16} />
            </button>
          </div>
        </div>
      </div>

      {parsedQueries.length > 0 && (
        <div className="flex flex-col gap-3">
             <label className="text-[10px] font-bold uppercase tracking-[0.2em] flex items-center justify-between" style={{ color: "var(--color-text-tertiary)" }}>
                <span>Parsed Preview ({parsedQueries.length})</span>
                <span className="text-blue-400 capitalize text-[9px]">Auto-categorization active</span>
            </label>
            <div className="flex flex-col gap-2 max-h-60 overflow-y-auto pr-2 custom-scrollbar">
                {parsedQueries.map((q, i) => (
                    <div 
                        key={i} 
                        className="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/5 animate-in fade-in slide-in-from-left-2 duration-300"
                        style={{ animationDelay: `${i * 30}ms` }}
                    >
                        <span className="px-2 py-0.5 rounded-md bg-blue-500/10 text-blue-400 text-[9px] font-bold uppercase tracking-wider whitespace-nowrap">
                            {q.category}
                        </span>
                        <span className="text-xs truncate opacity-70" style={{ color: "var(--color-text-primary)" }}>{q.question}</span>
                    </div>
                ))}
            </div>
        </div>
      )}

      <div className="flex items-center justify-between mt-4">
        <button 
            onClick={onCancel}
            className="text-xs font-bold uppercase tracking-widest px-6 py-3 rounded-xl transition-all opacity-50 hover:opacity-100 hover:bg-white/5"
            style={{ color: "var(--color-text-secondary)" }}
        >
            Cancel
        </button>
        <button 
            disabled={!suiteName || parsedQueries.length === 0 || isSaving}
            onClick={() => onSave(suiteName, parsedQueries)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-30 disabled:hover:bg-blue-600 text-white px-8 py-3 rounded-xl text-xs font-bold uppercase tracking-widest transition-all shadow-lg shadow-blue-500/20 active:scale-95"
        >
            {isSaving ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
                <Send size={14} />
            )}
            Save Suite
        </button>
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
