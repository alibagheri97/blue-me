import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "../lib/api";
import type { BrandConfig, User } from "../types";

interface AuthValue {
  user: User | null;
  brand: BrandConfig;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const fallbackBrand: BrandConfig = {
  app_name: "Blue Me",
  business_name: "Blue Me",
  tagline: "مدیریت شفاف، تصمیم‌گیری هوشمند",
  primary_color: "#2563eb",
  logo_url: null,
  locale: "en",
  timezone: "UTC",
  currency_label: "تومان",
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [brand, setBrand] = useState<BrandConfig>(fallbackBrand);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<BrandConfig>("/public/config")
      .then((config) => {
        setBrand(config);
        document.title = config.business_name;
        document.documentElement.style.setProperty("--brand", config.primary_color);
        document.documentElement.dir = ["fa", "ar", "he"].includes(config.locale) ? "rtl" : "ltr";
      })
      .catch(() => undefined);
    const token = localStorage.getItem("blue-me-token");
    if (!token) {
      setLoading(false);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => localStorage.removeItem("blue-me-token"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const expire = () => setUser(null);
    window.addEventListener("blue-me-session-expired", expire);
    return () => window.removeEventListener("blue-me-session-expired", expire);
  }, []);

  const login = async (username: string, password: string) => {
    const response = await api<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    localStorage.setItem("blue-me-token", response.access_token);
    setUser(response.user);
  };

  const logout = () => {
    localStorage.removeItem("blue-me-token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, brand, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// This hook intentionally shares the provider module so authentication state has one source of truth.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
