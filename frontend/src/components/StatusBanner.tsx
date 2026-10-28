import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthResponse } from "../api/types";

const POLL_MS = 10000;

export function StatusBanner() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .health()
        .then((h) => {
          if (alive) {
            setHealth(h);
            setFailed(false);
          }
        })
        .catch(() => {
          if (alive) setFailed(true);
        });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  if (failed) {
    return <div className="banner banner-error">Serveur PixelForge injoignable.</div>;
  }
  if (!health || health.comfy.ok) return null;

  const { comfy_reachable, missing_nodes, missing_models } = health.comfy;
  return (
    <div className="banner banner-warn" role="alert">
      {!comfy_reachable ? (
        <strong>ComfyUI est injoignable. Lancez-le puis patientez quelques secondes.</strong>
      ) : (
        <>
          <strong>ComfyUI est incomplet.</strong>
          {missing_nodes.length > 0 && <div>Nœuds manquants : {missing_nodes.join(", ")}</div>}
          {missing_models.length > 0 && <div>Modèles manquants : {missing_models.join(", ")}</div>}
        </>
      )}
    </div>
  );
}
