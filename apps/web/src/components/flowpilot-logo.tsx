/** FlowPilot marka işareti — sade, metin ağırlıklı logo. */

export function FlowPilotLogo() {
  return (
    <span className="inline-flex items-center gap-2 text-lg font-bold tracking-tight text-slate-900">
      <span
        aria-hidden="true"
        className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-black text-white"
      >
        FP
      </span>
      FlowPilot
    </span>
  );
}
