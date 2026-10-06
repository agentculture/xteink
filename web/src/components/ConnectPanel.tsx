import { useId, useState, type FormEvent } from "react";
import { verifyKey } from "../services/api";
import { errorMessage } from "../services/messages";
import { storeKey } from "../services/storage";

type Props = {
  onConnected: () => void;
  /** Set when a previously stored key stopped working. */
  expired?: boolean;
};

/**
 * First-run panel: this browser needs an API key to use the library.
 * Not a login: there is no account, just a key minted on the server.
 */
export function ConnectPanel({ onConnected, expired = false }: Props) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputId = useId();
  const hintId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    const key = value.trim();
    if (!key) {
      setError("Paste an API key first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (await verifyKey(key)) {
        storeKey(key);
        setValue("");
        onConnected();
      } else {
        setError(
          "The server didn't accept that key. Check it was copied whole and hasn't been revoked.",
        );
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="connect">
      <div className="connect-page">
        <h1 className="connect-title">Connect this browser to your library</h1>
        {expired ? (
          <p className="lede">
            The key this browser had stopped working. It may have been revoked. Paste a current one.
          </p>
        ) : (
          <p className="lede">
            Your books stay on the xteink server on your own network. This browser needs an API key
            to read and change the library.
          </p>
        )}
        <form onSubmit={submit} noValidate>
          <label htmlFor={inputId}>API key</label>
          <input
            id={inputId}
            type="password"
            autoComplete="off"
            spellCheck={false}
            placeholder="xtk_…"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-describedby={hintId}
            aria-invalid={error ? true : undefined}
          />
          <p id={hintId} className="hint">
            Make one on the server with <code>python -m xteink.server create-key "this laptop"</code>.
            The key is kept in this browser only.
          </p>
          {error && (
            <p role="alert" className="callout callout-error">
              {error}
            </p>
          )}
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {busy ? "Checking…" : "Connect this browser"}
          </button>
        </form>
      </div>
    </main>
  );
}
