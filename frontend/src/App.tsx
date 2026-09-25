import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./layouts/Layout";
import Audit from "./pages/Audit";
import Automation from "./pages/Automation";
import Channels from "./pages/Channels";
import Dashboard from "./pages/Dashboard";
import Emojis from "./pages/Emojis";
import Health from "./pages/Health";
import Login from "./pages/Login";
import Messages from "./pages/Messages";
import Preview from "./pages/Preview";
import Settings from "./pages/Settings";
import Styles from "./pages/Styles";
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
        <Route path="automation" element={<Automation />} />
        <Route path="messages" element={<Messages />} />
        <Route path="emojis" element={<Emojis />} />
        <Route path="styles" element={<Styles />} />
        <Route path="preview" element={<Preview />} />
        <Route path="settings" element={<Settings />} />
        <Route path="health" element={<Health />} />
        <Route path="audit" element={<Audit />} />
      </Route>
    </Routes>
  );
}
