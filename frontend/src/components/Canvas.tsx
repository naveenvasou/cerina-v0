
import { useState, useMemo } from 'react';
import { FileText, MoreHorizontal, Search, BrainCircuit, History, ChevronDown, Activity, ClipboardList, ShieldAlert, BookOpen, AlertTriangle, Eye, Ruler, CheckCircle } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: (string | undefined | null | false)[]) {
    return twMerge(clsx(inputs));
}

type TabType = 'draft' | 'research' | 'critic';

interface Tab {
    id: TabType;
    label: string;
    icon: React.ElementType;
}

const TABS: Tab[] = [
    { id: 'research', label: 'Planner Spec', icon: Search },
    { id: 'draft', label: 'Draft', icon: FileText },
    { id: 'critic', label: 'Critic Agent', icon: BrainCircuit },
];

interface DraftVersion {
    version: number;
    content: string;
    timestamp: string;
    status: 'draft' | 'revised' | 'final';
    iteration?: number;
    changes?: string;
}

interface CritiqueDocument {
    content: string;
    iteration: number;
    timestamp: string;
}

interface CanvasProps {
    plan: string;
    draft: string;
    critiqueDocument?: CritiqueDocument | null;
    critiqueVersions?: CritiqueDocument[];
    currentCritiqueIteration?: number;
    draftVersions?: DraftVersion[];
    currentDraftVersion?: number;
    reflectionIteration?: number;
    onVersionSelect?: (version: number) => void;
    onCritiqueVersionSelect?: (iteration: number) => void;
}

// --- New Planner Output Interfaces ---

interface DraftingSpec {
    required_fields?: string[];
    task_constraints?: Record<string, string | number>;
    style_rules?: string[];
}

interface SafetyEnvelope {
    forbidden_content?: string[];
    special_conditions?: string[];
}

interface CriticRubrics {
    safety?: string[];
    clinical_accuracy?: string[];
    usability?: string[];
}

interface EvidenceAnchor {
    source: string;
    note: string;
}

interface PlannerOutput {
    exercise_type?: string;
    drafting_spec?: DraftingSpec;
    safety_envelope?: SafetyEnvelope;
    critic_rubrics?: CriticRubrics;
    evidence_anchors?: EvidenceAnchor[];
    user_preview?: string;
}

export function Canvas({
    plan,
    draft,
    critiqueDocument,
    critiqueVersions = [],
    currentCritiqueIteration = 1,
    draftVersions = [],
    currentDraftVersion = 1,
    reflectionIteration = 0,
    onVersionSelect,
    onCritiqueVersionSelect
}: CanvasProps) {
    const [activeTab, setActiveTab] = useState<TabType>('research');
    const [showVersionDropdown, setShowVersionDropdown] = useState(false);

    // Parse Plan JSON safely
    const parsedPlan: PlannerOutput | null = useMemo(() => {
        if (!plan) return null;
        try {
            return JSON.parse(plan);
        } catch (e) {
            console.error("Failed to parse plan JSON", e);
            return null;
        }
    }, [plan]);

    // Get current version display text (tab-aware)
    const currentVersionText = useMemo(() => {
        if (activeTab === 'critic') {
            // For critic tab, show critique iterations
            if (critiqueVersions.length === 0) return 'Iteration 1 (Current)';
            const isCurrent = currentCritiqueIteration === critiqueVersions.length;
            return `Iteration ${currentCritiqueIteration}${isCurrent ? ' (Current)' : ''}`;
        }
        // For draft tab
        if (draftVersions.length === 0) return 'v1 (Current)';
        const version = draftVersions.find(v => v.version === currentDraftVersion);
        if (!version) return `v${currentDraftVersion}`;
        const isCurrent = version.version === draftVersions[draftVersions.length - 1]?.version;
        const statusBadge = version.status === 'final' ? ' ✅' : version.status === 'revised' ? ' 📝' : '';
        return `v${version.version}${statusBadge}${isCurrent ? ' (Current)' : ''}`;
    }, [activeTab, draftVersions, currentDraftVersion, critiqueVersions, currentCritiqueIteration]);

    // Get versions to display in dropdown based on active tab
    const versionsToShow = activeTab === 'critic' ? critiqueVersions : draftVersions;
    const versionCount = versionsToShow.length;

    return (
        <div className="flex-1 h-full bg-white flex flex-col relative overflow-hidden font-sans text-gray-900">
            {/* 1. Tabs Header */}
            <div className="flex items-center bg-gray-50 border-b border-gray-200">
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        className={cn(
                            "flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-r border-gray-200 transition-colors min-w-[140px]",
                            activeTab === tab.id
                                ? "bg-white text-gray-900 border-t-2 border-t-blue-500"
                                : "bg-gray-50 text-gray-500 hover:bg-gray-100 hover:text-gray-700 border-t-2 border-t-transparent"
                        )}
                    >
                        <tab.icon className={cn("w-3.5 h-3.5", activeTab === tab.id ? "text-blue-500" : "text-gray-400")} />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* 2. Sub-header / Toolbar */}
            <div className="h-12 border-b border-gray-100 flex items-center justify-between px-6 bg-white shrink-0">
                <div className="flex items-center gap-2 text-sm text-gray-500">
                    <span className="font-semibold text-gray-800">
                        {activeTab === 'draft' ? (draft ? 'CBT_Exercise.md' : 'New Draft') :
                            activeTab === 'research' ? 'Planner_Spec.json' : `Critique_Report_v${critiqueDocument?.iteration || 1}.md`}
                    </span>
                    {activeTab === 'draft' && !!draft && <span className="text-xs px-2 py-0.5 bg-green-50 text-green-700 border border-green-100 rounded-full font-medium">Live View</span>}
                    {reflectionIteration > 0 && (
                        <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 border border-blue-100 rounded-full font-medium">
                            Iteration {reflectionIteration}
                        </span>
                    )}
                </div>

                {/* Version History Dropdown - Only show for draft and critic tabs */}
                {(activeTab === 'draft' || activeTab === 'critic') && (
                    <div className="flex items-center gap-2 relative">
                        <div
                            onClick={() => setShowVersionDropdown(!showVersionDropdown)}
                            className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-lg hover:border-gray-300 transition-colors cursor-pointer group shadow-sm"
                        >
                            <History className="w-3.5 h-3.5 text-gray-400 group-hover:text-blue-500 transition-colors" />
                            <span className="text-xs font-medium text-gray-600">{currentVersionText}</span>
                            {versionCount > 1 && (
                                <span className="text-[10px] px-1.5 py-0.5 bg-blue-50 text-blue-600 rounded font-medium">
                                    {versionCount}
                                </span>
                            )}
                            <ChevronDown className={cn("w-3 h-3 text-gray-400 transition-transform", showVersionDropdown && "rotate-180")} />
                        </div>

                        {/* Version Dropdown Menu */}
                        {showVersionDropdown && (
                            <div className="absolute top-full right-0 mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1 max-h-80 overflow-y-auto">
                                {activeTab === 'critic' ? (
                                    // Critique versions dropdown
                                    critiqueVersions.length === 0 ? (
                                        <div className="px-4 py-3 text-xs text-gray-400 text-center">
                                            No critiques yet. Wait for the critic agent to evaluate.
                                        </div>
                                    ) : (
                                        critiqueVersions.slice().reverse().map((critique) => {
                                            const formattedTime = new Date(critique.timestamp).toLocaleTimeString('en-US', {
                                                hour: '2-digit',
                                                minute: '2-digit'
                                            });
                                            return (
                                                <button
                                                    key={critique.iteration}
                                                    onClick={() => {
                                                        onCritiqueVersionSelect?.(critique.iteration);
                                                        setShowVersionDropdown(false);
                                                    }}
                                                    className={cn(
                                                        "w-full px-3 py-2.5 text-left text-xs hover:bg-gray-50 flex items-center justify-between gap-2 border-b border-gray-50 last:border-0",
                                                        critique.iteration === currentCritiqueIteration && "bg-blue-50/50"
                                                    )}
                                                >
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="font-semibold text-gray-800">Iteration {critique.iteration}</span>
                                                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-100 text-orange-700">
                                                                critique
                                                            </span>
                                                            {critique.iteration === currentCritiqueIteration && (
                                                                <span className="text-[10px] text-blue-600 font-medium">← viewing</span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <span className="text-gray-400 text-[10px] shrink-0">{formattedTime}</span>
                                                </button>
                                            );
                                        })
                                    )
                                ) : (
                                    // Draft versions dropdown
                                    draftVersions.length === 0 ? (
                                        <div className="px-4 py-3 text-xs text-gray-400 text-center">
                                            No versions yet. Generate a draft to start tracking versions.
                                        </div>
                                    ) : (
                                        draftVersions.slice().reverse().map((version) => {
                                            const formattedTime = new Date(version.timestamp).toLocaleTimeString('en-US', {
                                                hour: '2-digit',
                                                minute: '2-digit'
                                            });
                                            return (
                                                <button
                                                    key={version.version}
                                                    onClick={() => {
                                                        onVersionSelect?.(version.version);
                                                        setShowVersionDropdown(false);
                                                    }}
                                                    className={cn(
                                                        "w-full px-3 py-2.5 text-left text-xs hover:bg-gray-50 flex items-center justify-between gap-2 border-b border-gray-50 last:border-0",
                                                        version.version === currentDraftVersion && "bg-blue-50/50"
                                                    )}
                                                >
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className="font-semibold text-gray-800">v{version.version}</span>
                                                            <span className={cn(
                                                                "px-1.5 py-0.5 rounded text-[10px] font-medium",
                                                                version.status === 'final' ? "bg-green-100 text-green-700" :
                                                                    version.status === 'revised' ? "bg-blue-100 text-blue-700" :
                                                                        "bg-gray-100 text-gray-600"
                                                            )}>
                                                                {version.status}
                                                            </span>
                                                            {version.version === currentDraftVersion && (
                                                                <span className="text-[10px] text-blue-600 font-medium">← viewing</span>
                                                            )}
                                                        </div>
                                                        {version.changes && (
                                                            <p className="text-gray-500 mt-1 truncate">{version.changes}</p>
                                                        )}
                                                    </div>
                                                    <span className="text-gray-400 text-[10px] shrink-0">{formattedTime}</span>
                                                </button>
                                            );
                                        })
                                    )
                                )}
                            </div>
                        )}

                        <button className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-50 rounded-md transition-colors">
                            <MoreHorizontal className="w-4 h-4" />
                        </button>
                    </div>
                )}

            </div>

            {/* 3. Main Content Area */}
            <div className="flex-1 overflow-y-auto bg-gray-50/30 p-8 flex justify-center">
                {activeTab === 'draft' ? (
                    <div className="w-full max-w-5xl bg-white shadow-sm border border-gray-200 rounded-xl p-12 transition-all h-fit min-h-[600px]">
                        {/* Draft Content */}
                        {!draft ? (
                            <div className="flex flex-col items-center justify-center min-h-[400px] text-gray-400 space-y-4">
                                <FileText className="w-16 h-16 opacity-10" />
                                <div className="text-center space-y-1">
                                    <p className="font-medium text-gray-500">Waiting for Draftsman Agent...</p>
                                    <p className="text-xs text-gray-400">The content will appear here once generated.</p>
                                </div>
                            </div>
                        ) : (
                            <div className="prose prose-slate prose-sm sm:prose-base max-w-none break-words prose-table:border-collapse prose-th:border prose-th:border-gray-300 prose-th:p-2 prose-th:bg-gray-50 prose-td:border prose-td:border-gray-300 prose-td:p-2">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{draft}</ReactMarkdown>
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="w-full max-w-4xl h-full pb-20">
                        {/* Agent Output View */}
                        <div className="flex flex-col gap-6">
                            {activeTab === 'research' && (
                                <div className="space-y-6 animate-in fade-in duration-500 slide-in-from-bottom-4 pb-12">

                                    {!parsedPlan ? (
                                        // Plain Text Fallback or Loading
                                        <div className="w-full bg-white min-h-[400px] shadow-sm border border-gray-200 rounded-xl p-8 flex flex-col items-center justify-center text-gray-400">
                                            {plan ? (
                                                <pre className="whitespace-pre-wrap text-sm font-mono text-gray-700 w-full overflow-auto max-h-[600px]">{plan}</pre>
                                            ) : (
                                                <>
                                                    <Search className="w-12 h-12 opacity-10 mb-4" />
                                                    <p>Waiting for planner specification...</p>
                                                </>
                                            )}
                                        </div>
                                    ) : (
                                        // Structured Planner Output Display
                                        <>
                                            {/* Header Card */}
                                            <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm relative overflow-hidden">
                                                <div className="absolute top-0 left-0 w-1 h-full bg-indigo-500"></div>
                                                <div className="flex items-start justify-between">
                                                    <div>
                                                        <div className="flex items-center gap-2 mb-2">
                                                            <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase bg-indigo-50 text-indigo-600 border border-indigo-100">
                                                                Execution Plan
                                                            </span>
                                                        </div>
                                                        <h2 className="text-xl font-bold text-gray-900 mb-2">
                                                            {parsedPlan.exercise_type || 'Untitled Exercise Plan'}
                                                        </h2>
                                                        {parsedPlan.user_preview && (
                                                            <div className="flex items-start gap-2 text-sm text-gray-500 bg-gray-50 p-3 rounded-lg border border-gray-100">
                                                                <Eye className="w-4 h-4 mt-0.5 text-gray-400 shrink-0" />
                                                                <span className="italic">"{parsedPlan.user_preview}"</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div className="h-10 w-10 bg-indigo-50 rounded-full flex items-center justify-center">
                                                        <Activity className="w-5 h-5 text-indigo-500" />
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Drafting Specs Grid */}
                                            {parsedPlan.drafting_spec && (
                                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                    {/* Required Fields & Style Rules */}
                                                    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
                                                        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                                                            <ClipboardList className="w-4 h-4" /> Requirements
                                                        </h3>
                                                        <div className="space-y-4">
                                                        
                                                            <div>
                                                                <span className="text-xs font-semibold text-gray-800 block mb-2">Style Rules</span>
                                                                <ul className="space-y-1.5">
                                                                    {parsedPlan.drafting_spec.style_rules?.map((rule, i) => (
                                                                        <li key={i} className="text-xs text-gray-600 flex items-start gap-1.5">
                                                                            <span className="block w-1 h-1 rounded-full bg-gray-400 mt-1.5 shrink-0"></span>
                                                                            {rule}
                                                                        </li>
                                                                    ))}
                                                                </ul>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    {/* Task Constraints */}
                                                    <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
                                                        <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                                                            <Ruler className="w-4 h-4" /> Constraints
                                                        </h3>
                                                        <div className="space-y-3">
                                                            {parsedPlan.drafting_spec.task_constraints && Object.entries(parsedPlan.drafting_spec.task_constraints).map(([key, value], i) => (
                                                                <div key={i} className="flex flex-col gap-1 pb-2 border-b border-gray-50 last:border-0 last:pb-0">
                                                                    <span className="text-[10px] font-mono text-gray-400 uppercase">{key.replace(/_/g, ' ')}</span>
                                                                    <span className="text-sm text-gray-700 font-medium">{value}</span>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                </div>
                                            )}

                                            {/* Safety Envelope & Evidence */}
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                {/* Safety Envelope */}
                                                {parsedPlan.safety_envelope && (
                                                    <div className="bg-red-50/30 border border-red-100 rounded-xl p-5 shadow-sm">
                                                        <h3 className="text-xs font-bold text-red-800 uppercase tracking-wide mb-4 flex items-center gap-2">
                                                            <ShieldAlert className="w-4 h-4" /> Safety Envelope
                                                        </h3>
                                                        <div className="space-y-4">
                                                            {parsedPlan.safety_envelope.forbidden_content && parsedPlan.safety_envelope.forbidden_content.length > 0 && (
                                                                <div>
                                                                    <span className="text-xs font-bold text-red-700 block mb-2">Forbidden Content</span>
                                                                    <ul className="space-y-1.5">
                                                                        {parsedPlan.safety_envelope.forbidden_content.map((item, i) => (
                                                                            <li key={i} className="text-xs text-gray-700 flex items-start gap-1.5">
                                                                                <AlertTriangle className="w-3 h-3 text-red-400 mt-0.5 shrink-0" />
                                                                                {item}
                                                                            </li>
                                                                        ))}
                                                                    </ul>
                                                                </div>
                                                            )}
                                                            {parsedPlan.safety_envelope.special_conditions && parsedPlan.safety_envelope.special_conditions.length > 0 && (
                                                                <div>
                                                                    <span className="text-xs font-bold text-red-700 block mb-2">Special Conditions</span>
                                                                    <ul className="space-y-1.5">
                                                                        {parsedPlan.safety_envelope.special_conditions.map((item, i) => (
                                                                            <li key={i} className="text-xs text-gray-700 flex items-start gap-1.5">
                                                                                <span className="block w-1 h-1 rounded-full bg-red-400 mt-1.5 shrink-0"></span>
                                                                                {item}
                                                                            </li>
                                                                        ))}
                                                                    </ul>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}

                                                {/* Evidence Anchors */}
                                                <div className="bg-blue-50/30 border border-blue-100 rounded-xl p-5 shadow-sm">
                                                    <h3 className="text-xs font-bold text-blue-800 uppercase tracking-wide mb-4 flex items-center gap-2">
                                                        <BookOpen className="w-4 h-4" /> Evidence Anchors
                                                    </h3>
                                                    <div className="space-y-3">
                                                        {parsedPlan.evidence_anchors?.map((anchor, i) => (
                                                            <div key={i} className="bg-white p-3 rounded border border-blue-100 shadow-sm">
                                                                <div className="text-xs font-bold text-gray-800 mb-1">{anchor.source}</div>
                                                                <div className="text-xs text-gray-600 italic">"{anchor.note}"</div>
                                                            </div>
                                                        ))}
                                                        {(!parsedPlan.evidence_anchors || parsedPlan.evidence_anchors.length === 0) && (
                                                            <p className="text-xs text-gray-400 italic">No evidence anchors cited.</p>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>

                                            {/* Critic Rubrics */}
                                            {parsedPlan.critic_rubrics && (
                                                <div className="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
                                                    <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-4 flex items-center gap-2">
                                                        <CheckCircle className="w-4 h-4" /> Evaluation Rubrics
                                                    </h3>
                                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                                        {Object.entries(parsedPlan.critic_rubrics).map(([category, items], i) => (
                                                            <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                                                                <h4 className="text-[11px] font-bold text-gray-700 uppercase mb-2 border-b border-gray-200 pb-1">
                                                                    {category.replace(/_/g, ' ')}
                                                                </h4>
                                                                <ul className="space-y-1.5">
                                                                    {items?.map((item: string, idx: number) => (
                                                                        <li key={idx} className="text-[10px] text-gray-600 leading-tight flex items-start gap-1">
                                                                            <span className="text-gray-400">•</span>
                                                                            {item}
                                                                        </li>
                                                                    ))}
                                                                </ul>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                        </>
                                    )}
                                </div>
                            )}

                            {activeTab === 'critic' && (
                                <div className="space-y-6 animate-in fade-in duration-500">
                                    {!critiqueDocument ? (
                                        <div className="bg-white border border-gray-200 rounded-lg p-6 shadow-sm">
                                            <div className="flex items-center gap-3 mb-4 text-gray-400">
                                                <BrainCircuit className="w-5 h-5" />
                                                <h3 className="font-semibold">Critic Agent Review</h3>
                                            </div>
                                            <div className="space-y-4 text-sm">
                                                <p className="text-gray-400 italic">Waiting for critique...</p>
                                                <p className="text-xs text-gray-400">The 3-agent critic (Safety, Clinical Accuracy, Tone/Empathy) will evaluate the draft once it's ready.</p>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
                                            <div className="flex items-center justify-between mb-4">
                                                <div className="flex items-center gap-3 text-orange-600">
                                                    <BrainCircuit className="w-5 h-5" />
                                                    <h3 className="font-semibold">Critic Agent Review</h3>
                                                </div>
                                                <span className="text-xs px-2 py-1 bg-orange-50 text-orange-700 border border-orange-100 rounded-full font-medium">
                                                    Iteration {critiqueDocument.iteration}
                                                </span>
                                            </div>
                                            <div className="prose prose-sm max-w-none text-gray-700">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                    {critiqueDocument.content}
                                                </ReactMarkdown>
                                            </div>
                                            <div className="mt-4 pt-4 border-t border-gray-100 text-xs text-gray-400">
                                                Generated at {critiqueDocument.timestamp}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
