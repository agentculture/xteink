import { useState } from "react";

type Props = {
  label: string;
  confirmLabel: string;
  question: string;
  onConfirm: () => void | Promise<void>;
  disabled?: boolean;
};

/** A destructive action that asks inline before it acts. */
export function Confirm({ label, confirmLabel, question, onConfirm, disabled }: Props) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!asking) {
    return (
      <button type="button" className="btn btn-quiet" disabled={disabled} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <span className="confirm" role="group" aria-label={question}>
      <span className="confirm-q">{question}</span>
      <button
        type="button"
        className="btn btn-danger"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setAsking(false);
          }
        }}
      >
        {confirmLabel}
      </button>
      <button type="button" className="btn btn-quiet" onClick={() => setAsking(false)}>
        Keep
      </button>
    </span>
  );
}
