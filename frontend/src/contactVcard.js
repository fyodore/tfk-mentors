/**
 * Build and download a vCard (.vcf) for phone contacts.
 * (vCard is the contact format for iPhone/Android; .ics is for calendar events.)
 */

/** @param {string} value */
function escapeVCardText(value) {
  return String(value ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

/**
 * @param {{
 *   firstName?: string,
 *   lastName?: string,
 *   phone?: string,
 *   email?: string,
 *   note?: string,
 * }} person
 */
export function buildVCard(person) {
  const firstName = (person.firstName || '').trim()
  const lastName = (person.lastName || '').trim()
  const phone = (person.phone || '').trim()
  const email = (person.email || '').trim()
  const note = (person.note || '').trim()
  const fullName = `${firstName} ${lastName}`.trim() || 'Contact'

  const lines = [
    'BEGIN:VCARD',
    'VERSION:3.0',
    `N:${escapeVCardText(lastName)};${escapeVCardText(firstName)};;;`,
    `FN:${escapeVCardText(fullName)}`,
  ]
  if (phone) {
    lines.push(`TEL;TYPE=CELL:${escapeVCardText(phone)}`)
  }
  if (email) {
    lines.push(`EMAIL;TYPE=INTERNET:${escapeVCardText(email)}`)
  }
  if (note) {
    lines.push(`NOTE:${escapeVCardText(note)}`)
  }
  lines.push('END:VCARD')
  return `${lines.join('\r\n')}\r\n`
}

/**
 * @param {{
 *   firstName?: string,
 *   lastName?: string,
 *   phone?: string,
 *   email?: string,
 *   note?: string,
 *   filenamePrefix?: string,
 * }} person
 */
export function downloadContactVCard(person) {
  const phone = (person.phone || '').trim()
  if (!phone) return

  const firstName = (person.firstName || '').trim()
  const lastName = (person.lastName || '').trim()
  const base =
    [firstName, lastName].filter(Boolean).join('_').replace(/[^\w.-]+/g, '_') ||
    'contact'
  const prefix = (person.filenamePrefix || '').replace(/[^\w.-]+/g, '_')
  const filename = `${prefix ? `${prefix}-` : ''}${base}.vcf`

  const blob = new Blob([buildVCard(person)], {
    type: 'text/vcard;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
