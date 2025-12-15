// Utilities
function groupIntPart(s : string) {
  // "1234567" -> "1 234 567"
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}
function groupFracPart(s : string) {
  // "123456" -> "123 456" (groups every 3 after the decimal)
  return s.replace(/(\d{3})(?=\d)/g, "$1 ");
}
function groupNumberString(s : string) {
  // groups both sides of the decimal point with spaces
  if (!s.includes(".")) return groupIntPart(s);
  const [i, f] = s.split(".");
  return groupIntPart(i) + "." + groupFracPart(f);
}
function trimZeros(s : string) {
  // remove trailing zeros and trailing dot
  return s.replace(/(\.\d*?[1-9])0+$/,"$1").replace(/\.$/,"");
}

const SUPERSCRIPTS: Record<string, string> = {
  "-": "⁻",
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};
const SI_PREFIXES = new Map<number, string>([
  [-15, "f"], 
  [-12, "p"], 
  [-9, "n"], 
  [-6, "µ"], 
  [-3, "m"],
  [3, "k"], 
  [6, "M"], 
  [9, "G"], 
  [12, "T"], 
  [15, "P"],
]);
// Convert exponent to superscript string    


function toSuperscript(exp: number) : string {
  return String(exp)
    .split("")
    .map((ch) => SUPERSCRIPTS[ch] || ch)
    .join("");
}
// Core formatters
function formatEngineering(x : number, sig = 4, unit = "") : string {
  if (x === 0) return "0";
  const ax = Math.abs(x);
  // exponent multiple of 3
  let exp = Math.floor(Math.log10(ax) / 3) * 3;
  // avoid silly exponents like 1e-0
  if (!isFinite(exp)) exp = 0;
  const mant = x / Math.pow(10, exp);
  // mantissa with N significant digits
  const m = Number(mant.toPrecision(sig));
  // Use regular decimal for the mantissa (no sci there), then group if needed
  const mStr = trimZeros(m.toString());

  // if a valid SI prefix is available and unit provided → use prefix
  const prefix = SI_PREFIXES.get(exp); // exp is a number

  if (unit && prefix) {
   return `${mStr} ${prefix}${unit}`;
  }

  // fallback: ×10ⁿ with superscript exponent
  const expStr = toSuperscript(exp);
  return `${mStr} ×10${expStr}${unit ? " " + unit : ""}`;
}

function formatDecimalGrouped(x: number, maxDp = 4) {
  // round to maxDp, then trim zeros, then group both sides
  const s = x.toFixed(maxDp);
  const trimmed = trimZeros(s);
  return groupNumberString(trimmed);
}

// Main function
export function formatCurrent(v: any, unit: string | null): string {
  if (v == null) return "—";
  if (unit == null) unit = "";
  unit = unit.trim();

  if (typeof v === "object") return JSON.stringify(v);

  if (typeof v === "number") {
    if (!isFinite(v)) return String(v)+" "+unit;
    if (v === 0) return "0";

    const ax = Math.abs(v);
    // thresholds: small -> engineering; large -> engineering
    const SMALL = 1e-2;
    const LARGE = 1e6;

    // Integers (small-ish): just group
    if (Number.isInteger(v) && ax < LARGE) {
      return groupIntPart(v.toString())+" " +unit;
    }

    // Engineering for very small or very large
    if (ax < SMALL || ax >= LARGE) {
      return formatEngineering(v, 4, unit); // 4 significant digits in mantissa
    }

    // Regular decimal with grouping
    return formatDecimalGrouped(v, 4)+" "+unit; // up to 4 decimals
  }

  return String(v);
}