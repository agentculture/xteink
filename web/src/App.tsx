import { useEffect, useState } from "react";
import { ConnectPanel } from "./components/ConnectPanel";
import { SessionProvider } from "./services/session";
import { clearStoredKey, getStoredKey } from "./services/storage";
import { AddView } from "./views/AddView";
import { DevicesView } from "./views/DevicesView";
import { LibraryView } from "./views/LibraryView";
import { SettingsView } from "./views/SettingsView";

const ROUTES = [
  ["library", "Library"],
  ["add", "Add books"],
  ["readers", "Readers"],
  ["settings", "Settings"],
] as const;

type Route = (typeof ROUTES)[number][0];

function routeFromHash(hash: string): Route {
  const name = hash.replace(/^#\/?/, "");
  return (ROUTES.find(([r]) => r === name)?.[0] ?? "library") as Route;
}

export function App() {
  const [connected, setConnected] = useState(() => getStoredKey() !== null);
  const [expired, setExpired] = useState(false);
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash));
  const [libraryVersion, setLibraryVersion] = useState(0);

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    document.title = connected
      ? `${ROUTES.find(([r]) => r === route)?.[1]}, xteink library`
      : "Connect, xteink library";
  }, [route, connected]);

  function go(next: Route) {
    window.location.hash = `#/${next}`;
    setRoute(next);
  }

  if (!connected) {
    return (
      <ConnectPanel
        expired={expired}
        onConnected={() => {
          setExpired(false);
          setConnected(true);
        }}
      />
    );
  }

  return (
    <SessionProvider
      onAuthLost={() => {
        clearStoredKey();
        setExpired(true);
        setConnected(false);
      }}
    >
      <a className="skip" href="#main">
        Skip to content
      </a>
      <header className="masthead">
        <a className="wordmark" href="#/library" aria-label="xteink library home">
          xteink
        </a>
        <nav aria-label="Sections">
          <ul>
            {ROUTES.map(([r, label]) => (
              <li key={r}>
                <a href={`#/${r}`} aria-current={route === r ? "page" : undefined}>
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" tabIndex={-1}>
        {route === "library" && (
          <LibraryView refreshToken={libraryVersion} onAddClick={() => go("add")} />
        )}
        {route === "add" && <AddView onAdded={() => setLibraryVersion((v) => v + 1)} />}
        {route === "readers" && <DevicesView />}
        {route === "settings" && (
          <SettingsView
            onForget={() => {
              clearStoredKey();
              setExpired(false);
              setConnected(false);
            }}
          />
        )}
      </main>
    </SessionProvider>
  );
}
