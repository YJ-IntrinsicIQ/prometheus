import fs from "node:fs";
import { Readable } from "node:stream";
import { annualReportPath } from "@/src/lib/evidence/documents";
import { COMPANIES } from "@/src/lib/story/companies";

// Serves an existing annual-report PDF inline (with Range support, so the browser can jump to #page=N without
// downloading the whole file). Slug and year are validated against fixed patterns; nothing user-supplied becomes a path.
export const dynamic = "force-dynamic";

export async function GET(request: Request, { params }: { params: Promise<{ companySlug: string; fiscalYear: string }> }) {
  const { companySlug, fiscalYear } = await params;
  const file = annualReportPath(companySlug, fiscalYear);
  if (!file) return new Response("Document not available", { status: 404 });
  const size = fs.statSync(file).size;
  const name = `${COMPANIES[companySlug].name} — Annual report ${fiscalYear.toUpperCase()}.pdf`;
  const base = {
    "Content-Type": "application/pdf",
    "Accept-Ranges": "bytes",
    "Content-Disposition": `inline; filename*=UTF-8''${encodeURIComponent(name)}`,
    "Cache-Control": "private, max-age=3600",
  };
  const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("range") ?? "");
  if (range && (range[1] || range[2])) {
    const start = range[1] ? Number(range[1]) : Math.max(0, size - Number(range[2]));
    const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
    if (start > end || start >= size) return new Response(null, { status: 416, headers: { ...base, "Content-Range": `bytes */${size}` } });
    return new Response(Readable.toWeb(fs.createReadStream(file, { start, end })) as ReadableStream, {
      status: 206,
      headers: { ...base, "Content-Range": `bytes ${start}-${end}/${size}`, "Content-Length": String(end - start + 1) },
    });
  }
  return new Response(Readable.toWeb(fs.createReadStream(file)) as ReadableStream, { headers: { ...base, "Content-Length": String(size) } });
}
