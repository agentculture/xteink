import { useId, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

type Props = {
  /** What the key is for, e.g. "Bedside" or "this laptop". */
  label: string;
  rawKey: string;
  /** Device keys get a QR code for setup on the reader; API keys don't need one. */
  qr?: boolean;
  onDone: () => void;
};

/**
 * Shows a freshly issued raw key exactly once. The parent drops `rawKey`
 * from state on `onDone`, so it is gone from the page afterwards.
 */
export function KeyReveal({ label, rawKey, qr = false, onDone }: Props) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const headingId = useId();

  async function copy() {
    try {
      await navigator.clipboard.writeText(rawKey);
      setCopied("copied");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <section className="reveal" role="region" aria-labelledby={headingId}>
      <h3 id={headingId}>Key for {label}</h3>
      <p className="reveal-note">
        Save this key now. It won't be shown again; if it's lost, rotate the key to get a new one.
      </p>
      <div className="reveal-body">
        {qr && (
          <div className="reveal-qr">
            <QRCodeSVG
              value={rawKey}
              size={176}
              marginSize={2}
              level="M"
              bgColor="#ffffff"
              fgColor="#000000"
              role="img"
              aria-label={`QR code of the key for ${label}`}
            />
          </div>
        )}
        <div className="reveal-key">
          <code className="key-text">{rawKey}</code>
          <div className="row">
            <button type="button" className="btn" onClick={copy}>
              {copied === "copied" ? "Copied" : "Copy key"}
            </button>
            <button type="button" className="btn btn-primary" onClick={onDone}>
              I've saved it
            </button>
          </div>
          {copied === "failed" && (
            <p className="hint" role="status">
              This browser blocked the clipboard. Select the key and copy it by hand.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
