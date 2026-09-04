/**
 * Live engine log for a recovery run.
 *
 * Previously exported from ConfidenceDonut.tsx; that file existed only to draw a
 * chart of fabricated confidence values and was deleted when the Recovery page
 * moved to a real checks-passed breakdown.
 */

function logTone(line: string): string {
  // Structure actually parsed from the index.
  if (
    /dual_signature|hikbtree_indexed|honeywell_index_4|honeywell_format_carve_4/.test(
      line,
    )
  ) {
    return "text-[var(--status-success)]";
  }
  // Recovered from a cleared or expired index entry — the forensically
  // interesting lines, and the ones an examiner should not scroll past.
  if (/deleted_entry|expired|header_footer|header-only/.test(line)) {
    return "text-[var(--status-warning)]";
  }
  if (/hikbtree_recording/.test(line)) {
    return "text-[var(--status-info)]";
  }
  if (/carve|unreferenced|h264_nal/.test(line)) {
    return "text-[var(--text-tertiary)]";
  }
  return "text-[var(--text-secondary)]";
}

export function RecoveryLogPanel({ lines }: { lines: string[] }) {
  return (
    <pre className="flex-1 overflow-y-auto p-3 font-mono text-[11px] leading-relaxed">
      {lines.length === 0 ? (
        <span className="text-[var(--text-tertiary)]">
          Log output appears when a recovery job runs.
        </span>
      ) : (
        lines.map((line, index) => (
          <div key={`${index}-${line.slice(0, 24)}`} className={logTone(line)}>
            {line}
          </div>
        ))
      )}
    </pre>
  );
}
