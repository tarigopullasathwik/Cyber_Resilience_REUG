import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import CommandCenter from "./pages/CommandCenter";
import Datasets from "./pages/Datasets";
import Preprocessing from "./pages/Preprocessing";
import Models from "./pages/Models";
import UnknownAttacks from "./pages/UnknownAttacks";
import ThreatIntelligence from "./pages/ThreatIntelligence";
import Containment from "./pages/Containment";
import Resources from "./pages/Resources";
import Analytics from "./pages/Analytics";
import Reports from "./pages/Reports";
import Documentation from "./pages/Documentation";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<CommandCenter />} />
        <Route path="datasets" element={<Datasets />} />
        <Route path="preprocessing" element={<Preprocessing />} />
        <Route path="models" element={<Models />} />
        <Route path="unknown" element={<UnknownAttacks />} />
        <Route path="threats" element={<ThreatIntelligence />} />
        <Route path="containment" element={<Containment />} />
        <Route path="resources" element={<Resources />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="reports" element={<Reports />} />
        <Route path="documentation" element={<Documentation />} />
      </Route>
    </Routes>
  );
}
