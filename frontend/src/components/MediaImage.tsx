// Renders a stored media asset (team logo / player photo) when available,
// otherwise an initials fallback. Media `url` is null whenever nothing is
// stored or the asset is under a takedown (see docs/team-member-enrichment-plan
// §4.3), so a graceful fallback is always required.

import { BACKEND_ORIGIN } from "@/lib/api";
import type { MediaAsset } from "@/types/api";

export function MediaImage({
  asset,
  alt,
  initials,
  size = 96,
  color,
  rounded = "full",
  fill = false,
}: {
  asset: MediaAsset | null;
  alt: string;
  initials: string;
  size?: number;
  color?: string;
  rounded?: "full" | "lg";
  fill?: boolean;
}) {
  const radius = rounded === "full" ? "rounded-full" : "rounded-lg";
  const fillStyle: React.CSSProperties = fill
    ? { width: "100%", height: "100%", objectFit: "cover" }
    : { width: size, height: size };

  if (asset?.url) {
    // The API returns root-relative paths (e.g. /media/...) so we prepend the
    // backend's public origin. Absolute URLs (CDN in production) are used as-is.
    const src = asset.url.startsWith("/")
      ? `${BACKEND_ORIGIN}${asset.url}`
      : asset.url;
    // Stored media of unknown dimensions from external sources; next/image adds
    // little here and would need per-host allow-listing, so a plain img is used.
    // Inline style overrides any CSS-reset that would ignore the HTML attributes.
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={alt}
        title={asset.attribution || alt}
        width={fill ? undefined : size}
        height={fill ? undefined : size}
        className={`${radius} ${fill ? "object-cover" : "object-contain bg-zinc-100 dark:bg-zinc-800 flex-shrink-0"}`}
        style={fillStyle}
      />
    );
  }

  return (
    <div
      aria-label={alt}
      className={`${radius} flex ${fill ? "" : "flex-shrink-0"} items-center justify-center font-semibold text-white`}
      style={{
        ...fillStyle,
        backgroundColor: color || "#3f3f46",
        fontSize: fill ? "2rem" : size * 0.36,
      }}
    >
      {initials}
    </div>
  );
}
