import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Layout from "./layouts/Layout";
import Dashboard from "./pages/Dashboard";
import Channels from "./pages/Channels";
import Messages from "./pages/Messages";
import Emojis from "./pages/Emojis";
import Styles from "./pages/Styles";
import Preview from "./pages/Preview";
import Settings from "./pages/Settings";
import Health from "./pages/Health";
import { useAuth } from "./stores/auth";

function Protected({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="channels" element={<Channels />} />
        <Route path="messages" element={<Messages />} />
        <Route path="emojis" element={<Emojis />} />
        <Route path="styles" element={<Styles />} />
        <Route path="preview" element={<Preview />} />
        <Route path="settings" element={<Settings />} />
        <Route path="health" element={<Health />} />
      </Route>
    </Routes>
  );
}
