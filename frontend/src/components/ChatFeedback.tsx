"use client";

import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, X, MessageSquare, Check } from "lucide-react";
import { api } from "@/lib/api";

interface ChatFeedbackProps {
  chatId: string | null;
  messageId: string | null;
  onClose: () => void;
}

export default function ChatFeedback({ chatId, messageId, onClose }: ChatFeedbackProps) {
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = async (selectedRating: number) => {
    setIsSubmitting(true);
    try {
      await api.postFeedback({
        chat_id: chatId,
        message_id: messageId,
        rating: selectedRating,
        comment: comment.trim() || undefined,
      });
      setIsSubmitted(true);
      setTimeout(() => {
        onClose();
      }, 2000);
    } catch (err) {
      console.error("Feedback failed:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSubmitted) {
    return (
      <div className="fixed bottom-28 right-8 z-50 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="bg-green-600 text-white px-6 py-3 rounded-2xl shadow-2xl flex items-center gap-3">
          <Check size={18} />
          <span className="text-sm font-semibold">Thanks for your feedback!</span>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed bottom-28 right-8 z-50 animate-in fade-in slide-in-from-bottom-4 duration-500 max-w-[280px] w-full">
      <div className="bg-slate-900/95 border border-white/10 backdrop-blur-xl p-5 rounded-[28px] shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-white/50">
            <MessageSquare size={14} />
            <span className="text-[9px] font-bold uppercase tracking-[0.15em]">Rate this Answer</span>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-white/5 rounded-full text-white/30 hover:text-white transition-colors">
            <X size={14} />
          </button>
        </div>

        <div className="flex gap-2">
          <button 
            onClick={() => handleSubmit(1)}
            disabled={isSubmitting}
            className="flex-1 flex flex-col items-center gap-2 p-4 rounded-2xl bg-white/5 border border-white/5 hover:border-green-500/50 hover:bg-green-500/10 transition-all group active:scale-95"
          >
            <ThumbsUp size={20} className="text-white/40 group-hover:text-green-500 transition-colors" />
            <span className="text-[9px] font-bold text-white/40 group-hover:text-green-500 uppercase">Helpful</span>
          </button>
          <button 
            onClick={() => handleSubmit(-1)}
            disabled={isSubmitting}
            className="flex-1 flex flex-col items-center gap-2 p-4 rounded-2xl bg-white/5 border border-white/5 hover:border-red-500/50 hover:bg-red-500/10 transition-all group active:scale-95"
          >
            <ThumbsDown size={20} className="text-white/40 group-hover:text-red-500 transition-colors" />
            <span className="text-[9px] font-bold text-white/40 group-hover:text-red-500 uppercase">Bad</span>
          </button>
        </div>

        <div className="flex flex-col gap-2">
          <textarea 
            placeholder="Tell us more..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="w-full bg-white/5 border border-white/5 rounded-xl p-3 text-xs text-white placeholder:text-white/20 outline-none focus:border-white/20 transition-all min-h-[60px] resize-none"
          />
        </div>
      </div>
    </div>
  );
}
