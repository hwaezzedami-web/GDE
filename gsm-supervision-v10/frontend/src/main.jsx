import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { Spinner } from './components/ui';
import { AuthProvider, useAuth } from './lib/auth';
import AdminPage from './pages/AdminPage';
import AlarmsPage from './pages/AlarmsPage';
import DashboardPage from './pages/DashboardPage';
import { ChangePasswordPage, LoginPage } from './pages/LoginPage';
import MapPage from './pages/MapPage';
import ReferencePage from './pages/ReferencePage';
import '@fontsource/atkinson-hyperlegible-next/400.css';
import '@fontsource/atkinson-hyperlegible-next/700.css';
import './styles.css';

function App() {
  const { user, ready, isSupervisor } = useAuth();
  if (!ready) return <Spinner label="Initialisation…" />;
  if (!user) return <LoginPage />;
  if (user.must_change_password) return <ChangePasswordPage forced />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<MapPage />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="alarms" element={<AlarmsPage />} />
        <Route path="referentiel" element={<ReferencePage />} />
        <Route path="password" element={<ChangePasswordPage />} />
        {isSupervisor && <Route path="admin" element={<AdminPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider><App /></AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
