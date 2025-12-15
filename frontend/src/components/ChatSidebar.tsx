import { useState, useRef, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Check, Send, Paperclip, ChevronDown, ChevronRight, ChevronUp, FileText, Loader2, Brain, Wrench, Terminal, Database, ShieldCheck } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { type Message, type AgentMemory } from '../types';
import { MemoryModal } from './MemoryModal';

function cn(...inputs: (string | undefined | null | false)[]) {
    return twMerge(clsx(inputs));
}

interface ChatSidebarProps {
    messages: Message[];
    onSendMessage: (text: string) => void;
    isConnected: boolean;
    agentMemories?: Record<string, AgentMemory>;
}

export function ChatSidebar({ messages, onSendMessage, isConnected, agentMemories = {} }: ChatSidebarProps) {
    const [inputValue, setInputValue] = useState("");
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Memory modal state
    const [memoryModalOpen, setMemoryModalOpen] = useState(false);
    const [selectedAgentMemory, setSelectedAgentMemory] = useState<AgentMemory | null>(null);

    const handleOpenMemory = (agentName?: string) => {
        if (agentName && agentMemories[agentName]) {
            setSelectedAgentMemory(agentMemories[agentName]);
            setMemoryModalOpen(true);
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSendMessage = () => {
        if (!inputValue.trim()) return;
        onSendMessage(inputValue);
        setInputValue("");
    };

    return (
        <div className="flex flex-col h-full bg-white w-full relative">
            {/* Header */}
            <div className="h-10 border-b border-gray-100 flex items-center justify-between px-4 bg-white sticky top-0 z-10">
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Chat</span>
                <span className={cn("w-2 h-2 rounded-full", isConnected ? "bg-green-500" : "bg-gray-300")} title={isConnected ? "Online" : "Offline"} />
            </div>

            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3 pb-64">
                {messages.map((msg) => (
                    <MessageItem
                        key={msg.id}
                        message={msg}
                        onOpenMemory={handleOpenMemory}
                        hasMemory={msg.agentName ? !!agentMemories[msg.agentName] : false}
                    />
                ))}
                <div ref={messagesEndRef} />
            </div>

            {/* Floating Input Area */}
            <div className="absolute bottom-4 left-4 right-4 z-20">
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-3">
                    <textarea
                        value={inputValue}
                        onChange={(e) => setInputValue(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSendMessage();
                            }
                        }}
                        placeholder="Send message..."
                        className="w-full min-h-[40px] max-h-[120px] p-2 resize-none bg-transparent border-none focus:ring-0 focus:outline-none text-gray-800 placeholder:text-gray-400 text-sm leading-relaxed"
                    />

                    <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-50">
                        <div className="flex items-center gap-2">
                            <button className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-50 rounded transition-colors">
                                <Paperclip className="w-4 h-4" />
                            </button>
                        </div>
                        <button
                            onClick={handleSendMessage}
                            disabled={!inputValue.trim()}
                            className="p-2 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                            <Send className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Memory Modal */}
            <MemoryModal
                isOpen={memoryModalOpen}
                onClose={() => setMemoryModalOpen(false)}
                memory={selectedAgentMemory}
            />
        </div>
    );
}

// --- Message Item Router ---
function MessageItem({ message, onOpenMemory, hasMemory }: { message: Message; onOpenMemory?: (agentName?: string) => void; hasMemory?: boolean }) {
    if (message.type === 'agent_start') return <AgentStartItem message={message} onOpenMemory={onOpenMemory} hasMemory={hasMemory} />;
    if (message.type === 'thought') return <ThoughtItem message={message} />;
    if (message.type === 'tool') return <ToolCard message={message} />;
    if (message.type === 'artifact') return <ArtifactItem message={message} />;
    if (message.type === 'critique') return <CritiqueItem message={message} />;
    if (message.type === 'log') return <LogItem message={message} />;
    if (message.type === 'action') return <ActionItem message={message} />;
    return <TextMessage message={message} />;
}

// --- Agent Start (Prominent) ---
function AgentStartItem({ message, onOpenMemory, hasMemory }: { message: Message; onOpenMemory?: (agentName?: string) => void; hasMemory?: boolean }) {
    // Helper to get initials (e.g. "Sales Bot" -> "SB")
    const initials = useMemo(() => {
        const name = message.agentName ?? 'AI Agent';
        return name
            .split(' ')
            .map((n) => n[0])
            .slice(0, 2)
            .join('')
            .toUpperCase();
    }, [message.agentName]);

    return (
        <div className="py-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
            <div className="flex items-start gap-4 px-5 py-4 bg-white border border-gray-100 shadow-sm rounded-xl">
                {/* Gradient Avatar with Initials */}
                <div className="flex items-center justify-center flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br from-gray-600 to-gray-800 shadow-sm">
                    <span className="text-xs font-bold text-white tracking-wider">
                        {initials}
                    </span>
                </div>

                <div className="flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-gray-900">
                            {message.agentName}
                        </span>

                    </div>
                    <div className="text-sm leading-relaxed text-gray-600">
                        {message.content}
                    </div>
                </div>

                {/* Memory Button */}
                {hasMemory && (
                    <button
                        onClick={() => onOpenMemory?.(message.agentName)}
                        className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-blue-900 bg-blue-50/50 hover:bg-blue-50 rounded-lg transition-colors"
                        title="View agent memory"
                    >
                        <Database className="w-3.5 h-3.5" />
                        <span>Memory</span>
                    </button>
                )}
            </div>
        </div>
    );
}

// --- Thought (Minimal) ---
function ThoughtItem({ message }: { message: Message }) {
    const [expanded, setExpanded] = useState(true);

    // Auto-collapse when streaming completes
    useEffect(() => {
        if (!message.isStreaming && expanded) {
            // Small delay before collapsing for smoother UX
            const timer = setTimeout(() => setExpanded(false), 300);
            return () => clearTimeout(timer);
        }
    }, [message.isStreaming]);

    // If content is short, we might not need the toggle, 
    // but keeping the card structure ensures visual consistency.

    return (
        <div className="w-full max-w-md my-2">
            <div
                className={clsx(
                    "group flex flex-col border border-gray-200 bg-white rounded-lg overflow-hidden transition-all duration-200 ease-in-out",
                    expanded ? "shadow-sm ring-1 ring-gray-200" : "hover:border-gray-300"
                )}
            >
                {/* Header */}
                <button
                    onClick={() => setExpanded(!expanded)}
                    className="flex items-start gap-3 px-3 py-2.5 w-full text-left cursor-pointer hover:bg-gray-50/50 transition-colors"
                >
                    {/* Icon - Purple for "Reasoning/Brain" */}
                    <div className="flex items-center justify-center w-5 h-5 rounded bg-violet-50 text-violet-600 mt-0.5 shrink-0">
                        <Brain className="w-3 h-3" />
                    </div>

                    <div className="flex flex-col flex-1 gap-1">
                        {/* Label */}
                        <div className="flex items-center gap-2">
                            <span className="text-[13px] font-medium text-gray-700">
                                Reasoning
                            </span>
                            {!expanded && !message.isStreaming && (
                                <span className="text-[11px] text-gray-400 font-normal truncate max-w-[200px]">
                                    {message.content}
                                </span>
                            )}
                        </div>

                        {/* Expanded Content - Rendered here if we want it to flow naturally 
                OR we can put it in a separate block below like the tools. 
                For thoughts, inline flow often feels more natural. */}
                        {expanded && (
                            <div className="animate-in fade-in slide-in-from-top-1 duration-200">
                                <div className="prose prose-sm prose-gray max-w-none text-[13px] text-gray-600 leading-relaxed italic prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5 prose-headings:text-gray-700 prose-headings:font-medium prose-strong:text-gray-700 prose-code:text-violet-600 prose-code:bg-violet-50 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs">
                                    <ReactMarkdown>{message.content}</ReactMarkdown>
                                </div>
                                {message.isStreaming && <span className="inline-block w-2 h-4 bg-violet-400 ml-0.5 animate-pulse" />}
                            </div>
                        )}
                    </div>

                    {/* Toggle Arrow */}
                    <ChevronDown
                        className={clsx(
                            "w-4 h-4 text-gray-400 transition-transform duration-200 mt-0.5 shrink-0",
                            expanded && "rotate-180"
                        )}
                    />
                </button>
            </div>
        </div>
    );
}

// --- Unified Tool Card (handles both running and completed states) ---
function ToolCard({ message }: { message: Message }) {
    const [expanded, setExpanded] = useState(false);
    const isCompleted = message.toolStatus === 'completed';
    const hasArgs = message.toolArgs && Object.keys(message.toolArgs).length > 0;
    const hasOutput = !!message.toolOutput;
    const hasExpandableContent = hasArgs || hasOutput;

    return (
        <div className="w-full max-w-md my-2">
            <div
                className={clsx(
                    "group flex flex-col border border-gray-200 bg-white rounded-lg overflow-hidden transition-all duration-200 ease-in-out",
                    expanded ? "shadow-sm ring-1 ring-gray-200" : "hover:border-gray-300"
                )}
            >
                {/* Header - Always Visible */}
                <button
                    onClick={() => hasExpandableContent && setExpanded(!expanded)}
                    disabled={!hasExpandableContent}
                    className={clsx(
                        "flex items-center gap-3 px-3 py-2.5 w-full text-left transition-colors",
                        hasExpandableContent ? "cursor-pointer hover:bg-gray-50/50" : "cursor-default"
                    )}
                >
                    {/* Status Icon */}
                    <div className={clsx(
                        "flex items-center justify-center w-5 h-5 rounded",
                        isCompleted ? "bg-emerald-50 text-emerald-600" : " bg-emerald-50 text-emerald-500"
                    )}>
                        {isCompleted ? (
                            <Check className="w-3 h-3" strokeWidth={3} />
                        ) : (
                            <Loader2 className="w-3 h-3 animate-spin" />
                        )}
                    </div>

                    {/* Tool Info */}
                    <div className="flex flex-col flex-1 leading-none gap-0.5">
                        <span className="text-[13px] font-medium text-gray-700 font-mono">
                            {message.toolName}
                        </span>
                        <span className="text-[11px] text-gray-400">
                            {isCompleted ? 'Complete' : 'Running...'}
                        </span>
                    </div>

                    {/* Toggle Indicator */}
                    {hasExpandableContent && (
                        <ChevronDown
                            className={clsx(
                                "w-4 h-4 text-gray-400 transition-transform duration-200",
                                expanded && "rotate-180"
                            )}
                        />
                    )}
                </button>

                {/* Expandable Body */}
                {expanded && hasExpandableContent && (
                    <div className="border-t border-gray-100 bg-gray-50/50 animate-in fade-in slide-in-from-top-1 duration-200">
                        {/* Arguments Section */}
                        {hasArgs && (
                            <div className="px-3 py-2 border-b border-gray-100">
                                <div className="flex items-center gap-1.5 mb-2 text-xs text-gray-500 uppercase tracking-wider font-semibold">
                                    <Terminal className="w-3 h-3" />
                                    Arguments
                                </div>
                                <pre className="text-[11px] font-mono leading-relaxed text-gray-600 overflow-x-auto whitespace-pre-wrap">
                                    {JSON.stringify(message.toolArgs, null, 2)}
                                </pre>
                            </div>
                        )}

                        {/* Output Section (only if completed) */}
                        {hasOutput && (
                            <div className="px-3 py-2">
                                <div className="flex items-center gap-1.5 mb-2 text-xs text-gray-500 uppercase tracking-wider font-semibold">
                                    <FileText className="w-3 h-3" />
                                    Result
                                </div>
                                <pre className="text-[11px] font-mono leading-relaxed text-gray-600 whitespace-pre-wrap max-h-48 overflow-y-auto">
                                    {message.toolOutput}
                                </pre>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

// --- Artifact (Plan, Draft, Revision, etc.) ---
function ArtifactItem({ message }: { message: Message }) {
    const [expanded, setExpanded] = useState(false);
    const isPlan = message.artifactType === 'clinical_protocol';
    const isRevision = message.artifactType === 'draft_revision';
    const isFinal = message.artifactType === 'cbt_exercise';

    // Determine display properties based on artifact type
    const getDisplayProps = () => {
        if (isPlan) {
            return { label: 'Plan', icon: <Wrench className="w-4 h-4 text-blue-500" />, borderColor: 'border-blue-200' };
        }
        if (isRevision) {
            return { label: 'Revision', icon: <FileText className="w-4 h-4 text-purple-500" />, borderColor: 'border-purple-200' };
        }
        if (isFinal) {
            return { label: 'Final', icon: <FileText className="w-4 h-4 text-green-500" />, borderColor: 'border-green-200' };
        }
        return { label: 'Artifact', icon: <FileText className="w-4 h-4 text-gray-500" />, borderColor: 'border-gray-200' };
    };

    const { label, icon, borderColor } = getDisplayProps();

    return (
        <div className="py-2 animate-in fade-in duration-200">
            <div
                onClick={() => setExpanded(!expanded)}
                className={`flex items-center gap-3 p-3 border ${borderColor} rounded-lg cursor-pointer hover:border-gray-300 transition-colors`}
            >
                <div className="w-8 h-8 rounded bg-gray-100 flex items-center justify-center">
                    {icon}
                </div>
                <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-gray-400 uppercase tracking-wide font-medium">
                        {label}
                    </div>
                    <div className="text-sm text-gray-700 font-medium truncate">
                        {message.artifactTitle || 'Artifact'}
                    </div>
                </div>
                {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </div>
            {expanded && (
                <pre className="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-700 font-mono overflow-x-auto max-h-48 overflow-y-auto whitespace-pre-wrap border border-gray-100">
                    {message.content}
                </pre>
            )}
        </div>
    );
}


// --- Critique Card ---
function CritiqueItem({ message }: { message: Message }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="py-2 animate-in fade-in duration-200">
            <div
                onClick={() => setExpanded(!expanded)}
                className="flex items-center gap-3 p-3 border border-orange-200 rounded-lg cursor-pointer hover:border-orange-300 transition-colors bg-orange-50/30"
            >
                <div className="w-8 h-8 rounded bg-orange-100 flex items-center justify-center">
                    <ShieldCheck className="w-4 h-4 text-orange-600" />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <div className="text-[10px] text-orange-600 uppercase tracking-wide font-medium">
                            Critique Report
                        </div>
                        {message.iteration && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-orange-100 text-orange-700 rounded font-medium">
                                Iteration {message.iteration}
                            </span>
                        )}
                    </div>
                    <div className="text-sm text-gray-700 font-medium truncate">
                        3-Agent Critique (Safety, Clinical, Tone)
                    </div>
                </div>
                {expanded ? <ChevronUp className="w-4 h-4 text-orange-400" /> : <ChevronDown className="w-4 h-4 text-orange-400" />}
            </div>
            {expanded && (
                <div className="mt-2 p-4 bg-white rounded-lg border border-orange-100 max-h-96 overflow-y-auto">
                    <div className="prose prose-sm prose-orange max-w-none text-gray-700">
                        <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                </div>
            )}
        </div>
    );
}

// --- Log/Status ---
function LogItem({ message }: { message: Message }) {
    return (
        <div className="flex items-center justify-center py-1 opacity-60">
            <span className="text-[10px] text-gray-400 uppercase tracking-wide">{message.content}</span>
        </div>
    );
}

// --- Action Card ---
function ActionItem({ message }: { message: Message }) {
    return (
        <div className="py-2 animate-in fade-in duration-200">
            <div className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg">
                <div className="w-8 h-8 rounded bg-gray-100 flex items-center justify-center">
                    <FileText className="w-4 h-4 text-gray-500" />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-gray-400 uppercase tracking-wide font-medium">
                        {message.actionType || 'update'}
                    </div>
                    <div className="text-sm text-gray-700 font-mono truncate">
                        {message.fileName || 'document.md'}
                    </div>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-400" />
            </div>
        </div>
    );
}

// --- Default Text Message ---
function TextMessage({ message }: { message: Message }) {
    const isUser = message.role === 'user';
    const [expanded, setExpanded] = useState(true);

    // Compute truncated content (first 3 lines)
    const { truncatedContent, hasMore } = useMemo(() => {
        const lines = message.content.split('\n');
        const MAX_LINES = 2;
        if (lines.length <= MAX_LINES) {
            return { truncatedContent: message.content, hasMore: false };
        }
        return {
            truncatedContent: lines.slice(0, MAX_LINES).join('\n'),
            hasMore: true
        };
    }, [message.content]);

    // Only allow collapsing for assistant messages with more than 3 lines
    const isCollapsible = !isUser && hasMore;

    // Auto-collapse when streaming completes
    useEffect(() => {
        if (isCollapsible && !message.isStreaming && expanded) {
            // Small delay to let user see the final chunk briefly
            const timer = setTimeout(() => setExpanded(false), 500);
            return () => clearTimeout(timer);
        }
    }, [message.isStreaming, isCollapsible]);

    return (
        <div className={cn("py-1", isUser ? "text-right" : "text-left")}>
            <div className={cn(
                "inline-block max-w-[85%] text-sm leading-relaxed transition-all",
                isUser ? "bg-gray-100 text-gray-800 px-3 py-2 rounded-xl" : "text-gray-700 w-full"
            )}>
                {/* Header for assistant messages */}
                {!isUser && (
                    <div className="flex items-center gap-2 mb-1 p-1 -ml-1 w-fit">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                            {message.agentName || 'Assistant'}
                        </span>
                    </div>
                )}

                {/* Content */}
                <div className={cn("prose prose-sm prose-gray max-w-none text-gray-800", isUser && "text-gray-800")}>
                    <ReactMarkdown>
                        {expanded || !hasMore ? message.content : truncatedContent}
                    </ReactMarkdown>
                </div>

                {/* Show more/less toggle */}
                {isCollapsible && (
                    <button
                        onClick={() => setExpanded(!expanded)}
                        className="flex items-center gap-1 mt-2 text-xs text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        {expanded ? (
                            <>
                                <ChevronUp className="w-3 h-3" />
                                <span>Show less</span>
                            </>
                        ) : (
                            <>
                                <ChevronDown className="w-3 h-3" />
                                <span>Show more</span>
                            </>
                        )}
                    </button>
                )}
            </div>
        </div>
    );
}
