// Site-wide constants.
//
// The rights-holder takedown contact (docs/team-member-enrichment-plan.md §3) is
// read from NEXT_PUBLIC_CONTACT_EMAIL so each deployment sets its own address.
// The fallback is a clearly-placeholder value to replace before going public.
export const CONTACT_EMAIL =
  process.env.NEXT_PUBLIC_CONTACT_EMAIL ?? "derechos@basketstats.example";

export const GITHUB_URL =
  process.env.NEXT_PUBLIC_GITHUB_URL ??
  "https://github.com/jpablogg/basquetestads";
