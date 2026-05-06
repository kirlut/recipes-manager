import { ApiError } from "../api/client";

export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null;
  let title = "Error";
  let detail: string | undefined;
  let violations: { field: string; message: string }[] | undefined;

  if (error instanceof ApiError) {
    title = error.problem.title || title;
    detail = error.problem.detail;
    violations = error.problem.extensions?.violations;
  } else if (error instanceof Error) {
    detail = error.message;
  } else {
    detail = String(error);
  }

  return (
    <div role="alert" className="alert alert-error mb-4">
      <div className="flex flex-col items-start gap-1">
        <strong>{title}</strong>
        {detail && <span className="text-sm">{detail}</span>}
        {violations && violations.length > 0 && (
          <ul className="list-disc pl-5 text-sm">
            {violations.map((v, i) => (
              <li key={i}>
                <code>{v.field}</code>: {v.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
