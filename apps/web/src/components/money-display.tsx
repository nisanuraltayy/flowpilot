/** Kuruş (minor unit) → TL gösterimi. Float ile hesaplanmaz (bkz. lib/money). */

import { formatMinorAsTry } from "@/lib/money";

interface MoneyDisplayProps {
  readonly amountMinor: number;
  readonly className?: string;
}

export function MoneyDisplay({ amountMinor, className }: MoneyDisplayProps) {
  return <span className={className}>{formatMinorAsTry(amountMinor)}</span>;
}
