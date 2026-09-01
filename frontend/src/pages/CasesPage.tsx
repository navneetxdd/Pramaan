import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { api, type CaseRecord } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export function CasesPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [examiner, setExaminer] = useState("");
  const [reference, setReference] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCases();
      setCases(data.cases);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cases");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim() || !examiner.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await api.createCase({
        title: title.trim(),
        examiner: examiner.trim(),
        reference: reference.trim() || undefined,
      });
      setTitle("");
      setReference("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create case");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-8">
      <section className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="label">Case registry</p>
          <h1 className="font-serif text-3xl text-ink">Investigations</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-muted">
            Each case binds acquisition hashes, recovery jobs, and custody events into one auditable record.
          </p>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <section className="panel overflow-hidden">
          <div className="border-b border-hairline px-5 py-4">
            <h2 className="text-sm font-medium text-ink">Active cases</h2>
          </div>
          {loading ? (
            <p className="px-5 py-8 text-sm text-ink-faint">Loading…</p>
          ) : cases.length === 0 ? (
            <p className="px-5 py-8 text-sm text-ink-faint">No cases opened yet.</p>
          ) : (
            <ul className="divide-y divide-hairline">
              {cases.map((item) => (
                <li key={item.id}>
                  <Link
                    to={`/cases/${item.id}`}
                    className="flex items-center justify-between gap-4 px-5 py-4 transition hover:bg-raised"
                  >
                    <div>
                      <p className="font-medium text-ink">{item.title}</p>
                      <p className="mono mt-1">{item.examiner} · {new Date(item.created_at).toLocaleString()}</p>
                    </div>
                    <StatusBadge status={item.status} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <form onSubmit={handleCreate} className="panel space-y-4 p-5">
          <div className="flex items-center gap-2">
            <Plus className="h-4 w-4 text-accent" />
            <h2 className="text-sm font-medium text-ink">Open case</h2>
          </div>
          <div className="space-y-2">
            <label className="label" htmlFor="title">Title</label>
            <input id="title" className="field" value={title} onChange={(e) => setTitle(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <label className="label" htmlFor="examiner">Examiner</label>
            <input id="examiner" className="field" value={examiner} onChange={(e) => setExaminer(e.target.value)} required />
          </div>
          <div className="space-y-2">
            <label className="label" htmlFor="reference">Reference</label>
            <input id="reference" className="field" value={reference} onChange={(e) => setReference(e.target.value)} />
          </div>
          {error ? <p className="text-sm text-danger">{error}</p> : null}
          <button type="submit" className="btn-primary w-full" disabled={creating}>
            {creating ? "Creating…" : "Create case"}
          </button>
        </form>
      </div>
    </div>
  );
}
