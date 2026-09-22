import { create } from "zustand";
type AuthState = { token: string | null; username: string | null; role: string | null; setAuth: (t: string, u: string, r: string) => void; logout: () => void; };
export const useAuth = create<AuthState>((set) => ({
  token: localStorage.getItem("token"),
  username: localStorage.getItem("username"),
  role: localStorage.getItem("role"),
  setAuth: (t, u, r) => { localStorage.setItem("token", t); localStorage.setItem("username", u); localStorage.setItem("role", r); set({ token: t, username: u, role: r }); },
  logout: () => { localStorage.clear(); set({ token: null, username: null, role: null }); }
}));
