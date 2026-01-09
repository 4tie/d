import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="max-w-3xl">
      <div className="text-lg font-semibold">Page not found</div>
      <div className="mt-2 text-sm text-fg-400">The requested route does not exist.</div>
      <div className="mt-4">
        <Link className="text-sm text-semantic-info hover:underline" to="/backtest">
          Go to Backtest
        </Link>
      </div>
    </div>
  );
}
