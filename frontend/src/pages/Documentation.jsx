import { useEffect, useState } from "react";
import { BookOpen, Printer } from "lucide-react";
import { useFetch } from "../hooks";
import { Badge, Button, ErrorNotice, LoadingBlock, Panel, ScopeNote } from "../components/ui";

export default function Documentation() {
  const { data, error, loading, refresh } = useFetch("/api/documentation");
  const [active, setActive] = useState("abstract");

  useEffect(() => {
    if (!data?.sections?.length) return undefined;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-120px 0px -60% 0px", threshold: [0.1, 0.4] },
    );
    data.sections.forEach((section) => {
      const element = document.getElementById(section.id);
      if (element) observer.observe(element);
    });
    return () => observer.disconnect();
  }, [data]);

  if (loading && !data) return <LoadingBlock rows={8} />;
  if (error && !data) return <Panel><ErrorNotice error={error} onRetry={refresh} /></Panel>;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Panel
        title="Research documentation"
        subtitle={data.research_title}
        action={<Button variant="ghost" onClick={() => window.print()} className="no-print"><Printer size={12} /> Print</Button>}
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="cyan">REUG research prototype</Badge>
          <Badge tone="neutral">Methodology matches the implemented pipeline</Badge>
          <Badge tone="amber">No embedded results</Badge>
        </div>
        <ScopeNote>{data.scope_note}</ScopeNote>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="no-print hidden xl:block">
          <div className="sticky top-30 space-y-0.5 rounded-xl border border-line/60 bg-ink-900/50 p-2.5">
            <div className="mb-2 px-2 text-[9px] font-semibold uppercase tracking-[0.16em] text-slate-600">Contents</div>
            {data.sections.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                onClick={() => setActive(section.id)}
                className={`block rounded-md px-2 py-1.5 text-[10.5px] leading-snug transition ${active === section.id ? "bg-cyan/[0.08] text-cyan" : "text-slate-500 hover:bg-ink-800/60 hover:text-slate-300"}`}
              >
                {section.title}
              </a>
            ))}
            <a href="#references" className="block rounded-md px-2 py-1.5 text-[10.5px] text-slate-500 hover:text-slate-300">References</a>
          </div>
        </aside>

        <div className="space-y-4">
          {data.sections.map((section, index) => (
            <section key={section.id} id={section.id} className="panel scroll-mt-28">
              <div className="panel-head">
                <div className="flex items-baseline gap-2.5">
                  <span className="font-mono text-[10px] text-cyan/60">{String(index + 1).padStart(2, "0")}</span>
                  <h2 className="text-[15px] font-semibold tracking-tight text-slate-100">{section.title}</h2>
                </div>
              </div>
              <div className="panel-body space-y-3">
                {(section.paragraphs || []).map((paragraph, paragraphIndex) => (
                  <p key={paragraphIndex} className="text-[11.8px] leading-6 text-slate-400">{paragraph}</p>
                ))}
                {(section.bullets || []).length > 0 && (
                  <ul className="space-y-1.5">
                    {section.bullets.map((bullet, bulletIndex) => (
                      <li key={bulletIndex} className="flex gap-2 text-[11.5px] leading-relaxed text-slate-400">
                        <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-cyan/60" />
                        <span>{bullet}</span>
                      </li>
                    ))}
                  </ul>
                )}
                {section.diagram && (
                  <div className="rounded-lg border border-line/60 bg-ink-950/50 p-3 font-mono text-[10px] leading-6 text-slate-400">
                    {section.diagram.map((line) => <div key={line}>{line}</div>)}
                  </div>
                )}
              </div>
            </section>
          ))}

          <section id="references" className="panel scroll-mt-28">
            <div className="panel-head"><h2 className="text-[15px] font-semibold text-slate-100">References</h2></div>
            <div className="panel-body">
              <ol className="space-y-2">
                {data.references.map((reference, index) => (
                  <li key={reference} className="flex gap-2.5 text-[11px] leading-relaxed text-slate-500">
                    <span className="font-mono text-cyan/50">[{index + 1}]</span>
                    <span>{reference}</span>
                  </li>
                ))}
              </ol>
            </div>
          </section>
        </div>
      </div>

      <ScopeNote>
        This documentation is served by the backend and documents the implemented methodology. Actual quantitative results are produced only by experiments run in this installation.
      </ScopeNote>
    </div>
  );
}
