import { useEffect, useState } from "react";
import { ConnectPanel } from "./components/ConnectPanel";
import { probeSession } from "./services/api";
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

/**
 * How this browser is signed in:
 * - `key`: an API key stored here (LAN use, or by choice),
 * - `sso`: no key, but the server accepts this browser's Cloudflare Access
 *   session (ebooks.culture.dev), so no key is needed,
 * - `checking`: asking the server whether an SSO session exists,
 * - `none`: neither; the connect panel asks for a key.
 * `expired` remembers that a stored key just stopped working.
 */
type Auth =
  | { kind: "checking"; expired: boolean }
  | { kind: "key" }
  | { kind: "sso"; identity: string }
  | { kind: "none"; expired: boolean };

function initialAuth(): Auth {
  return getStoredKey() !== null ? { kind: "key" } : { kind: "checking", expired: false };
}

export function App() {
  const [auth, setAuth] = useState<Auth>(initialAuth);
  const connected = auth.kind === "key" || auth.kind === "sso";
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash));
  const [libraryVersion, setLibraryVersion] = useState(0);

  useEffect(() => {
    const onHash = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (auth.kind !== "checking") return;
    const expired = auth.expired;
    let live = true;
    probeSession()
      .then((who) => {
        if (!live) return;
        setAuth(who ? { kind: "sso", identity: who.identity } : { kind: "none", expired });
      })
      .catch(() => {
        if (live) setAuth({ kind: "none", expired });
      });
    return () => {
      live = false;
    };
  }, [auth]);

  useEffect(() => {
    document.title = connected
      ? `${ROUTES.find(([r]) => r === route)?.[1]}, xteink library`
      : "Connect, xteink library";
  }, [route, connected]);

  function go(next: Route) {
    window.location.hash = `#/${next}`;
    setRoute(next);
  }

  if (auth.kind === "checking") {
    return (
      <main id="main" className="checking">
        <p role="status" className="muted">
          Checking sign-in…
        </p>
      </main>
    );
  }

  if (auth.kind === "none") {
    return <ConnectPanel expired={auth.expired} onConnected={() => setAuth({ kind: "key" })} />;
  }

  return (
    <SessionProvider
      onAuthLost={() => {
        // A rejected key is dropped; then ask once whether an SSO session covers us.
        clearStoredKey();
        setAuth({ kind: "checking", expired: auth.kind === "key" });
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
            access={auth.kind === "sso" ? { identity: auth.identity } : null}
            onForget={() => {
              clearStoredKey();
              setAuth({ kind: "checking", expired: false });
            }}
          />
        )}
      </main>
    </SessionProvider>
  );
}
