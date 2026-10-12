import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import {
  deviceQueue,
  listDevices,
  registerDevice,
  revokeDevice,
  rotateDeviceKey,
  setMirror,
  type Device,
  type QueueEntry,
} from "../services/api";
import { formatAgo, formatBytes, formatWhen } from "../services/format";
import { useSession } from "../services/session";
import { Confirm } from "../components/Confirm";
import { KeyReveal } from "../components/KeyReveal";

type Reveal = { label: string; key: string };

export function DevicesView() {
  const { explain } = useSession();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reveal, setReveal] = useState<Reveal | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await listDevices();
      setDevices(res.devices);
      setError(null);
    } catch (err) {
      setError(explain(err));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section aria-labelledby="devices-heading" className="view">
      <h1 id="devices-heading" className="view-title">Readers</h1>

      <PairForm
        onPaired={(device, key) => {
          setReveal({ label: device.name, key });
          void load();
        }}
      />

      {reveal && (
        <KeyReveal label={reveal.label} rawKey={reveal.key} qr onDone={() => setReveal(null)} />
      )}

      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}
      {devices === null && !error && <p className="muted">Loading readers…</p>}
      {devices && devices.length === 0 && (
        <p className="empty">
          No readers yet. Pair one above, then enter its key on the reader to start syncing.
        </p>
      )}
      {devices && devices.length > 0 && (
        <ul className="devices">
          {devices.map((d) => (
            <li key={d.id}>
              <DeviceCard
                device={d}
                onChanged={load}
                onNewKey={(key) => setReveal({ label: d.name, key })}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function PairForm({ onPaired }: { onPaired: (device: Device, key: string) => void }) {
  const { explain } = useSession();
  const [name, setName] = useState("");
  const [mirror, setMirrorFlag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameId = useId();
  const mirrorId = useId();

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Give the reader a name you'll recognise, like “Bedside”.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await registerDevice(name.trim(), mirror);
      setName("");
      setMirrorFlag(false);
      onPaired(res.device, res.key);
    } catch (err) {
      setError(explain(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel pair" onSubmit={submit} noValidate aria-labelledby="pair-heading">
      <h2 id="pair-heading">Pair a reader</h2>
      <div className="pair-fields">
        <div className="field">
          <label htmlFor={nameId}>Device name</label>
          <input id={nameId} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
        </div>
        <div className="check">
          <input
            id={mirrorId}
            type="checkbox"
            checked={mirror}
            onChange={(e) => setMirrorFlag(e.target.checked)}
          />
          <label htmlFor={mirrorId}>
            Mirror the library
            <span className="hint">
              Books you delete here are removed from the reader too, unless you've annotated them.
            </span>
          </label>
        </div>
      </div>
      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {busy ? "Pairing…" : "Pair device"}
      </button>
    </form>
  );
}

function DeviceCard({
  device,
  onChanged,
  onNewKey,
}: {
  device: Device;
  onChanged: () => void;
  onNewKey: (key: string) => void;
}) {
  const { explain } = useSession();
  const [queue, setQueue] = useState<QueueEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revoked = device.revoked_at !== null;
  const mirrorId = useId();

  useEffect(() => {
    let live = true;
    deviceQueue(device.id, "all")
      .then((res) => live && setQueue(res.entries))
      .catch((err) => live && setError(explain(err)));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device.id, device.last_seen]);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(explain(err));
    }
  }

  return (
    <article className={`device${revoked ? " is-revoked" : ""}`} aria-labelledby={`dev-${device.id}`}>
      <header className="device-head">
        <h3 id={`dev-${device.id}`}>{device.name}</h3>
        {revoked && <span className="tag tag-inverse">Key revoked</span>}
      </header>

      <dl className="facts">
        <div>
          <dt>Last seen</dt>
          <dd>{device.last_seen ? formatAgo(device.last_seen) : "Not yet; enter the key on the reader"}</dd>
        </div>
        {device.last_sync_result && (
          <div>
            <dt>Last sync</dt>
            <dd>{device.last_sync_result}</dd>
          </div>
        )}
        {device.free_sd_bytes !== null && (
          <div>
            <dt>Free space</dt>
            <dd>{formatBytes(device.free_sd_bytes)}</dd>
          </div>
        )}
        {device.firmware_version && (
          <div>
            <dt>Firmware</dt>
            <dd>{device.firmware_version}</dd>
          </div>
        )}
        {device.last_error && (
          <div className="fact-error">
            <dt>Last error</dt>
            <dd>{device.last_error}</dd>
          </div>
        )}
      </dl>

      <div className="check">
        <input
          id={mirrorId}
          type="checkbox"
          checked={device.mirror}
          disabled={revoked}
          onChange={(e) => void act(() => setMirror(device.id, e.target.checked))}
        />
        <label htmlFor={mirrorId}>Mirror the library</label>
      </div>

      <h4 className="queue-title">Sent to this reader</h4>
      {queue === null && !error && <p className="muted">Loading…</p>}
      {queue && queue.length === 0 && (
        <p className="muted">Nothing sent yet. Use “Send to reader” in the library.</p>
      )}
      {queue && queue.length > 0 && <DeliveryList entries={queue} />}

      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}

      <div className="row actions">
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() =>
            void act(async () => {
              const res = await rotateDeviceKey(device.id);
              onNewKey(res.key);
            })
          }
        >
          {revoked ? "Issue a new key" : "Rotate key"}
        </button>
        {!revoked && (
          <Confirm
            label="Revoke key"
            confirmLabel={`Revoke ${device.name}'s key`}
            question="The reader stops syncing until it gets a new key."
            onConfirm={() => act(() => revokeDevice(device.id))}
          />
        )}
      </div>
    </article>
  );
}

export function DeliveryList({ entries }: { entries: QueueEntry[] }) {
  return (
    <ul className="deliveries">
      {entries.map((e) => (
        <li key={e.id} className={`delivery delivery-${e.state}`}>
          <span className="delivery-title">{e.title}</span>
          <span className="delivery-state">
            {e.state === "delivered"
              ? `On the device since ${formatWhen(e.delivered_at)}`
              : `Waiting for next sync, sent ${formatWhen(e.queued_at)}`}
          </span>
        </li>
      ))}
    </ul>
  );
}
