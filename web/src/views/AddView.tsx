import { useId, useRef, useState, type DragEvent } from "react";
import { uploadItem, type Item, type Kind } from "../services/api";
import { formatBytes } from "../services/format";
import { useSession } from "../services/session";

type Upload = {
  key: number;
  name: string;
  size: number;
  state: "waiting" | "uploading" | "added" | "duplicate" | "failed";
  title?: string;
  message?: string;
};

type Props = { onAdded: (item: Item) => void };

const ACCEPT = ".epub,.txt,.md,.markdown,.html,.htm,.bmp";
let nextKey = 1;

export function AddView({ onAdded }: Props) {
  const { explain } = useSession();
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [dragging, setDragging] = useState(false);
  const [kind, setKind] = useState<Kind | "">("");
  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("");
  const depth = useRef(0);
  const pickerId = useId();

  const patch = (key: number, change: Partial<Upload>) =>
    setUploads((list) => list.map((u) => (u.key === key ? { ...u, ...change } : u)));

  async function addFiles(files: File[]) {
    if (files.length === 0) return;
    const batch = files.map((f) => ({
      file: f,
      entry: { key: nextKey++, name: f.name, size: f.size, state: "waiting" as const },
    }));
    setUploads((list) => [...batch.map((b) => b.entry), ...list]);
    const single = files.length === 1;
    // One at a time: the server converts some formats, and order should be predictable.
    for (const { file, entry } of batch) {
      patch(entry.key, { state: "uploading" });
      try {
        const res = await uploadItem(file, { kind, author, title: single ? title : "" });
        patch(entry.key, { state: res.created ? "added" : "duplicate", title: res.item.title });
        if (res.created) onAdded(res.item);
      } catch (err) {
        patch(entry.key, { state: "failed", message: explain(err) });
      }
    }
    if (single) setTitle("");
  }

  function onDragEnter(e: DragEvent) {
    e.preventDefault();
    depth.current += 1;
    setDragging(true);
  }
  function onDragLeave(e: DragEvent) {
    e.preventDefault();
    depth.current = Math.max(0, depth.current - 1);
    if (depth.current === 0) setDragging(false);
  }
  function onDrop(e: DragEvent) {
    e.preventDefault();
    depth.current = 0;
    setDragging(false);
    void addFiles(Array.from(e.dataTransfer?.files ?? []));
  }

  return (
    <section aria-labelledby="add-heading" className="view">
      <h1 id="add-heading" className="view-title">Add to your library</h1>
      <div
        data-testid="drop-page"
        className={`drop-page${dragging ? " is-dragging" : ""}`}
        onDragEnter={onDragEnter}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        <div className="drop-inner">
          <p className="drop-lead">{dragging ? "Let go to add" : "Drop books and articles here"}</p>
          <p className="drop-formats">EPUB, plain text, BMP, or Markdown and HTML (converted to EPUB)</p>
          <label htmlFor={pickerId} className="btn btn-primary drop-pick">
            Choose files
          </label>
          <input
            id={pickerId}
            className="visually-hidden-input"
            type="file"
            multiple
            accept={ACCEPT}
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              e.target.value = "";
              void addFiles(files);
            }}
          />
        </div>
      </div>

      <details className="details">
        <summary>Title, author and kind</summary>
        <div className="fields">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} />
            <span className="hint">Blank uses the file's own title. Ignored when adding several files.</span>
          </label>
          <label>
            Author
            <input value={author} onChange={(e) => setAuthor(e.target.value)} />
          </label>
          <label>
            Kind
            <select value={kind} onChange={(e) => setKind(e.target.value as Kind | "")}>
              <option value="">Decide from the file</option>
              <option value="book">Book</option>
              <option value="article">Article</option>
            </select>
          </label>
        </div>
      </details>

      {uploads.length > 0 && (
        <ul className="uploads" aria-label="Files added in this visit" aria-live="polite">
          {uploads.map((u) => (
            <li key={u.key} className={`upload upload-${u.state}`}>
              <span className="upload-name">{u.name}</span>
              <span className="upload-size">{formatBytes(u.size)}</span>
              <span className="upload-status">
                {u.state === "waiting" && "Waiting"}
                {u.state === "uploading" && "Adding…"}
                {u.state === "added" && `Added as “${u.title}”`}
                {u.state === "duplicate" && `Already in your library as “${u.title}”`}
                {u.state === "failed" && u.message}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
