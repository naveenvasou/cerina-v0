const trimTrailingSlash = (url: string) => url.replace(/\/+$/, '');

export const API_BASE_URL = trimTrailingSlash(
    import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
);

// Optional override for websocket base; falls back to API base host.
const WS_BASE = trimTrailingSlash(import.meta.env.VITE_WS_BASE_URL ?? API_BASE_URL);

export const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

export const wsUrl = (path: string) => {
    const base = new URL(WS_BASE);
    const protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${base.host}${path}`;
};

