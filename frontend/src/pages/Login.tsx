import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "../services/api";
import { useAuth } from "../stores/auth";

export default function Login() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuth((s) => s.setAuth);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr("");
    try {
      const { data } = await api.post("/api/auth/login", { username, password });
      setAuth(data.access_token, data.username, data.role);
      navigate("/");
    } catch (e: any) {
      setErr(e.response?.data?.detail || "خطا در ورود");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen gradient-bg flex items-center justify-center p-6">
      <form onSubmit={submit} className="glass-strong rounded-[24px] p-8 w-full max-w-[400px] flex flex-col gap-5">
        <div className="text-center">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-500 to-blue-500 flex items-center justify-center text-2xl mx-auto">👑</div>
          <h1 className="text-xl font-bold text-white mt-3">خوشگلاسیون</h1>
          <p className="text-sm text-white/50 mt-1">ورود به پنل مدیریت</p>
        </div>
        <div className="flex flex-col gap-3">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="نام کاربری" className="glass rounded-xl px-4 py-3 text-sm bg-transparent outline-none placeholder:text-white/30 text-white" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="رمز عبور" className="glass rounded-xl px-4 py-3 text-sm bg-transparent outline-none placeholder:text-white/30 text-white" />
        </div>
        {err && <div className="text-xs text-red-400 bg-red-500/10 rounded-xl px-3 py-2">{err}</div>}
        <button disabled={loading} className="bg-gradient-to-r from-violet-600 to-blue-600 rounded-xl py-3 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
          {loading ? "در حال ورود..." : "ورود"}
        </button>
        <p className="text-[11px] text-white/30 text-center">پیش‌فرض: admin / مقدار ADMIN_SECRET</p>
      </form>
    </div>
  );
}
