import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { register } from "../api/auth";
import { ErrorBanner } from "../components/ErrorBanner";

export function Register() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register({
        username,
        password,
        full_name: fullName.trim() === "" ? null : fullName,
      });
      navigate("/login", { replace: true });
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
          <h1 className="card-title">Register</h1>
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
              autoComplete="new-password"
              className="input input-bordered"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          <label className="form-control">
            <span className="label-text mb-1">Full name</span>
            <input
              type="text"
              autoComplete="name"
              className="input input-bordered"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="btn btn-primary mt-2"
            disabled={busy}
          >
            Register
          </button>
          <div className="text-sm text-center mt-2">
            Already have an account?{" "}
            <a href="/login" className="link">
              Log in
            </a>
          </div>
        </form>
      </div>
    </div>
  );
}
