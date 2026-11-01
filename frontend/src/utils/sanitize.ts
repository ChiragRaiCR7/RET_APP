/**
 * The one place untrusted HTML is cleaned before it reaches v-html.
 *
 * Chat answers quote uploaded XML/CSV and model output, so they are untrusted. DOMPurify
 * parses in an inert document (no scripts, no image loads, no event handlers fire) and
 * keeps only safe tags, attributes and URL schemes. Its defaults keep the structural
 * markup the renderers emit: div/span/sup/pre, class, id, title and data-* attributes.
 */
import DOMPurify, { type Config } from 'dompurify'

export function sanitizeHtml(html: string, config: Config = {}): string {
  return DOMPurify.sanitize(html, { ...config, RETURN_TRUSTED_TYPE: false }) as string
}
