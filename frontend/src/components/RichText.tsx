import { Fragment, type ReactNode } from "react";

/* A small Markdown renderer for the agent's replies: headings, **bold**, *italic*, bullet and numbered lists,
   "> " notes and pipe tables. It builds React elements only (never raw HTML), so reply text cannot inject markup. */

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\[[^\]]+\]\([^)\s]+\)|\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g;
  let last = 0;
  let i = 0;
  for (const m of text.matchAll(re)) {
    const at = m.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const tok = m[0];
    const link = tok.startsWith("[") ? /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(tok) : null;
    if (link) {
      // Only same-site paths and http(s) URLs become links; anything else stays as plain text.
      if (/^(\/|https?:\/\/)/.test(link[2])) {
        out.push(
          <a key={`${keyBase}-${i++}`} href={link[2]} target="_blank" rel="noreferrer" className="font-medium text-[#ea580c] underline underline-offset-2">
            {link[1]}
          </a>,
        );
      } else {
        out.push(link[1]);
      }
      last = at + tok.length;
      continue;
    }
    out.push(
      tok.startsWith("**") ? (
        <strong key={`${keyBase}-${i++}`} className="font-semibold text-[#111111]">{tok.slice(2, -2)}</strong>
      ) : (
        <em key={`${keyBase}-${i++}`}>{tok.slice(1, -1)}</em>
      ),
    );
    last = at + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const isRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const isDivider = (l: string) => /^\s*\|[\s:|-]+\|\s*$/.test(l) && l.includes("-");
const cells = (l: string) => l.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());

function Table({ lines, k }: { lines: string[]; k: string }) {
  const hasHead = lines.length > 1 && isDivider(lines[1]);
  const head = hasHead ? cells(lines[0]) : [];
  const body = (hasHead ? lines.slice(2) : lines).map(cells);
  const headerBlank = head.every((h) => h === "");
  return (
    <div className="my-2 overflow-x-auto rounded-[10px] border border-[#ecebe8] bg-white">
      <table className="w-full border-collapse text-left text-[13px] leading-snug">
        {hasHead && !headerBlank && (
          <thead>
            <tr className="bg-[#f5f4f1] text-[12px] uppercase tracking-wide text-[#6b6b66]">
              {head.map((h, c) => (
                <th key={c} className="px-3 py-2 font-medium">{inline(h, `${k}-h${c}`)}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((row, r) => (
            <tr key={r} className="border-t border-[#f0efec] first:border-t-0">
              {row.map((cell, c) => (
                <td
                  key={c}
                  className={`px-3 py-2 align-top ${c === 0 && row.length === 2 && headerBlank ? "w-[38%] font-medium text-[#6b6b66]" : "text-[#111111]"}`}
                >
                  {inline(cell, `${k}-${r}-${c}`)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RichText({ text }: { text: string }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let n = 0;
  const key = () => `b${n++}`;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (isRow(line)) {
      const start = i;
      while (i < lines.length && isRow(lines[i])) i++;
      blocks.push(<Table key={key()} k={`t${start}`} lines={lines.slice(start, i)} />);
      continue;
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      blocks.push(
        <h3 key={key()} className="mb-1 mt-1 text-[15px] font-semibold text-[#111111]">{inline(h[2], `h${i}`)}</h3>,
      );
      i++;
      continue;
    }
    if (/^\s*>\s?/.test(line)) {
      const parts: string[] = [];
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) parts.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push(
        <p key={key()} className="my-2 border-l-2 border-[#ea580c]/40 pl-3 text-[12px] leading-relaxed text-[#6b6b66]">
          {inline(parts.join(" "), `q${i}`)}
        </p>,
      );
      continue;
    }
    if (/^\s*(?:[-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*(?:[-*•]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*(?:[-*•]|\d+[.)])\s+/, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={key()} className={`my-1.5 space-y-1 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-[#ea580c]`}>
          {items.map((it, idx) => (
            <li key={idx} className="pl-0.5">{inline(it, `l${i}-${idx}`)}</li>
          ))}
        </List>,
      );
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !isRow(lines[i]) &&
      !/^(#{1,4})\s+/.test(lines[i]) &&
      !/^\s*>\s?/.test(lines[i]) &&
      !/^\s*(?:[-*•]|\d+[.)])\s+/.test(lines[i])
    ) {
      para.push(lines[i++]);
    }
    blocks.push(
      <p key={key()} className="my-1.5">
        {para.map((p, idx) => (
          <Fragment key={idx}>
            {idx > 0 && <br />}
            {inline(p, `p${i}-${idx}`)}
          </Fragment>
        ))}
      </p>,
    );
  }

  return <div className="text-[15px] leading-relaxed [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">{blocks}</div>;
}
