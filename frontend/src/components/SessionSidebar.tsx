import React, { useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { Plus, MessageSquare, Trash2, LogOut, ChevronLeft, ChevronRight, Menu, PanelLeft } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';

interface Session {
    id: string;
    title: string;
    updated_at: string;
}

interface SessionSidebarProps {
    currentSessionId?: string | null;
    onSelectSession: (id: string) => void;
    onNewChat: () => void;
    isOpen: boolean;
    toggleSidebar: () => void;
}

export function SessionSidebar({
    currentSessionId,
    onSelectSession,
    onNewChat,
    isOpen,
    toggleSidebar
}: SessionSidebarProps) {
    const { user, signOut, getToken } = useAuth();
    const [sessions, setSessions] = useState<Session[]>([]);
    const [loading, setLoading] = useState(true);

    // Fetch sessions on mount
    useEffect(() => {
        fetchSessions();
    }, [user]);

    const fetchSessions = async () => {
        if (!user) return;
        try {
            setLoading(true);
            const token = await getToken();
            // For now, API doesn't require token, will update later
            // But we should send user_id header temporarily as per my backend implementation
            const response = await fetch('http://localhost:8000/api/sessions', {
                headers: {
                    'user-id': user.uid // Temporary placeholder auth
                }
            });
            if (response.ok) {
                const data = await response.json();
                setSessions(data);
            }
        } catch (error) {
            console.error("Failed to fetch sessions", error);
        } finally {
            setLoading(false);
        }
    };

    const deleteSession = async (e: React.MouseEvent, sessionId: string) => {
        e.stopPropagation(); // Prevent selecting session when deleting
        if (!confirm('Are you sure you want to delete this chat?')) return;

        try {
            if (!user) return;
            await fetch(`http://localhost:8000/api/sessions/${sessionId}`, {
                method: 'DELETE',
                headers: {
                    'user-id': user.uid
                }
            });
            setSessions(prev => prev.filter(s => s.id !== sessionId));
            if (currentSessionId === sessionId) {
                onNewChat();
            }
        } catch (error) {
            console.error("Failed to delete session", error);
        }
    };

    // Group sessions by date (Today, Yesterday, Previous 7 Days, Older) - Simple version for now

    if (!isOpen) {
        return (
            <div className="h-full bg-zinc-50 border-r border-gray-200 flex flex-col items-center py-4 w-14 transition-all duration-300">
                <button
                    onClick={toggleSidebar}
                    className="p-2 rounded-lg hover:bg-gray-200 text-gray-500 hover:text-gray-900 transition-colors mb-4"
                >
                    <PanelLeft className="w-5 h-5" />
                </button>
                <button
                    onClick={onNewChat}
                    className="p-2 rounded-lg bg-gray-200 text-gray-500 hover:bg-gray-300 hover:text-gray-600 transition-colors mb-4 shadow-sm"
                    title="New Chat"
                >
                    <Plus className="w-5 h-5" />
                </button>
            </div>
        );
    }

    return (
        <div className="h-full w-64 bg-zinc-50 border-r border-gray-200 flex flex-col transition-all duration-300">
            {/* Header */}
            <div className="p-4 flex items-center justify-between">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-zinc-900 text-white shadow-sm">
                    <span className="font-bold text-lg font-serif">C</span>
                </div>
                <button
                    onClick={toggleSidebar}
                    className="p-2 rounded-lg hover:bg-gray-200 text-gray-500 hover:text-gray-900 transition-colors"
                    title="Close Sidebar"
                >
                    <PanelLeft className="w-5 h-5" />
                </button>
            </div>

            {/* New Chat Button (Prominent) */}
            <div className="px-3 mb-2">
                <button
                    onClick={onNewChat}
                    className="w-full flex items-center gap-3 px-3 py-3 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 transition-all text-sm text-gray-700 shadow-sm"
                >
                    <Plus className="w-4 h-4" />
                    <span>New chat</span>
                </button>
            </div>

            {/* Session List */}
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1 scrollbar-thin scrollbar-thumb-gray-300">
                <div className="text-xs font-medium text-gray-400 px-3 py-2 uppercase tracking-wider">Recents</div>
                {loading ? (
                    <div className="px-3 text-xs text-gray-400">Loading...</div>
                ) : sessions.length === 0 ? (
                    <div className="px-3 text-xs text-gray-400 italic">No history yet.</div>
                ) : (
                    sessions.map(session => (
                        <div
                            key={session.id}
                            onClick={() => onSelectSession(session.id)}
                            className={`group flex items-center justify-between px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-all ${currentSessionId === session.id
                                ? 'bg-gray-200 text-gray-900 shadow-sm font-medium'
                                : 'text-gray-600 hover:bg-gray-200/50 hover:text-gray-900'
                                }`}
                        >
                            <div className="flex items-center gap-3 overflow-hidden">
                                <MessageSquare className={`w-4 h-4 flex-shrink-0 ${currentSessionId === session.id ? 'text-blue-600' : 'text-gray-400'}`} />
                                <span className="truncate">{session.title}</span>
                            </div>

                            {/* Delete button only visible on hover (or if active) */}
                            <button
                                onClick={(e) => deleteSession(e, session.id)}
                                className={`opacity-0 group-hover:opacity-100 p-1 hover:text-red-500 transition-all text-gray-400 ${currentSessionId === session.id ? 'opacity-100' : ''
                                    }`}
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    ))
                )}
            </div>

            {/* User Footer */}
            <div className="p-4 border-t border-gray-200 bg-zinc-50">
                <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-gray-200 cursor-pointer transition-colors group">
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-xs font-medium text-white shadow-sm">
                        {user?.email?.[0].toUpperCase() || 'U'}
                    </div>
                    <div className="flex-1 overflow-hidden">
                        <div className="text-sm font-medium text-gray-900 truncate">{user?.displayName || 'User'}</div>
                        <div className="text-xs text-gray-500 truncate">{user?.email}</div>
                    </div>
                    <button
                        onClick={() => signOut()}
                        className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-white hover:shadow-sm rounded-md transition-all text-gray-400 hover:text-gray-900"
                        title="Sign Out"
                    >
                        <LogOut className="w-4 h-4" />
                    </button>
                </div>
            </div>
        </div>
    );
}
