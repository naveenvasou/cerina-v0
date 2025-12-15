export interface AgentMemoryMessage {
    type: string;
    content: string;
    name?: string;
    tool_calls?: any[];
    tool_call_id?: string;
}

export interface AgentMemory {
    agentName: string;
    messages: AgentMemoryMessage[];
    scratchpad: string;
}

export interface Message {
    id: number;
    role: 'system' | 'user' | 'assistant' | 'agent';
    content: string;
    timestamp: string;
    agentName?: string;
    status?: 'thinking' | 'done';
    type?: 'text' | 'thought' | 'action' | 'log' | 'tool' | 'artifact' | 'agent_start' | 'critique';
    actionType?: 'write' | 'read' | 'edit';
    fileName?: string;
    // Tool fields (unified for both call and result)
    toolName?: string;
    toolArgs?: Record<string, unknown>;
    toolOutput?: string;
    toolStatus?: 'running' | 'completed';
    artifactType?: string;
    artifactTitle?: string;
    // Streaming thought indicator
    isStreaming?: boolean;
    // Reflection loop fields
    iteration?: number;
    version?: number;
}

// Draft version for version history
export interface DraftVersion {
    version: number;
    content: string;
    timestamp: string;
    status: 'draft' | 'revised' | 'final';
    iteration?: number;
    changes?: string;
}

// Critique document structure
export interface CritiqueDocument {
    content: string;
    iteration: number;
    timestamp: string;
}
