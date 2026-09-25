import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./layouts/Layout";
import Login from "./pages/Login";
import { PageSkeleton } from "@/components/ui/page-state";
import { useAuth } from "./stores/auth";

const Audit = lazy(() => import("./pages/Audit"));
const Automation = lazy(() => import("./pages/Automation"));
const Channels = lazy(() => import("./pages/Channels"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Emojis = lazy(() => import("./pages/Emojis"));
const Health = lazy(() => import("./pages/Health"));
const Messages = lazy(() => import("./pages/Messages"));
const Preview = lazy(() => import("./pages/Preview"));
const Settings = lazy(() => import("./pages/Settings"));
const Styles = lazy(() => import("./pages/Styles"));

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
        <Route index element={<Suspense fallback={<PageSkeleton />}><Dashboard /></Suspense>} />
        <Route path="channels" element={<Suspense fallback={<PageSkeleton variant="form" />}><Channels /></Suspense>} />
        <Route path="automation" element={<Suspense fallback={<PageSkeleton />}><Automation /></Suspense>} />
        <Route path="messages" element={<Suspense fallback={<PageSkeleton variant="table" />}><Messages /></Suspense>} />
        <Route path="emojis" element={<Suspense fallback={<PageSkeleton variant="form" />}><Emojis /></Suspense>} />
        <Route path="styles" element={<Suspense fallback={<PageSkeleton variant="form" />}><Styles /></Suspense>} />
        <Route path="preview" element={<Suspense fallback={<PageSkeleton variant="form" />}><Preview /></Suspense>} />
        <Route path="settings" element={<Suspense fallback={<PageSkeleton variant="form" />}><Settings /></Suspense>} />
        <Route path="health" element={<Suspense fallback={<PageSkeleton />}><Health /></Suspense>} />
        <Route path="audit" element={<Suspense fallback={<PageSkeleton variant="table" />}><Audit /></Suspense>} />
      </Route>
    </Routes>
  );
}
