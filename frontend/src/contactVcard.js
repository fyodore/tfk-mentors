/**
 * Build and download mentor/coach contact cards.
 * Uses .ics with an attached vCard so iPhone Safari can open and save the contact.
 */

/** @param {string} value */
function escapeVCardText(value) {
  return String(value ?? '')
    .replace(/\\/g, '\\\\')
    .replace(/\n/g, '\\n')
    .replace(/,/g, '\\,')
    .replace(/;/g, '\\;')
}

/** @param {string} value */
function escapeIcsText(value) {
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

/** @param {Date} date */
function icsUtcStamp(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`
  )
}

/** @param {string} text */
function utf8ToBase64(text) {
  const bytes = new TextEncoder().encode(text)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

/**
 * Fold base64 for ICS ATTACH (RFC 5545 / Apple Contacts).
 * @param {string} b64
 */
function foldBase64ForIcs(b64) {
  const chunks = b64.match(/.{1,74}/g) || []
  return chunks.map((line) => ` ${line}`).join('\r\n')
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
 * @param {string} vcfFilename
 */
export function buildContactIcs(person, vcfFilename) {
  const firstName = (person.firstName || '').trim()
  const lastName = (person.lastName || '').trim()
  const fullName = `${firstName} ${lastName}`.trim() || 'Contact'
  const vcard = buildVCard(person)
  const folded = foldBase64ForIcs(utf8ToBase64(vcard))
  const now = new Date()
  const stamp = icsUtcStamp(now)
  const day = stamp.slice(0, 8)
  const safeName = fullName.replace(/[^\w.-]+/g, '_') || 'contact'
  const uid = `tfk-contact-${safeName}-${stamp}@tfkmentors`

  const attachHeader =
    'ATTACH;VALUE=BINARY;ENCODING=BASE64;FMTTYPE=text/directory;\r\n' +
    ` X-APPLE-FILENAME=${vcfFilename}:`

  return [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//TFK Mentors//Contact//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${uid}`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${day}`,
    `SUMMARY:${escapeIcsText(fullName)}`,
    `DESCRIPTION:${escapeIcsText(`Contact card for ${fullName}`)}`,
    `${attachHeader}\r\n${folded}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ].join('\r\n') + '\r\n'
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
function contactFilenameParts(person) {
  const firstName = (person.firstName || '').trim()
  const lastName = (person.lastName || '').trim()
  const base =
    [firstName, lastName].filter(Boolean).join('_').replace(/[^\w.-]+/g, '_') ||
    'contact'
  const prefix = (person.filenamePrefix || '').replace(/[^\w.-]+/g, '_')
  const stem = `${prefix ? `${prefix}-` : ''}${base}`
  return { base, stem }
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

  const { stem } = contactFilenameParts(person)
  const filename = `${stem}.vcf`

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

/**
 * Download an .ics calendar file with the contact attached as a vCard.
 * @param {{
 *   firstName?: string,
 *   lastName?: string,
 *   phone?: string,
 *   email?: string,
 *   note?: string,
 *   filenamePrefix?: string,
 * }} person
 */
export function downloadContactIcs(person) {
  const phone = (person.phone || '').trim()
  if (!phone) return

  const { stem } = contactFilenameParts(person)
  const vcfFilename = `${stem}.vcf`
  const filename = `${stem}.ics`

  const blob = new Blob([buildContactIcs(person, vcfFilename)], {
    type: 'text/calendar;charset=utf-8',
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
