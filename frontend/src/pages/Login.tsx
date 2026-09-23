import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import api from "../services/api";
import { useAuth } from "../stores/auth";

export default function Login() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
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
      setErr(error.response?.data?.detail || "ورود انجام نشد. نام کاربری و رمز را دوباره بررسی کن.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-wrap">
      <aside className="login-aside">
        <div className="brand">
          <div className="mark" aria-hidden="true">خ</div>
          <div><b>خوشگلاسیون</b><span>اتاق فرمان رتبه لند</span></div>
        </div>
        <h2>وضعیت ربات، کانال و ادیت‌ها اینجاست.</h2>
        <p className="tiny">عدد ساختگی نشان داده نمی‌شود. اگر پستی پردازش نشده باشد، داشبورد خالی می‌ماند.</p>
      </aside>
      <div className="login-panel">
        <form className="card login-card" onSubmit={submit}>
          <div className="brand" style={{ marginBottom: 18 }}>
            <div className="mark" aria-hidden="true">خ</div>
            <div><h1 style={{ fontSize: 16, margin: 0 }}>ورود</h1><span>فقط ادمین پنل</span></div>
          </div>
          {err && <div className="alert danger" role="alert" tabIndex={-1} style={{ marginBottom: 12 }}>{err}</div>}
          <div className="grid">
            <label className="field">
              <span>نام کاربری</span>
              <input id="username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </label>
            <label className="field">
              <span>رمز عبور</span>
              <input id="password" name="password" autoComplete="current-password" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
          </div>
          <button className="btn" type="button" style={{ marginTop: 8 }} onClick={() => setShow((value) => !value)} aria-pressed={show}>
            <Icon name={show ? "eyeOff" : "eye"} />{show ? "پنهان کردن رمز" : "نمایش رمز"}
          </button>
          <button className="btn-gold" style={{ width: "100%", marginTop: 12 }} disabled={loading} aria-busy={loading}>{loading ? "در حال ورود..." : "ورود"}</button>
          <p className="tiny" style={{ textAlign: "center" }}>رمز اولیه همان ADMIN_SECRET روی Railway است.</p>
        </form>
      </div>
    </div>
  );
}
