import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { API_URL, GOOGLE_CLIENT_ID } from "@/config";

interface AuthUser {
  email: string;
  name: string;
  picture: string;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  signIn: () => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  token: null,
  loading: true,
  signIn: () => {},
  signOut: () => {},
});

export const useAuth = () => useContext(AuthContext);

/**
 * Adds JWT to fetch requests automatically.
 */
export function authFetch(
  url: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = localStorage.getItem("jwt_token");
  const headers = new Headers(options.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(url, { ...options, headers });
}

/**
 * Returns the WebSocket URL with the JWT token appended.
 */
export function getAuthWsUrl(baseWsUrl: string): string {
  const token = localStorage.getItem("jwt_token");
  if (token) {
    const separator = baseWsUrl.includes("?") ? "&" : "?";
    return `${baseWsUrl}${separator}token=${token}`;
  }
  return baseWsUrl;
}

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: Record<string, unknown>) => void;
          prompt: () => void;
          renderButton: (
            element: HTMLElement,
            config: Record<string, unknown>,
          ) => void;
          revoke: (email: string, callback: () => void) => void;
        };
      };
    };
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session from localStorage
  useEffect(() => {
    const savedToken = localStorage.getItem("jwt_token");
    const savedUser = localStorage.getItem("auth_user");
    if (savedToken && savedUser) {
      try {
        setToken(savedToken);
        setUser(JSON.parse(savedUser));
      } catch {
        localStorage.removeItem("jwt_token");
        localStorage.removeItem("auth_user");
      }
    }
    setLoading(false);
  }, []);

  // Load Google Identity Services script
  useEffect(() => {
    if (document.getElementById("google-gis-script")) return;

    const script = document.createElement("script");
    script.id = "google-gis-script";
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
  }, []);

  const handleCredentialResponse = useCallback(
    async (response: { credential: string }) => {
      try {
        const res = await fetch(`${API_URL}/auth/google`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: response.credential }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          console.error("Auth failed:", err);
          return;
        }

        const data = await res.json();
        setToken(data.token);
        setUser({
          email: data.email,
          name: data.name,
          picture: data.picture,
        });
        localStorage.setItem("jwt_token", data.token);
        localStorage.setItem(
          "auth_user",
          JSON.stringify({
            email: data.email,
            name: data.name,
            picture: data.picture,
          }),
        );
      } catch (err) {
        console.error("Auth error:", err);
      }
    },
    [],
  );

  // Initialize Google Sign-In when script loads
  useEffect(() => {
    const initGoogle = () => {
      window.google?.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: handleCredentialResponse,
        auto_select: true,
      });
    };

    // Check if already loaded
    if (window.google?.accounts) {
      initGoogle();
      return;
    }

    // Wait for script to load
    const script = document.getElementById("google-gis-script");
    if (script) {
      script.addEventListener("load", initGoogle);
      return () => script.removeEventListener("load", initGoogle);
    }
  }, [handleCredentialResponse]);

  const signIn = useCallback(() => {
    window.google?.accounts.id.prompt();
  }, []);

  const signOut = useCallback(() => {
    const email = user?.email;
    setUser(null);
    setToken(null);
    localStorage.removeItem("jwt_token");
    localStorage.removeItem("auth_user");
    if (email) {
      window.google?.accounts.id.revoke(email, () => {});
    }
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, token, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
