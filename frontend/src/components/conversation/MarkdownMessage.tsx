/**
 * Lightweight inline markdown renderer for assistant messages.
 * Handles the patterns GPT-family models commonly produce:
 *   ### / ## / # headers
 *   **bold**  *italic*  `inline code`
 *   - unordered lists
 *   1. ordered lists
 *   plain paragraphs
 *
 * No external dependencies. Raw text is HTML-escaped before any tags
 * are injected, so only the controlled tags (<strong><em><code>) can
 * appear in the output.
 */

type Block =
  | { type: 'h1' | 'h2' | 'h3'; text: string }
  | { type: 'p'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'ol'; items: string[] }

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function applyInline(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
    .replace(/`([^`\n]+)`/g, '<code>$1</code>')
}

function parseBlocks(markdown: string): Block[] {
  const lines = markdown.split('\n')
  const blocks: Block[] = []
  let listBuf: { ordered: boolean; items: string[] } | null = null

  const flushList = () => {
    if (!listBuf) return
    blocks.push(
      listBuf.ordered
        ? { type: 'ol', items: listBuf.items }
        : { type: 'ul', items: listBuf.items },
    )
    listBuf = null
  }

  for (const line of lines) {
    if (line.startsWith('### ')) {
      flushList()
      blocks.push({ type: 'h3', text: line.slice(4) })
    } else if (line.startsWith('## ')) {
      flushList()
      blocks.push({ type: 'h2', text: line.slice(3) })
    } else if (line.startsWith('# ')) {
      flushList()
      blocks.push({ type: 'h1', text: line.slice(2) })
    } else if (/^- /.test(line)) {
      if (listBuf?.ordered) flushList()
      if (!listBuf) listBuf = { ordered: false, items: [] }
      listBuf.items.push(line.slice(2))
    } else if (/^\d+\. /.test(line)) {
      if (listBuf && !listBuf.ordered) flushList()
      if (!listBuf) listBuf = { ordered: true, items: [] }
      listBuf.items.push(line.replace(/^\d+\. /, ''))
    } else if (line.trim() === '') {
      flushList()
    } else {
      flushList()
      blocks.push({ type: 'p', text: line })
    }
  }
  flushList()
  return blocks
}

interface MarkdownMessageProps {
  content: string
}

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  const blocks = parseBlocks(content)

  return (
    <div className="md">
      {blocks.map((block, i) => {
        switch (block.type) {
          case 'h1':
            return <h1 key={i} dangerouslySetInnerHTML={{ __html: applyInline(block.text) }} />
          case 'h2':
            return <h2 key={i} dangerouslySetInnerHTML={{ __html: applyInline(block.text) }} />
          case 'h3':
            return <h3 key={i} dangerouslySetInnerHTML={{ __html: applyInline(block.text) }} />
          case 'ul':
            return (
              <ul key={i}>
                {block.items.map((item, j) => (
                  <li key={j} dangerouslySetInnerHTML={{ __html: applyInline(item) }} />
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={i}>
                {block.items.map((item, j) => (
                  <li key={j} dangerouslySetInnerHTML={{ __html: applyInline(item) }} />
                ))}
              </ol>
            )
          case 'p':
          default:
            return <p key={i} dangerouslySetInnerHTML={{ __html: applyInline(block.text) }} />
        }
      })}
    </div>
  )
}
