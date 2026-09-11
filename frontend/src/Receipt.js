import { useState } from "react";
import { Printer, Share2, X, Check, RotateCcw } from "lucide-react";

const money = n => `₹${Number(n || 0).toLocaleString("en-IN")}`;
const when = iso => iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";

const receiptText = o => [
  `Navyug Catering & Tiffin — Receipt`,
  `Order ${o.order_id} · ${when(o.created_at)}`,
  ``,
  ...o.items.map(i => `${i.quantity} × ${i.name}  ${money(i.price * i.quantity)}`),
  ``,
  `Subtotal ${money(o.subtotal)}`,
  `Delivery ${o.delivery_fee ? money(o.delivery_fee) : "Free"}`,
  `Total ${money(o.total)} (${o.payment_status === "Paid" ? "Paid online" : "Cash on delivery"})`,
  ``,
  `Deliver to: ${o.customer_name}, ${o.address}`,
  `The taste of love……`,
].join("\n");

export function Receipt({ order, onClose, onReorder }) {
  const [copied, setCopied] = useState(false);
  const share = async () => {
    const text = receiptText(order);
    if (navigator.share) { try { await navigator.share({ title: `Navyug order ${order.order_id}`, text }); return; } catch { /* dismissed */ } }
    await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="receipt-backdrop" data-testid="receipt-modal" onClick={onClose}>
      <div className="receipt-sheet" onClick={e => e.stopPropagation()}>
        <div className="receipt-actions no-print">
          <button className="button primary" data-testid="receipt-print-button" onClick={() => window.print()}><Printer size={15}/> Print / Save PDF</button>
          <button className="button ghost" data-testid="receipt-share-button" onClick={share}>{copied ? <><Check size={15}/> Copied</> : <><Share2 size={15}/> Share</>}</button>
          {onReorder && <button className="button ghost" data-testid="receipt-reorder-button" onClick={onReorder}><RotateCcw size={15}/> Order again</button>}
          <button className="icon-button" data-testid="receipt-close-button" onClick={onClose} aria-label="Close"><X size={20}/></button>
        </div>
        <header className="receipt-head">
          <div className="logo"><span className="logo-mark">N</span><span><b>Navyug</b><small>The taste of love……</small></span></div>
          <div className="receipt-meta"><span>ORDER</span><strong data-testid="receipt-order-id">{order.order_id}</strong><small>{when(order.created_at)}</small></div>
        </header>
        <div className="receipt-parties">
          <div><span>DELIVER TO</span><b>{order.customer_name}</b><p>{order.address}</p><p>{order.phone}</p></div>
          <div><span>STATUS</span><b data-testid="receipt-status">{order.status}</b><p>{order.payment_status === "Paid" ? "Paid online" : "Cash on delivery"}</p></div>
        </div>
        <table className="receipt-table">
          <thead><tr><th>Dish</th><th>Qty</th><th>Price</th><th>Amount</th></tr></thead>
          <tbody>{order.items.map((i, k) => <tr key={k}><td>{i.name}</td><td>{i.quantity}</td><td>{money(i.price)}</td><td>{money(i.price * i.quantity)}</td></tr>)}</tbody>
          <tfoot>
            <tr><td colSpan="3">Subtotal</td><td>{money(order.subtotal)}</td></tr>
            <tr><td colSpan="3">Delivery</td><td>{order.delivery_fee ? money(order.delivery_fee) : "Free"}</td></tr>
            <tr className="receipt-total"><td colSpan="3">Total</td><td data-testid="receipt-total">{money(order.total)}</td></tr>
          </tfoot>
        </table>
        {order.special_instructions && <p className="receipt-note"><span>NOTE</span> {order.special_instructions}</p>}
        <footer className="receipt-foot">Ghar jaisa khana, ab aapke ghar tak. Thank you for choosing Navyug.<br/>+91 99999 99999 · @navyugcatering</footer>
      </div>
    </div>
  );
}
