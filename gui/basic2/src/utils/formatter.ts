// Value formatting utilities

// Superscript characters for exponents
const SUPERSCRIPTS: Record<string, string> = {
  '-': '⁻',
  '0': '⁰',
  '1': '¹',
  '2': '²',
  '3': '³',
  '4': '⁴',
  '5': '⁵',
  '6': '⁶',
  '7': '⁷',
  '8': '⁸',
  '9': '⁹',
};

// SI prefixes by exponent
const SI_PREFIXES = new Map<number, string>([
  [-15, 'f'],
  [-12, 'p'],
  [-9, 'n'],
  [-6, 'µ'],
  [-3, 'm'],
  [3, 'k'],
  [6, 'M'],
  [9, 'G'],
  [12, 'T'],
  [15, 'P'],
]);

// Group integer part with spaces (e.g., "1234567" -> "1 234 567")
function groupIntPart(s: string): string {
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// Group fractional part with spaces (e.g., "123456" -> "123 456")
function groupFracPart(s: string): string {
  return s.replace(/(\d{3})(?=\d)/g, '$1 ');
}

// Group both sides of decimal point
function groupNumberString(s: string): string {
  if (!s.includes('.')) return groupIntPart(s);
  const parts = s.split('.');
  const intPart = parts[0] || '0';
  const fracPart = parts[1] || '';
  return groupIntPart(intPart) + '.' + groupFracPart(fracPart);
}

// Remove trailing zeros and trailing dot
function trimZeros(s: string): string {
  return s.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.$/, '');
}

// Convert number to superscript string
function toSuperscript(exp: number): string {
  return String(exp)
    .split('')
    .map((ch) => SUPERSCRIPTS[ch] || ch)
    .join('');
}

// Format in engineering notation (exponent multiple of 3)
function formatEngineering(x: number, sig = 4, unit = ''): string {
  if (x === 0) return '0';
  const ax = Math.abs(x);
  let exp = Math.floor(Math.log10(ax) / 3) * 3;
  if (!isFinite(exp)) exp = 0;

  const mant = x / Math.pow(10, exp);
  const m = Number(mant.toPrecision(sig));
  const mStr = trimZeros(m.toString());

  // Use SI prefix if available and unit provided
  const prefix = SI_PREFIXES.get(exp);
  if (unit && prefix) {
    return `${mStr} ${prefix}${unit}`;
  }

  // Fallback: ×10ⁿ with superscript exponent
  const expStr = toSuperscript(exp);
  return `${mStr} ×10${expStr}${unit ? ' ' + unit : ''}`;
}

// Format decimal with grouping
function formatDecimalGrouped(x: number, maxDp = 4): string {
  const s = x.toFixed(maxDp);
  const trimmed = trimZeros(s);
  return groupNumberString(trimmed);
}

/**
 * Format a value for display with optional unit
 */
export function formatValue(v: unknown, unit?: string | null): string {
  if (v == null) return '—';
  const u = (unit || '').trim();

  if (typeof v === 'object') {
    return JSON.stringify(v);
  }

  if (typeof v === 'boolean') {
    return v ? 'true' : 'false';
  }

  if (typeof v === 'number') {
    if (!isFinite(v)) return String(v) + (u ? ' ' + u : '');
    if (v === 0) return '0' + (u ? ' ' + u : '');

    const ax = Math.abs(v);
    const SMALL = 1e-2;
    const LARGE = 1e6;

    // Integers (small-ish): just group
    if (Number.isInteger(v) && ax < LARGE) {
      return groupIntPart(v.toString()) + (u ? ' ' + u : '');
    }

    // Engineering for very small or very large
    if (ax < SMALL || ax >= LARGE) {
      return formatEngineering(v, 4, u);
    }

    // Regular decimal with grouping
    return formatDecimalGrouped(v, 4) + (u ? ' ' + u : '');
  }

  // v is a string at this point (all other types handled above)
  return v as string;
}

/**
 * Infer display type from property spec
 */
export function inferType(prop: {
  type?: string;
  choices?: unknown[];
  min?: number;
  max?: number;
}): string {
  if (!prop) return 'Any';
  if (prop.choices?.length) {
    const t = typeof prop.choices[0];
    return t === 'string' ? 'Literal' : t;
  }
  if (prop.min != null || prop.max != null) return 'float';
  return prop.type || 'Any';
}

/**
 * Get step value for number inputs
 */
export function getNumStep(meta: { step?: number; type?: string }): string | number {
  if (meta?.step != null) return meta.step;
  return meta?.type === 'int' ? 1 : 'any';
}
