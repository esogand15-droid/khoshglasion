import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles } from "lucide-react";
import api from "../services/api";
import { useAuth } from "../stores/auth";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";


export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const setAuth = useAuth((s) => s.setAuth);
  const navigate = useNavigate();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      const { data } = await api.post("/api/auth/login", { username, password });
      setAuth(data.access_token, data.username, data.role);
      navigate("/");
    } catch (err: any) {
      setError(err.response?.data?.detail || "ورود انجام نشد");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative grid min-h-dvh place-items-center overflow-hidden bg-background px-4">
      <div className="pointer-events-none absolute inset-0 bg-grid opacity-50 mask-radial" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_at_top,oklch(from_var(--brand)_l_c_h/28%),transparent_70%)]" />
      <Card className="relative w-full max-w-md border-border/80 bg-card/90 shadow-2xl backdrop-blur">
        <CardHeader>
          <div className="mb-3 flex size-11 items-center justify-center rounded-2xl bg-brand text-brand-foreground">
            <Sparkles className="size-5" />
          </div>
          <CardTitle>ورود به خوشگلاسیون</CardTitle>
          <CardDescription>پست‌های کانال همین‌جا آرایش می‌شوند. عدد و رتبه دست نمی‌خورند.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="نام کاربری">
              <Input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </Field>
            <Field label="رمز عبور">
              <PasswordInput autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            {error && <Alert variant="destructive">{error}</Alert>}
            <Button type="submit" variant="brand" className="w-full" loading={loading}>ورود</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
