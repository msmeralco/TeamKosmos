import { createRoot } from "react-dom/client";
import "./index.css";
import { SolMark } from "./components/SolMark";
import SolMascot from "./components/SolMascot";

createRoot(document.getElementById("root")!).render(
  <div style={{ display: "flex", gap: 24, padding: 24, alignItems: "center" }}>
    <SolMascot size={340} />
    <SolMark size={340} />
    <SolMark size={34} />
    <SolMascot size={128} />
  </div>,
);
