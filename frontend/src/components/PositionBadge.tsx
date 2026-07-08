const POSITION_COLORS: Record<string, string> = {
  PG: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  SG: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300",
  SF: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  PF: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
  C: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
};

const POSITION_LABELS: Record<string, string> = {
  PG: "Base",
  SG: "Escolta",
  SF: "Alero",
  PF: "Ala-pívot",
  C: "Pívot",
};

interface Props {
  position: string | null | undefined;
  short?: boolean;
}

export function PositionBadge({ position, short = false }: Props) {
  if (!position) return null;
  const color = POSITION_COLORS[position] ?? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  const label = short ? position : (POSITION_LABELS[position] ?? position);
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-semibold ${color}`}>
      {label}
    </span>
  );
}
