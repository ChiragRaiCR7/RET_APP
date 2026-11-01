import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: false });

/**
 * Render assistant Markdown safely. Model output is untrusted (it can echo uploaded data), so
 * the HTML is sanitised; citation markers like [3] become buttons the chat view wires up.
 */
export function renderAnswer(md: string, citationCount: number): string {
  const html = marked.parse(md, { async: false });
  const withCites = html.replace(/\[(\d{1,3})\]/g, (whole, n: string) => {
    const i = Number(n);
    return i >= 1 && i <= citationCount
      ? `<button type="button" class="cite" data-cite="${i}" aria-label="Source ${i}">${i}</button>`
      : whole;
  });
  return DOMPurify.sanitize(withCites, {
    ALLOWED_TAGS: ["p", "strong", "em", "code", "pre", "ul", "ol", "li", "table", "thead", "tbody",
      "tr", "th", "td", "br", "h3", "h4", "blockquote", "button", "del"],
    ALLOWED_ATTR: ["type", "class", "data-cite", "aria-label"],
  });
}
