import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { createKey, listKeys, revokeKey, type ApiKey } from "../services/api";
import { formatAgo, formatWhen } from "../services/format";
import { useSession } from "../services/session";
import { getStoredKey, keyIdOf, keyPrefix } from "../services/storage";
import { Confirm } from "../components/Confirm";
import { KeyReveal } from "../components/KeyReveal";

/**
 * Public hostnames the Cloudflare Tunnel is configured with. This is
 * configuration, not a live health check: the UI makes no Cloudflare calls.
 */
export const TUNNEL_HOSTS = {
  library: "ebooks.culture.dev",
  devices: "xteink.culture.dev",
} as const;

type Props = { onForget: () => void; hostname?: string };

export function SettingsView({ onForget, hostname = window.location.hostname }: Props) {
  const stored = getStoredKey();
  const viaTunnel = hostname === TUNNEL_HOSTS.library;

  return (
    <section aria-labelledby="settings-heading" className="view">
      <h1 id="settings-heading" className="view-title">Settings</h1>

      <section className="panel" aria-labelledby="conn-heading">
        <h2 id="conn-heading">This browser</h2>
        <p>
          This browser uses the key <code>{stored ? keyPrefix(stored) : "none"}</code>, stored here
          only. Its secret part is never shown.
        </p>
        <Confirm
          label="Forget this key"
          confirmLabel="Forget key"
          question="You'll need to paste a key again to use the library here."
          onConfirm={onForget}
        />
      </section>

      <section className="panel" aria-labelledby="tunnel-heading">
        <h2 id="tunnel-heading">Remote access</h2>
        <p className="muted">
          Configured hostnames for the Cloudflare Tunnel. This shows configuration, not whether the
          tunnel is up right now.
        </p>
        <dl className="facts">
          <div>
            <dt>Library (this page)</dt>
            <dd>
              <code>{TUNNEL_HOSTS.library}</code>, behind Cloudflare Access
            </dd>
          </div>
          <div>
            <dt>Readers sync from</dt>
            <dd>
              <code>{TUNNEL_HOSTS.devices}</code>, device keys only
            </dd>
          </div>
          <div>
            <dt>You're on</dt>
            <dd>
              {viaTunnel
                ? "the tunnel, through Cloudflare Access"
                : `your local network (${hostname || "this machine"})`}
            </dd>
          </div>
        </dl>
      </section>

      <ApiKeys />
    </section>
  );
}

function ApiKeys() {
  const { explain } = useSession();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [reveal, setReveal] = useState<{ label: string; key: string } | null>(null);
  const nameId = useId();
  const stored = getStoredKey();
  const mine = stored ? keyIdOf(stored) : null;

  const load = useCallback(async () => {
    try {
      setKeys((await listKeys()).keys);
      setError(null);
    } catch (err) {
      setError(explain(err));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Name the key after where it'll be used, like “phone” or “calibre script”.");
      return;
    }
    try {
      const res = await createKey(name.trim());
      setReveal({ label: res.api_key.name, key: res.key });
      setName("");
      await load();
    } catch (err) {
      setError(explain(err));
    }
  }

  return (
    <section className="panel" aria-labelledby="keys-heading">
      <h2 id="keys-heading">API keys</h2>
      <p className="muted">
        Keys let browsers, scripts and the MCP server use the library. Readers use their own device
        keys.
      </p>
      <form onSubmit={create} className="inline-form" noValidate>
        <label htmlFor={nameId}>New key name</label>
        <div className="row">
          <input id={nameId} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          <button type="submit" className="btn btn-primary">
            Create key
          </button>
        </div>
      </form>
      {reveal && <KeyReveal label={reveal.label} rawKey={reveal.key} onDone={() => setReveal(null)} />}
      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}
      {keys && (
        <ul className="keys">
          {keys.map((k) => (
            <li key={k.id} className={k.revoked_at ? "is-revoked" : undefined}>
              <div>
                <span className="key-name">{k.name}</span>
                {k.key_id === mine && <span className="tag">This browser</span>}
                {k.revoked_at && <span className="tag tag-inverse">Revoked</span>}
                <p className="key-meta">
                  <code>xtk_{k.key_id}…</code>, made {formatWhen(k.created_at)}, last used{" "}
                  {formatAgo(k.last_used)}
                </p>
              </div>
              {!k.revoked_at && (
                <Confirm
                  label="Revoke"
                  confirmLabel={`Revoke “${k.name}”`}
                  question={
                    k.key_id === mine
                      ? "This is the key this browser uses. It will be disconnected."
                      : "Anything using this key stops working."
                  }
                  onConfirm={async () => {
                    try {
                      await revokeKey(k.id);
                      await load();
                    } catch (err) {
                      setError(explain(err));
                    }
                  }}
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
