import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../api/auth";
import { useAuth } from "../auth/useAuth";
import { ErrorBanner } from "../components/ErrorBanner";

export function Login() {
  const navigate = useNavigate();
  const auth = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await login(username, password);
      auth.login(res.token, res.user);
      navigate("/products", { replace: true });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base-200 p-4">
      <div className="card bg-base-100 shadow w-full max-w-sm">
        <form className="card-body gap-2" onSubmit={onSubmit}>
          <h1 className="card-title">Log in</h1>
          <ErrorBanner error={error} />
          <label className="form-control">
            <span className="label-text mb-1">Username</span>
            <input
              type="text"
              autoComplete="username"
              className="input input-bordered"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label className="form-control">
            <span className="label-text mb-1">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              className="input input-bordered"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <button
            type="submit"
            className="btn btn-primary mt-2"
            disabled={busy}
          >
            Log in
          </button>
          <div className="text-sm text-center mt-2">
            No account?{" "}
            <a href="/register" className="link">
              Register
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}
