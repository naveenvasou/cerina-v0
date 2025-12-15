import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChatSidebar } from './ChatSidebar';
import { Canvas } from './Canvas';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { type Message, type DraftVersion, type CritiqueDocument, type AgentMemory } from '../types';
import { useAuth } from '../contexts/AuthContext';
import { Loader2 } from 'lucide-react';

interface DashboardProps {
    currentSessionId?: string | null;
}

export function Dashboard({ currentSessionId }: DashboardProps) {
    const navigate = useNavigate();
    const { user, getToken } = useAuth();
    const [messages, setMessages] = useState<Message[]>([
        {
            id: 1,
            role: 'system',
            content: 'System initialized.',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            type: 'log'
        }
    ]);
    const [socket, setSocket] = useState<WebSocket | null>(null);
    const [isConnected, setIsConnected] = useState(false);

    // Track which session we've loaded history for (to prevent overwriting real-time messages)
    const loadedSessionRef = React.useRef<string | null>(null);

    // Track seen event IDs to prevent duplicates when history and real-time overlap
    const seenIdsRef = React.useRef<Set<string>>(new Set());

    // State for Canvas
    const [plan, setPlan] = useState<string>("");
    const [draft, setDraft] = useState<string>("");

    // State for Agent Memories (for Memory popup)
    const [agentMemories, setAgentMemories] = useState<Record<string, AgentMemory>>({});

    // State for Critique-Revision Loop
    const [critiqueDocument, setCritiqueDocument] = useState<CritiqueDocument | null>(null);
    const [critiqueVersions, setCritiqueVersions] = useState<CritiqueDocument[]>([]);
    const [currentCritiqueIteration, setCurrentCritiqueIteration] = useState<number>(1);
    const [draftVersions, setDraftVersions] = useState<DraftVersion[]>([]);
    const [currentDraftVersion, setCurrentDraftVersion] = useState<number>(1);
    const [reflectionIteration, setReflectionIteration] = useState<number>(0);

    // State for Human-in-the-Loop Plan Approval
    const [pendingApproval, setPendingApproval] = useState<{
        isOpen: boolean;
        planJson: string;
        userPreview: string;
        workflowRunId?: string;
    }>({ isOpen: false, planJson: '', userPreview: '' });

    // Track current workflow run ID for HITL resume
    const currentWorkflowRunRef = React.useRef<string | null>(null);

    // ==========================================================================
    // HISTORY LOADING: Fetch from /chat-history endpoint on session load
    // This is ONLY called on page load/refresh, NOT during active streaming
    // ==========================================================================
    useEffect(() => {
        if (!currentSessionId || !user) return;

        // Skip if we already loaded this session's history
        if (loadedSessionRef.current === currentSessionId) return;

        const fetchHistory = async () => {
            try {
                const headers = { 'user-id': user.uid };

                // Single endpoint call - returns unified chat history in display order
                const res = await fetch(
                    `http://localhost:8000/api/sessions/${currentSessionId}/chat-history`,
                    { headers }
                );

                if (!res.ok) {
                    console.error('Failed to fetch chat history:', res.status);
                    return;
                }

                const history = await res.json();

                // Direct mapping - /chat-history response matches frontend Message type!
                const chatHistory: Message[] = history.map((item: any) => {
                    // Track seen IDs for deduplication
                    if (item.id) {
                        seenIdsRef.current.add(item.id);
                    }

                    // Map backend item_type to frontend type
                    // Backend: tool_call, tool_result, user_message, message, thought, artifact, etc.
                    // Frontend: tool, text, thought, artifact, agent_start, critique, log, etc.
                    const mapItemType = (itemType: string): string => {
                        switch (itemType) {
                            case 'tool_call':
                            case 'tool_result':
                                return 'tool';
                            case 'user_message':
                            case 'message':
                                return 'text';
                            case 'critique_document':
                                return 'critique';
                            case 'draft_updated':
                                return 'artifact';
                            default:
                                return itemType; // thought, artifact, agent_start, etc.
                        }
                    };

                    // For tool_result, we need to mark it as completed
                    const toolStatus = item.item_type === 'tool_result' ? 'completed' :
                        item.item_type === 'tool_call' ? 'running' :
                            item.tool_status;

                    return {
                        id: item.id,
                        role: item.role as 'user' | 'assistant' | 'agent' | 'system',
                        content: item.content,
                        agentName: item.agent_name,
                        timestamp: new Date(item.created_at).toLocaleTimeString([], {
                            hour: '2-digit', minute: '2-digit'
                        }),
                        type: mapItemType(item.item_type),
                        toolName: item.tool_name,
                        toolArgs: item.tool_args,
                        toolOutput: item.tool_output,
                        toolStatus: toolStatus,
                        artifactType: item.artifact_type,
                        artifactTitle: item.artifact_title,
                        iteration: item.iteration,
                        version: item.version,
                        isStreaming: false  // History items are never streaming
                    };
                });

                if (chatHistory.length > 0) {
                    setMessages(chatHistory);
                } else {
                    setMessages([{
                        id: Date.now(),
                        role: 'system',
                        content: 'Session started.',
                        timestamp: new Date().toLocaleTimeString(),
                        type: 'log'
                    }]);
                }

                // === Restore Canvas State from history artifacts ===
                const artifacts = history.filter((item: any) => item.item_type === 'artifact');

                // Plan
                const planArtifact = artifacts.find((a: any) =>
                    a.artifact_type === 'plan' || a.artifact_type === 'clinical_protocol'
                );
                if (planArtifact) {
                    setPlan(planArtifact.content);
                }

                // Draft versions
                const draftItems = artifacts
                    .filter((a: any) => ['draft', 'draft_revision', 'cbt_exercise'].includes(a.artifact_type))
                    .sort((a: any, b: any) => a.sequence - b.sequence);

                if (draftItems.length > 0) {
                    const versions: DraftVersion[] = draftItems.map((art: any, idx: number) => ({
                        version: art.version || (idx + 1),
                        content: art.content,
                        timestamp: new Date(art.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                        status: art.artifact_type === 'cbt_exercise' ? 'final' :
                            art.artifact_type === 'draft_revision' ? 'revised' : 'draft',
                        iteration: art.iteration || 0,
                        changes: art.artifact_title
                    }));
                    setDraftVersions(versions);
                    setDraft(draftItems[draftItems.length - 1].content);
                    setCurrentDraftVersion(versions[versions.length - 1].version);
                }

                // Critique versions
                const critiqueItems = artifacts
                    .filter((a: any) => ['critique', 'critique_document'].includes(a.artifact_type))
                    .sort((a: any, b: any) => a.sequence - b.sequence);

                if (critiqueItems.length > 0) {
                    const critiques: CritiqueDocument[] = critiqueItems.map((art: any, idx: number) => ({
                        content: art.content,
                        iteration: art.iteration || (idx + 1),
                        timestamp: new Date(art.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    }));
                    setCritiqueVersions(critiques);
                    setCritiqueDocument(critiques[critiques.length - 1]);
                    setCurrentCritiqueIteration(critiques[critiques.length - 1].iteration);
                    setReflectionIteration(critiques[critiques.length - 1].iteration);
                }

                // Mark this session as loaded
                loadedSessionRef.current = currentSessionId;

                // === Restore HITL Pending Approval State ===
                try {
                    const hitlRes = await fetch(
                        `http://localhost:8000/api/sessions/${currentSessionId}/hitl-status`,
                        { headers }
                    );
                    if (hitlRes.ok) {
                        const hitlStatus = await hitlRes.json();
                        if (hitlStatus.hitl_pending) {
                            setPendingApproval({
                                isOpen: true,
                                workflowRunId: hitlStatus.workflow_run_id,
                                userPreview: 'Plan ready for review'
                            });
                        }
                    }
                } catch (hitlErr) {
                    console.error("Failed to check HITL status:", hitlErr);
                }

            } catch (err) {
                console.error("Failed to load session history:", err);
            }
        };

        fetchHistory();
    }, [currentSessionId, user]);

    useEffect(() => {
        // wait for session ID if expected
        // For now, let's connect immediately but user might want to select a session first
        // If currentSessionId changes, reconnect

        // Construct URL
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let url = `${protocol}//localhost:8000/ws/chat`;

        const params = new URLSearchParams();
        if (currentSessionId) params.append('session_id', currentSessionId);
        if (user) params.append('user_id', user.uid);

        if (params.toString()) {
            url += `?${params.toString()}`;
        }

        const ws = new WebSocket(url);

        ws.onopen = () => {
            console.log('Connected to WebSocket');
            setIsConnected(true);
            // Only clear messages if switching sessions, handled by parent usually
            if (currentSessionId) {
                // If switching session, backend might send history? 
                // For now assume backend sends history on connect or we fetch it via REST
            }
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'session_created') {
                    navigate(`/c/${data.session_id}`);
                    return;
                }

                // =================================================
                // DEDUPLICATION: Skip if we've already seen this ID
                // This prevents duplicates when history and real-time overlap
                // =================================================
                if (data.id && seenIdsRef.current.has(data.id)) {
                    return; // Skip duplicate
                }
                if (data.id) {
                    seenIdsRef.current.add(data.id);
                }

                const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                // Helper: Mark any streaming message as complete
                const finalizeStreaming = () => {
                    setMessages(prev => prev.map(msg =>
                        msg.isStreaming ? { ...msg, isStreaming: false } : msg
                    ));
                };

                // For non-chunk events (except message_end which handles its own finalization), finalize any streaming message first
                if (data.type !== 'thought_chunk' && data.type !== 'message_chunk' && data.type !== 'message_end') {
                    finalizeStreaming();
                }

                // Handle message_end: explicitly finalize streaming messages
                if (data.type === 'message_end') {
                    finalizeStreaming();
                    return; // Nothing else to do for this event
                }

                if (data.type === 'status') {
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'system',
                        content: data.content,
                        agentName: data.agent,
                        timestamp: timestamp,
                        type: 'log'
                    }]);
                } else if (data.type === 'message') {
                    // Direct response from Router (conversational layer)
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'assistant',
                        content: data.content,
                        agentName: 'Cerina',
                        timestamp: timestamp,
                        type: 'text'
                    }]);
                } else if (data.type === 'thought') {
                    // Complete thought (used for non-streaming or final thought)
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'agent',
                        content: data.content,
                        agentName: data.agent || 'Planner',
                        timestamp: timestamp,
                        type: 'thought'
                    }]);
                } else if (data.type === 'thought_chunk') {
                    // Streaming thought chunk
                    setMessages(prev => {
                        const lastIdx = prev.length - 1;
                        const lastMsg = prev[lastIdx];

                        // If strictly continuing a streaming THOUGHT
                        if (lastMsg && lastMsg.type === 'thought' && lastMsg.isStreaming) {
                            const updated = [...prev];
                            updated[lastIdx] = { ...lastMsg, content: lastMsg.content + data.content };
                            return updated;
                        }

                        // Otherwise, effectively "finalize" others by creating new
                        const closedPrev = prev.map(m => m.isStreaming ? { ...m, isStreaming: false } : m);

                        return [...closedPrev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: data.agent || 'Planner',
                            timestamp: timestamp,
                            type: 'thought',
                            isStreaming: true
                        }];
                    });
                } else if (data.type === 'message_chunk') {
                    // Streaming text chunk
                    setMessages(prev => {
                        const lastIdx = prev.length - 1;
                        const lastMsg = prev[lastIdx];

                        // If strictly continuing a streaming TEXT
                        if (lastMsg && lastMsg.type === 'text' && lastMsg.isStreaming) {
                            const updated = [...prev];
                            updated[lastIdx] = { ...lastMsg, content: lastMsg.content + data.content };
                            return updated;
                        }

                        // Otherwise, finalize any others and start new
                        const closedPrev = prev.map(m => m.isStreaming ? { ...m, isStreaming: false } : m);

                        return [...closedPrev, {
                            id: Date.now(),
                            role: 'assistant',
                            content: data.content,
                            agentName: data.agent || 'Planner',
                            timestamp: timestamp,
                            type: 'text',
                            isStreaming: true
                        }];
                    });
                } else if (data.type === 'agent_start') {
                    // Agent invocation - prominent display
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'agent',
                        content: data.content,
                        agentName: data.agent,
                        timestamp: timestamp,
                        type: 'agent_start'
                    }]);
                } else if (data.type === 'tool_call') {
                    // Tool is starting to execute - add new tool message
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'agent',
                        content: `Calling tool: ${data.tool_name}`,
                        agentName: data.agent || 'Planner',
                        timestamp: timestamp,
                        type: 'tool',
                        toolName: data.tool_name,
                        toolArgs: data.tool_args,
                        toolStatus: 'running'
                    }]);
                } else if (data.type === 'tool_result') {
                    // Tool finished - UPDATE the existing tool message instead of adding new
                    setMessages(prev => {
                        // Find the most recent tool message with matching toolName that is still running
                        const lastIndex = [...prev].reverse().findIndex(
                            msg => msg.type === 'tool' &&
                                msg.toolName === data.tool_name &&
                                msg.toolStatus === 'running'
                        );

                        if (lastIndex !== -1) {
                            const actualIndex = prev.length - 1 - lastIndex;
                            const updated = [...prev];
                            updated[actualIndex] = {
                                ...updated[actualIndex],
                                toolOutput: data.tool_output,
                                toolStatus: 'completed'
                            };
                            return updated;
                        }

                        // Fallback: add as new message if no matching tool_call found
                        return [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: `Tool completed: ${data.tool_name}`,
                            agentName: data.agent || 'Planner',
                            timestamp: timestamp,
                            type: 'tool',
                            toolName: data.tool_name,
                            toolOutput: data.tool_output,
                            toolStatus: 'completed'
                        }];
                    });
                } else if (data.type === 'artifact') {
                    // Final artifact - could be plan, draft, critique, or other
                    if (data.artifact_type === 'clinical_protocol') {
                        setPlan(data.content);
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: 'Planner',
                            timestamp: timestamp,
                            type: 'artifact',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || 'Clinical Protocol'
                        }]);
                    } else if (data.artifact_type === 'critique_document') {
                        // Critique document - update canvas critique panel ONLY (not draft!)
                        setCritiqueDocument({
                            content: data.content,
                            iteration: data.iteration || reflectionIteration || 1,
                            timestamp: timestamp
                        });
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: 'Critic',
                            timestamp: timestamp,
                            type: 'critique',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || 'Critique Report',
                            iteration: data.iteration || reflectionIteration || 1
                        }]);
                    } else if (data.artifact_type === 'draft_revision') {
                        // Draft revision from reviser - update draft and version history
                        const newVersion: DraftVersion = {
                            version: data.version || (draftVersions.length + 1),
                            content: data.content,
                            timestamp: timestamp,
                            status: 'revised',
                            iteration: reflectionIteration
                        };
                        setDraftVersions(prev => [...prev, newVersion]);
                        setDraft(data.content);
                        setCurrentDraftVersion(newVersion.version);
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: 'Reviser',
                            timestamp: timestamp,
                            type: 'artifact',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || `Revised Draft (v${newVersion.version})`
                        }]);
                    } else if (data.artifact_type === 'cbt_exercise') {
                        // Final synthesized exercise - mark as final version
                        // Use functional update to get correct version number
                        setDraftVersions(prev => {
                            const finalVersion: DraftVersion = {
                                version: prev.length + 1,
                                content: data.content,
                                timestamp: timestamp,
                                status: 'final',
                                iteration: reflectionIteration,
                                changes: 'Final presentation formatting applied'
                            };
                            setDraft(data.content);
                            setCurrentDraftVersion(finalVersion.version);
                            return [...prev, finalVersion];
                        });
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: 'Synthesizer',
                            timestamp: timestamp,
                            type: 'artifact',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || 'Final CBT Exercise',
                            actionType: 'write',
                            fileName: 'CBT_Exercise.md'
                        }]);
                    } else if (data.artifact_type === 'draft') {
                        // Initial draft from draftsman - create v1 entry
                        const initialVersion: DraftVersion = {
                            version: 1,
                            content: data.content,
                            timestamp: timestamp,
                            status: 'draft',
                            iteration: 0,
                            changes: 'Initial draft generated'
                        };
                        setDraftVersions([initialVersion]); // Reset to just v1
                        setDraft(data.content);
                        setCurrentDraftVersion(1);
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: 'Draftsman',
                            timestamp: timestamp,
                            type: 'artifact',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || 'Initial Draft (v1)',
                            actionType: 'write',
                            fileName: 'CBT_Exercise.md'
                        }]);
                    } else {
                        // Unknown artifact type - add to messages but don't update draft/critique
                        setMessages(prev => [...prev, {
                            id: Date.now(),
                            role: 'agent',
                            content: data.content,
                            agentName: data.agent || 'Agent',
                            timestamp: timestamp,
                            type: 'artifact',
                            artifactType: data.artifact_type,
                            artifactTitle: data.artifact_title || 'Artifact'
                        }]);
                    }

                } else if (data.type === 'agent_memory') {
                    // Store agent memory for Memory popup
                    setAgentMemories(prev => ({
                        ...prev,
                        [data.agent]: {
                            agentName: data.agent,
                            messages: data.messages || [],
                            scratchpad: data.scratchpad || ''
                        }
                    }));
                } else if (data.type === 'critique_document') {
                    // Critique document from critic agent
                    setCritiqueDocument({
                        content: data.content,
                        iteration: data.iteration || 1,
                        timestamp: timestamp
                    });
                    // Also add as a message
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'agent',
                        content: data.content,
                        agentName: 'Critic',
                        timestamp: timestamp,
                        type: 'critique',
                        iteration: data.iteration
                    }]);
                } else if (data.type === 'draft_updated') {
                    // Draft version update from reviser
                    // Use functional update to get correct version number
                    setDraftVersions(prev => {
                        const newVersion: DraftVersion = {
                            version: data.version || (prev.length + 1),
                            content: data.content,
                            timestamp: timestamp,
                            status: 'revised',
                            iteration: reflectionIteration
                        };
                        setDraft(data.content);
                        setCurrentDraftVersion(newVersion.version);
                        return [...prev, newVersion];
                    });
                } else if (data.type === 'reflection_status') {
                    // Reflection loop status update
                    setReflectionIteration(data.iteration || 0);
                    setMessages(prev => [...prev, {
                        id: Date.now(),
                        role: 'system',
                        content: `Reflection: ${data.content}`,
                        agentName: data.agent,
                        timestamp: timestamp,
                        type: 'log'
                    }]);
                } else if (data.type === 'plan_pending_approval') {
                    // Human-in-the-Loop: Workflow halted for plan approval
                    console.log('📋 Plan pending approval received');
                    setPendingApproval({
                        isOpen: true,
                        planJson: data.content,
                        userPreview: data.artifact_title || '',
                        workflowRunId: currentWorkflowRunRef.current || undefined
                    });

                }
            } catch (e) {
                console.error("Error parsing WS message", e);
            }
        };

        ws.onclose = () => {
            console.log('Disconnected from WebSocket');
            setIsConnected(false);
        };

        setSocket(ws);

        return () => {
            ws.close();
        };
    }, [currentSessionId]); // Reconnect when session changes

    const sendMessage = async (text: string) => {
        if (socket && isConnected) {
            // Check if we're in pending approval mode
            // If so, treat this message as a revision request
            if (pendingApproval.isOpen) {
                // Close the approval state and send as revision
                setPendingApproval(prev => ({ ...prev, isOpen: false }));

                // Add user message to chat
                setMessages(prev => [...prev, {
                    id: Date.now(),
                    role: 'user',
                    content: text,
                    timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                }]);

                // Send as plan revision
                sendPlanDecision('revised', text);
                return;
            }

            // Normal message flow
            setMessages(prev => [...prev, {
                id: Date.now(),
                role: 'user',
                content: text,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
            }]);

            // If we have a current session, send it too
            if (currentSessionId) {
                socket.send(JSON.stringify({
                    message: text,
                    session_id: currentSessionId
                }));
            } else {
                socket.send(text);
            }
        }
    };

    // ==========================================================================
    // HITL: Plan Approval Decision Functions
    // ==========================================================================
    const sendPlanDecision = (decision: 'approved' | 'revised' | 'rejected', feedback?: string) => {
        if (socket && isConnected) {
            const message = {
                type: 'plan_decision',
                decision,
                feedback: feedback || '',
                workflow_run_id: pendingApproval.workflowRunId
            };
            console.log('📤 Sending plan decision:', message);
            socket.send(JSON.stringify(message));
        }
    };

    const handlePlanApprove = () => {
        sendPlanDecision('approved');
        setPendingApproval(prev => ({ ...prev, isOpen: false }));
        setMessages(prev => [...prev, {
            id: Date.now(),
            role: 'system',
            content: '✅ Plan approved. Proceeding to draft generation...',
            agentName: 'System',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            type: 'log'
        }]);
    };

    const handlePlanReject = () => {
        sendPlanDecision('rejected');
        setPendingApproval(prev => ({ ...prev, isOpen: false }));
        setMessages(prev => [...prev, {
            id: Date.now(),
            role: 'system',
            content: '❌ Plan rejected. Workflow terminated.',
            agentName: 'System',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            type: 'log'
        }]);
    };

    return (
        <div className="flex h-screen w-full bg-white overflow-hidden font-sans text-gray-900">
            <PanelGroup direction="horizontal">
                <Panel defaultSize={40} minSize={20} maxSize={50}>
                    <ChatSidebar
                        messages={messages}
                        onSendMessage={sendMessage}
                        isConnected={isConnected}
                        agentMemories={agentMemories}
                        pendingApproval={pendingApproval.isOpen}
                        onApprove={handlePlanApprove}
                        onReject={handlePlanReject}
                    />
                </Panel>

                <PanelResizeHandle className="w-[2px] bg-gray-200 hover:bg-blue-400 transition-colors flex items-center justify-center group z-10">
                    <div className="h-8 w-1 bg-gray-300 rounded-full group-hover:bg-blue-500 transition-colors hidden sm:block delay-150" />
                </PanelResizeHandle>

                <Panel>
                    <Canvas
                        plan={plan}
                        draft={draft}
                        critiqueDocument={critiqueDocument}
                        critiqueVersions={critiqueVersions}
                        currentCritiqueIteration={currentCritiqueIteration}
                        draftVersions={draftVersions}
                        currentDraftVersion={currentDraftVersion}
                        reflectionIteration={reflectionIteration}
                        onVersionSelect={(version: number) => {
                            const selected = draftVersions.find(v => v.version === version);
                            if (selected) {
                                setDraft(selected.content);
                                setCurrentDraftVersion(version);
                            }
                        }}
                        onCritiqueVersionSelect={(iteration: number) => {
                            const selected = critiqueVersions.find(v => v.iteration === iteration);
                            if (selected) {
                                setCritiqueDocument(selected);
                                setCurrentCritiqueIteration(iteration);
                            }
                        }}
                    />
                </Panel>

            </PanelGroup>
        </div>
    );
}
