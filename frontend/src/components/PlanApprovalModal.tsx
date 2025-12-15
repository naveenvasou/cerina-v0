import { useState } from 'react';
import { X, Check, Edit3, XCircle, FileText, Shield, Target, BookOpen } from 'lucide-react';


interface PlanApprovalModalProps {
    isOpen: boolean;
    planJson: string;
    userPreview: string;
    /* workflowRunId?: string; */
    onApprove: () => void;
    onRevise: (feedback: string) => void;
    onReject: () => void;
    onClose: () => void;
}

interface ParsedPlan {
    exercise_type?: string;
    drafting_spec?: {
        task_constraints?: Record<string, string>;
        style_rules?: string[];
    };
    safety_envelope?: {
        forbidden_content?: string[];
        special_conditions?: string[];
    };
    critic_rubrics?: {
        safety?: string[];
        clinical_accuracy?: string[];
        usability?: string[];
    };
    evidence_anchors?: Array<{
        source: string;
        note: string;
    }>;
    user_preview?: string;
}

export function PlanApprovalModal({
    isOpen,
    planJson,
    userPreview,
    onApprove,
    onRevise,
    onReject,
    onClose
}: PlanApprovalModalProps) {
    const [showFeedback, setShowFeedback] = useState(false);
    const [feedback, setFeedback] = useState('');
    const [activeTab, setActiveTab] = useState<'overview' | 'details' | 'safety'>('overview');

    if (!isOpen) return null;

    // Parse the plan JSON
    let plan: ParsedPlan = {};
    try {
        plan = typeof planJson === 'string' ? JSON.parse(planJson) : planJson;
    } catch (e) {
        console.error('Failed to parse plan JSON:', e);
    }

    const handleReviseClick = () => {
        if (showFeedback && feedback.trim()) {
            onRevise(feedback);
            setFeedback('');
            setShowFeedback(false);
        } else {
            setShowFeedback(true);
        }
    };

    const handleApprove = () => {
        onApprove();
        onClose();
    };

    const handleReject = () => {
        onReject();
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
            <div className="bg-white rounded-2xl shadow-2xl w-[800px] max-h-[85vh] flex flex-col overflow-hidden border border-zinc-200">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200 bg-gradient-to-r from-emerald-50 to-teal-50">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
                            <FileText className="w-5 h-5 text-emerald-600" />
                        </div>
                        <div>
                            <h2 className="text-lg font-semibold text-zinc-900">Review Your Clinical Plan</h2>
                            <p className="text-sm text-zinc-500">Please review before proceeding</p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-lg hover:bg-zinc-100 text-zinc-400 hover:text-zinc-600 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* User Preview Banner */}
                {(userPreview || plan.user_preview) && (
                    <div className="px-6 py-3 bg-emerald-50 border-b border-emerald-100">
                        <p className="text-sm text-emerald-800 font-medium">
                            {userPreview || plan.user_preview}
                        </p>
                    </div>
                )}

                {/* Tabs */}
                <div className="flex gap-1 px-6 pt-4 border-b border-zinc-100">
                    {[
                        { id: 'overview', label: 'Overview', icon: Target },
                        { id: 'details', label: 'Drafting Specs', icon: BookOpen },
                        { id: 'safety', label: 'Safety & Rubrics', icon: Shield },
                    ].map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id as any)}
                            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${activeTab === id
                                    ? 'bg-white text-emerald-600 border-b-2 border-emerald-500'
                                    : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50'
                                }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto px-6 py-4">
                    {activeTab === 'overview' && (
                        <div className="space-y-4">
                            {/* Exercise Type */}
                            {plan.exercise_type && (
                                <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100">
                                    <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-2">
                                        Exercise Type
                                    </h3>
                                    <p className="text-lg font-medium text-zinc-900">{plan.exercise_type}</p>
                                </div>
                            )}

                            {/* Evidence Anchors */}
                            {plan.evidence_anchors && plan.evidence_anchors.length > 0 && (
                                <div className="p-4 bg-blue-50 rounded-xl border border-blue-100">
                                    <h3 className="text-xs font-semibold text-blue-600 uppercase tracking-wide mb-3">
                                        Evidence Base
                                    </h3>
                                    <div className="space-y-2">
                                        {plan.evidence_anchors.map((anchor, idx) => (
                                            <div key={idx} className="flex gap-2 text-sm">
                                                <span className="font-medium text-blue-700">{anchor.source}:</span>
                                                <span className="text-blue-600">{anchor.note}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'details' && (
                        <div className="space-y-4">
                            {/* Task Constraints */}
                            {plan.drafting_spec?.task_constraints && (
                                <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100">
                                    <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
                                        Task Constraints
                                    </h3>
                                    <div className="space-y-2">
                                        {Object.entries(plan.drafting_spec.task_constraints).map(([key, value]) => (
                                            <div key={key} className="flex gap-2 text-sm">
                                                <span className="font-medium text-zinc-700 capitalize">
                                                    {key.replace(/_/g, ' ')}:
                                                </span>
                                                <span className="text-zinc-600">{value}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Style Rules */}
                            {plan.drafting_spec?.style_rules && plan.drafting_spec.style_rules.length > 0 && (
                                <div className="p-4 bg-zinc-50 rounded-xl border border-zinc-100">
                                    <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-3">
                                        Style Rules
                                    </h3>
                                    <ul className="space-y-1.5">
                                        {plan.drafting_spec.style_rules.map((rule, idx) => (
                                            <li key={idx} className="flex gap-2 text-sm text-zinc-600">
                                                <span className="text-emerald-500">•</span>
                                                {rule}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {activeTab === 'safety' && (
                        <div className="space-y-4">
                            {/* Safety Envelope */}
                            {plan.safety_envelope && (
                                <div className="p-4 bg-red-50 rounded-xl border border-red-100">
                                    <h3 className="text-xs font-semibold text-red-600 uppercase tracking-wide mb-3">
                                        Safety Envelope
                                    </h3>

                                    {plan.safety_envelope.forbidden_content && (
                                        <div className="mb-3">
                                            <p className="text-xs font-medium text-red-500 mb-1.5">Forbidden Content:</p>
                                            <ul className="space-y-1">
                                                {plan.safety_envelope.forbidden_content.map((item, idx) => (
                                                    <li key={idx} className="flex gap-2 text-sm text-red-700">
                                                        <XCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                                                        {item}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}

                                    {plan.safety_envelope.special_conditions && (
                                        <div>
                                            <p className="text-xs font-medium text-amber-600 mb-1.5">Special Conditions:</p>
                                            <ul className="space-y-1">
                                                {plan.safety_envelope.special_conditions.map((cond, idx) => (
                                                    <li key={idx} className="flex gap-2 text-sm text-amber-700">
                                                        <Shield className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                                                        {cond}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Critic Rubrics */}
                            {plan.critic_rubrics && (
                                <div className="p-4 bg-purple-50 rounded-xl border border-purple-100">
                                    <h3 className="text-xs font-semibold text-purple-600 uppercase tracking-wide mb-3">
                                        Evaluation Rubrics
                                    </h3>

                                    <div className="grid grid-cols-1 gap-3">
                                        {plan.critic_rubrics.safety && (
                                            <div>
                                                <p className="text-xs font-medium text-purple-500 mb-1">Safety:</p>
                                                <ul className="space-y-0.5">
                                                    {plan.critic_rubrics.safety.map((item, idx) => (
                                                        <li key={idx} className="text-sm text-purple-700 pl-3">• {item}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        {plan.critic_rubrics.clinical_accuracy && (
                                            <div>
                                                <p className="text-xs font-medium text-purple-500 mb-1">Clinical Accuracy:</p>
                                                <ul className="space-y-0.5">
                                                    {plan.critic_rubrics.clinical_accuracy.map((item, idx) => (
                                                        <li key={idx} className="text-sm text-purple-700 pl-3">• {item}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                        {plan.critic_rubrics.usability && (
                                            <div>
                                                <p className="text-xs font-medium text-purple-500 mb-1">Usability:</p>
                                                <ul className="space-y-0.5">
                                                    {plan.critic_rubrics.usability.map((item, idx) => (
                                                        <li key={idx} className="text-sm text-purple-700 pl-3">• {item}</li>
                                                    ))}
                                                </ul>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Feedback Input (when requesting revision) */}
                {showFeedback && (
                    <div className="px-6 py-4 border-t border-zinc-200 bg-amber-50">
                        <label className="block text-sm font-medium text-amber-800 mb-2">
                            What changes would you like?
                        </label>
                        <textarea
                            value={feedback}
                            onChange={(e) => setFeedback(e.target.value)}
                            placeholder="Describe the changes you'd like to see in the plan..."
                            className="w-full h-24 px-4 py-3 text-sm border border-amber-200 rounded-xl 
                                     focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent
                                     bg-white placeholder-amber-300 text-zinc-800 resize-none"
                            autoFocus
                        />
                    </div>
                )}

                {/* Actions */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-zinc-200 bg-zinc-50">
                    <button
                        onClick={handleReject}
                        className="flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-red-600 
                                 hover:bg-red-50 rounded-lg transition-colors"
                    >
                        <XCircle className="w-4 h-4" />
                        Reject Plan
                    </button>

                    <div className="flex items-center gap-3">
                        <button
                            onClick={handleReviseClick}
                            className="flex items-center gap-2 px-5 py-2.5 text-sm font-medium 
                                     text-amber-700 bg-amber-100 hover:bg-amber-200 
                                     rounded-lg transition-colors"
                        >
                            <Edit3 className="w-4 h-4" />
                            {showFeedback ? 'Submit Revision' : 'Request Changes'}
                        </button>

                        <button
                            onClick={handleApprove}
                            className="flex items-center gap-2 px-6 py-2.5 text-sm font-semibold 
                                     text-white bg-emerald-600 hover:bg-emerald-700 
                                     rounded-lg transition-colors shadow-sm"
                        >
                            <Check className="w-4 h-4" />
                            Approve & Continue
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
