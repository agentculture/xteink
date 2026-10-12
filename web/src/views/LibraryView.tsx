import { useEffect, useId, useState } from "react";
import {
  deleteItem,
  downloadItem,
  listDevices,
  listItems,
  queueItem,
  type Device,
  type Item,
  type Kind,
  type QueueEntry,
} from "../services/api";
import { formatBytes, formatWhen } from "../services/format";
import { useSession } from "../services/session";
import { Confirm } from "../components/Confirm";

const PAGE = 50;

type Props = { refreshToken?: number; onAddClick: () => void };

export function LibraryView({ refreshToken = 0, onAddClick }: Props) {
  const { explain } = useSession();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [kind, setKind] = useState<Kind | "">("");
  const [items, setItems] = useState<Item[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const searchId = useId();

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 250);
    return () => window.clearTimeout(t);
  }, [query]);

  useEffect(() => {
    let live = true;
    listItems({ q: debounced, kind, limit: PAGE })
      .then((res) => {
        if (!live) return;
        setItems(res.items);
        setHasMore(!debounced.trim() && res.items.length === PAGE);
        setError(null);
      })
      .catch((err) => live && setError(explain(err)));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced, kind, refreshToken]);

  useEffect(() => {
    listDevices()
      .then((res) => setDevices(res.devices.filter((d) => d.revoked_at === null)))
      .catch(() => setDevices([]));
  }, [refreshToken]);

  async function more() {
    try {
      const res = await listItems({ kind, limit: PAGE, offset: items?.length ?? 0 });
      setItems((cur) => [...(cur ?? []), ...res.items]);
      setHasMore(res.items.length === PAGE);
    } catch (err) {
      setError(explain(err));
    }
  }

  const searching = debounced.trim() !== "";

  return (
    <section aria-labelledby="library-heading" className="view">
      <h1 id="library-heading" className="view-title">Library</h1>

      <div className="toolbar" role="search">
        <label htmlFor={searchId} className="visually-hidden">
          Search by title or author
        </label>
        <input
          id={searchId}
          type="search"
          className="search"
          placeholder="Search by title or author"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="segmented" role="radiogroup" aria-label="Show">
          {(
            [
              ["", "All"],
              ["book", "Books"],
              ["article", "Articles"],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className={kind === value ? "is-on" : undefined}>
              <input
                type="radio"
                name="kind"
                value={value}
                checked={kind === value}
                onChange={() => setKind(value)}
              />
              {label}
            </label>
          ))}
        </div>
      </div>

      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}
      {items === null && !error && <p className="muted">Opening the library…</p>}
      {items && items.length === 0 && !searching && !kind && (
        <div className="empty">
          <p>Your library is empty. Add an EPUB, a text file or an article to start.</p>
          <button type="button" className="btn btn-primary" onClick={onAddClick}>
            Add books
          </button>
        </div>
      )}
      {items && items.length === 0 && (searching || kind) && (
        <p className="empty">Nothing matches. Try part of the title or the author's surname.</p>
      )}
      {items && items.length > 0 && (
        <ol className="shelf" aria-label="Books and articles">
          {items.map((item) => (
            <li key={item.id}>
              <LibraryItem
                item={item}
                devices={devices}
                onDeleted={() => setItems((cur) => (cur ?? []).filter((i) => i.id !== item.id))}
              />
            </li>
          ))}
        </ol>
      )}
      {hasMore && (
        <button type="button" className="btn btn-quiet more" onClick={() => void more()}>
          Show more
        </button>
      )}
    </section>
  );
}

function LibraryItem({
  item,
  devices,
  onDeleted,
}: {
  item: Item;
  devices: Device[];
  onDeleted: () => void;
}) {
  const { explain } = useSession();
  const [sending, setSending] = useState(false);
  const [target, setTarget] = useState<number | "">("");
  const [sent, setSent] = useState<{ device: string; entry: QueueEntry }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const selectId = useId();

  async function send() {
    const device = devices.find((d) => d.id === target);
    if (!device) return;
    setError(null);
    try {
      const entry = await queueItem(device.id, item.id);
      setSent((cur) => [...cur.filter((s) => s.device !== device.name), { device: device.name, entry }]);
      setSending(false);
    } catch (err) {
      setError(explain(err));
    }
  }

  async function download() {
    setError(null);
    try {
      const blob = await downloadItem(item.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${item.title}.${item.format}`;
      a.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setError(explain(err));
    }
  }

  return (
    <article className="book" aria-labelledby={`item-${item.id}`}>
      <div className="book-text">
        <h2 id={`item-${item.id}`} className="book-title">
          {item.title}
        </h2>
        {item.author && <p className="book-author">{item.author}</p>}
        <p className="book-meta">
          {item.kind === "article" ? "Article" : "Book"}, {item.format.toUpperCase()},{" "}
          {formatBytes(item.size)}, added {formatWhen(item.created_at)}
        </p>
        {sent.map(({ device, entry }) => (
          <p key={device} className="sent" role="status">
            {entry.state === "delivered"
              ? `Already on ${device}.`
              : `Sent to ${device}. It arrives on the reader's next sync.`}
          </p>
        ))}
      </div>

      <div className="book-actions">
        {!sending && (
          <button
            type="button"
            className="btn"
            onClick={() => {
              setSending(true);
              if (devices.length === 1) setTarget(devices[0].id);
            }}
          >
            Send to reader
          </button>
        )}
        {sending && devices.length === 0 && (
          <p className="hint">
            No paired readers yet. Pair one under Readers first.{" "}
            <button type="button" className="link" onClick={() => setSending(false)}>
              Close
            </button>
          </p>
        )}
        {sending && devices.length > 0 && (
          <span className="send">
            <label htmlFor={selectId} className="visually-hidden">
              Reader
            </label>
            <select
              id={selectId}
              className="send-select"
              value={target}
              onChange={(e) => setTarget(e.target.value ? Number(e.target.value) : "")}
            >
              <option value="">Choose a reader</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-primary" disabled={target === ""} onClick={() => void send()}>
              Send
            </button>
            <button type="button" className="btn btn-quiet" onClick={() => setSending(false)}>
              Cancel
            </button>
          </span>
        )}
        <button type="button" className="btn btn-quiet" onClick={() => void download()}>
          Download
        </button>
        <Confirm
          label="Delete"
          confirmLabel={`Delete “${item.title}”`}
          question="Readers that mirror the library remove it too."
          onConfirm={async () => {
            try {
              await deleteItem(item.id);
              onDeleted();
            } catch (err) {
              setError(explain(err));
            }
          }}
        />
      </div>
      {error && (
        <p role="alert" className="callout callout-error">
          {error}
        </p>
      )}
    </article>
  );
}
