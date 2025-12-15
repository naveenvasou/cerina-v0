import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useNavigate, useParams } from 'react-router-dom';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import LoginPage from './pages/LoginPage';
import { Dashboard } from './components/Dashboard';
import { SessionSidebar } from './components/SessionSidebar';
import { Loader2 } from 'lucide-react';


// --- Private Route ---


// --- Private Route ---
const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-white dark:bg-zinc-950">
        <Loader2 className="w-8 h-8 animate-spin text-zinc-400" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" />;
  }

  return <>{children}</>;
};

// --- Main Layout ---
const MainLayout = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const navigate = useNavigate();
  const { sessionId } = useParams();

  const handleNewChat = () => {
    // Create new session via API then navigate? 
    // Or just navigate to root and let Dashboard create one on first message?
    // Let's navigate to root for now
    navigate('/');
    // You might want to create a blank session ID here to allow "New Chat" entries in DB immediately
    // For now, root '/' implies new fresh state in Dashboard
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-white dark:bg-zinc-950">
      <SessionSidebar
        currentSessionId={sessionId}
        onSelectSession={(id) => navigate(`/c/${id}`)}
        onNewChat={handleNewChat}
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
      />
      <div className="flex-1 h-full overflow-hidden">
        {/* Pass Key to force remount on session change? Or just prop update */}
        <Dashboard key={sessionId || 'new'} currentSessionId={sessionId} />
      </div>
    </div>
  );
};

function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<LoginPage />} />

          <Route path="/" element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          } />

          <Route path="/c/:sessionId" element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          } />

          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}

export default App;
