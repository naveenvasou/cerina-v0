import { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { X, User, Bot, Wrench, Database, MessageSquare, FileText, Terminal } from 'lucide-react';
import { clsx } from 'clsx';
import { type AgentMemory, type AgentMemoryMessage } from '../types';

interface MemoryModalProps {
    isOpen: boolean;
    onClose: () => void;
    memory: AgentMemory | null;
}

type TabType = 'messages' | 'scratchpad';

export function MemoryModal({ isOpen, onClose, memory }: MemoryModalProps) {
    const [activeTab, setActiveTab] = useState<TabType>('messages');

    // Handle escape key
    const handleKeyDown = useCallback((e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
    }, [onClose]);

    useEffect(() => {
        if (isOpen) {
            document.addEventListener('keydown', handleKeyDown);
            document.body.style.overflow = 'hidden';
            setActiveTab('messages');
        }
        return () => {
            document.removeEventListener('keydown', handleKeyDown);
            document.body.style.overflow = '';
        };
    }, [isOpen, handleKeyDown]);

    if (!isOpen || !memory) return null;

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-200"
            onClick={onClose}
        >
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300" />

            <div
                className="relative w-full max-w-4xl max-h-[90vh] bg-white rounded-2xl shadow-2xl overflow-hidden flex flex-col ring-1 ring-black/5 animate-in zoom-in-95 duration-200"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Minimal Header */}
                <div className="shrink-0 px-6 py-5 border-b border-gray-100/50 flex items-center justify-between bg-white/80 backdrop-blur-md sticky top-0 z-20">
                    <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-xl bg-blue-50 border border-gray-200 flex items-center justify-center shadow-sm">
                            <Database className="w-5 h-5 text-blue-900" />
                        </div>
                        <div>
                            <h2 className="text-xl font-semibold text-gray-900 tracking-tight">{memory.agentName}</h2>
                            <div className="flex items-center gap-2 text-xs text-gray-500 font-medium">
                                <span>Agent Memory</span>
                            </div>
                        </div>
                    </div>

                    <button
                        onClick={onClose}
                        className="group p-2 rounded-full hover:bg-gray-100 transition-all duration-200 border border-transparent hover:border-gray-200"
                    >
                        <X className="w-5 h-5 text-gray-400 group-hover:text-gray-900" />
                    </button>
                </div>

                {/* Modern Pill Tabs */}
                <div className="shrink-0 px-6 pt-4 pb-2 bg-white">
                    <div className="flex p-1 bg-blue-50/50 rounded-lg w-fit">
                        <button
                            onClick={() => setActiveTab('messages')}
                            className={clsx(
                                "flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-md transition-all duration-200",
                                activeTab === 'messages'
                                    ? "bg-white text-gray-900 shadow-sm ring-1 ring-black/5"
                                    : "text-gray-500 hover:text-gray-900"
                            )}
                        >
                            <MessageSquare className="w-4 h-4" />
                            message_history
                            <span className={clsx(
                                "ml-1.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full border",
                                activeTab === 'messages' ? "bg-gray-50 border-gray-200 text-gray-900" : "bg-gray-200 border-transparent text-gray-500"
                            )}>
                                {memory.messages.length}
                            </span>
                        </button>
                        <button
                            onClick={() => setActiveTab('scratchpad')}
                            className={clsx(
                                "flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-md transition-all duration-200",
                                activeTab === 'scratchpad'
                                    ? "bg-white text-gray-900 shadow-sm ring-1 ring-black/5"
                                    : "text-gray-500 hover:text-gray-900"
                            )}
                        >
                            <FileText className="w-4 h-4" />
                            scratchpad
                        </button>
                    </div>
                </div>

                {/* Content Area */}
                <div className="flex-1 overflow-y-auto bg-white scroll-smooth">
                    {activeTab === 'messages' && (
                        <div className="p-6 md:p-8 space-y-8">
                            {memory.messages.length > 0 ? (
                                memory.messages.map((msg, idx) => (
                                    <MessageCard key={idx} message={msg} index={idx} />
                                ))
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full py-20 text-gray-400">
                                    <div className="w-16 h-16 rounded-full bg-gray-50 flex items-center justify-center mb-4">
                                        <MessageSquare className="w-8 h-8 opacity-20" />
                                    </div>
                                    <p className="text-gray-900 font-medium">No messages recorded</p>
                                    <p className="text-xs text-gray-500 mt-1">Activity will appear here</p>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'scratchpad' && (
                        <div className="p-6 md:p-8 h-full bg-gray-50/30">
                            {memory.scratchpad ? (
                                <div className="bg-white rounded-xl border border-gray-200 p-8 min-h-full">
                                    <div className="prose prose-slate prose-sm max-w-none prose-headings:font-bold prose-headings:tracking-tight prose-a:text-gray-900 prose-a:underline prose-code:text-gray-700 prose-code:bg-gray-100 prose-code:px-1 py-0.5 prose-code:rounded-md prose-pre:bg-gray-900 prose-pre:text-gray-50">
                                        <ReactMarkdown>{memory.scratchpad}</ReactMarkdown>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center h-full py-20 text-gray-400">
                                    <div className="w-16 h-16 rounded-full bg-gray-50 flex items-center justify-center mb-4">
                                        <FileText className="w-8 h-8 opacity-20" />
                                    </div>
                                    <p className="text-gray-900 font-medium">No scratchpad content</p>
                                    <p className="text-xs text-gray-500 mt-1">Thinking process will appear here</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function MessageCard({ message, index }: { message: AgentMemoryMessage; index: number }) {
    const isHuman = message.type === 'HumanMessage';
    const isTool = message.type === 'ToolMessage';
    const isAI = message.type === 'AIMessage';

    return (
        <div className={clsx(
            "relative pl-8 py-2 transition-all group",
        )}>
            {/* Timeline Line */}
            <div className="absolute left-[11px] top-0 bottom-0 w-px bg-blue-100 group-last:bottom-auto group-last:h-4" />

            {/* Timeline Dot */}
            <div className={clsx(
                "absolute left-[7px] top-6 w-2.5 h-2.5 rounded-full z-10 box-content border-4 border-white",
                isHuman && "bg-blue-600",
                isAI && "bg-blue-600",
                isTool && "bg-blue-600"
            )} />

            <div className={clsx(
                "rounded-lg border transition-all duration-200 overflow-hidden",
                isHuman && "bg-white border-gray-200",
                isAI && "bg-white border-gray-200 shadow-sm",
                isTool && "bg-white border-gray-200"
            )}>
                {/* Card Header */}
                <div className={clsx(
                    "flex items-center gap-3 px-4 py-2.5 border-b",
                    isHuman && "bg-blue-50/50 border-gray-100",
                    isAI && "bg-blue-50/50 border-gray-100",
                    isTool && "bg-blue-50/50 border-gray-100"
                )}>
                    <div className={clsx(
                        "flex items-center gap-2",
                        isHuman && "text-blue-900",
                        isAI && "text-blue-900",
                        isTool && "text-blue-900"
                    )}>
                        {isHuman && <User className="w-4 h-4 stroke-[2.5] " />}
                        {isTool && <Wrench className="w-3.5 h-3.5" />}
                        {isAI && <Bot className="w-4 h-4 stroke-[2.5]" />}

                        <span className={clsx(
                            "text-xs font-semibold tracking-wide uppercase",
                        )}>
                            {isHuman && "User"}
                            {isAI && "Assistant"}
                            {isTool && "Tool Output"}
                        </span>
                    </div>

                    {isTool && message.name && (
                        <span className="text-[10px] font-mono text-gray-500 bg-gray-200/50 px-1.5 py-0.5 rounded border border-gray-200">
                            {message.name}
                        </span>
                    )}

                    <div className="ml-auto">
                        <span className="text-[10px] font-mono text-gray-400 opacity-60">
                            #{index + 1}
                        </span>
                    </div>
                </div>

                {/* Content */}
                <div className="px-4 py-3">
                    {message.content && (
                        <div className={clsx(
                            "text-sm",
                            isHuman && "text-gray-900 font-medium leading-relaxed",
                            isTool && "font-mono text-xs text-gray-600 bg-white p-2.5 rounded border border-gray-200 max-h-80 overflow-y-auto whitespace-pre-wrap custom-scrollbar",
                            isAI && "prose prose-sm max-w-none prose-slate prose-p:text-gray-700 prose-p:leading-relaxed prose-pre:bg-gray-50 prose-pre:text-gray-800 prose-pre:border prose-pre:border-gray-200"
                        )}>
                            {isAI ? (
                                <ReactMarkdown>{message.content}</ReactMarkdown>
                            ) : (
                                message.content
                            )}
                        </div>
                    )}

                    {/* Tool Calls */}
                    {isAI && message.tool_calls && message.tool_calls.length > 0 && (
                        <div className="mt-4 space-y-2">
                            {message.tool_calls.map((tc, tcIdx) => (
                                <div key={tcIdx} className="group/tool relative overflow-hidden rounded border border-gray-200 bg-gray-50/50">
                                    <div className="flex items-center gap-3 px-3 py-2 border-b border-gray-200/50 bg-white">
                                        <Terminal className="w-3.5 h-3.5 text-gray-400" />
                                        <span className="text-xs font-semibold text-gray-700 font-mono">{tc.name}</span>
                                        <span className="text-[10px] text-gray-400 font-medium ml-auto">ARGS</span>
                                    </div>
                                    <div className="p-2.5 bg-gray-50/30">
                                        <pre className="text-[11px] text-gray-600 font-mono overflow-x-auto custom-scrollbar">
                                            {JSON.stringify(tc.args, null, 2)}
                                        </pre>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
