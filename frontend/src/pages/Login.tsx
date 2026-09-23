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
    } catch (error: any) {
      setErr(error.response?.data?.detail || "ورود انجام نشد");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 18 }}>
          <div className="mark">خ</div>
          <div><b>خوشگلاسیون</b><span>ورود به اتاق فرمان</span></div>
        </div>
        <div className="grid">
          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="نام کاربری" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="رمز عبور" />
        </div>
        {err && <div className="alert danger" style={{ marginTop: 12 }}>{err}</div>}
        <button className="btn-gold" style={{ width: "100%", marginTop: 16 }} disabled={loading}>{loading ? "در حال ورود..." : "ورود"}</button>
        <p className="tiny" style={{ textAlign: "center" }}>رمز اولیه همان ADMIN_SECRET روی Railway است.</p>
      </form>
    </div>
  );
}
