import { Link } from "react-router-dom";

function Mark() {
  return <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>;
}

/** AlgoProfitX wordmark. `plain` renders it without a link (e.g. footer). */
export function Brand({ to = "/", plain = false }: { to?: string; plain?: boolean }) {
  const word = <span className="brand-word">AlgoProfit<span>X</span></span>;
  if (plain) return <span className="brand"><Mark />{word}</span>;
  return (
    <Link className="brand" to={to} aria-label="AlgoProfitX home">
      <Mark />
      {word}
    </Link>
  );
}
