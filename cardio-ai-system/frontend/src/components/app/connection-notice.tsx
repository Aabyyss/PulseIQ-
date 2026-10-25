import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { isOnline, subscribeToConnectivity } from "@/lib/connectivity";

/**
 * A quiet bar under the top of the document when the device is offline.
 *
 * The service worker keeps the shell available, so the failure mode this
 * prevents is the confusing one: pages open, the shell looks alive, and a save
 * quietly cannot reach the engine. It is rendered at the app root rather than
 * inside the workspace shell, because the sign-in page is exactly where an
 * offline launch lands and it should say the same thing.
 */
export function ConnectionNotice() {
  const [online, setOnline] = useState(isOnline);

  useEffect(() => subscribeToConnectivity(setOnline), []);

  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-2 bg-warn/15 px-4 py-1.5 text-center text-2xs font-medium text-warn-strong print:hidden"
    >
      <WifiOff className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
      <span>
        Offline — showing what this device already has. Saving a visit needs the
        engine.
      </span>
    </div>
  );
}
