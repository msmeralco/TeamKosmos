import type { PackageRow } from "./api";

/* Packages without an installer photo come with a generated drawing (a /packages/*.svg path).
   Show a stock photo of the same kind of system instead. The data is not changed. */

export type PackagePhoto = { src: string; kind: "stock" | "installer" };

const STOCK = "/packages/stock";

export function packagePhoto(p: Pick<PackageRow, "photo" | "type" | "kwp">): PackagePhoto | null {
  if (!p.photo) return null;
  if (!p.photo.toLowerCase().endsWith(".svg")) return { src: p.photo, kind: "installer" };
  if (p.type === "off-grid") return { src: `${STOCK}/${p.kwp <= 5 ? "ground-field" : "aerial-array"}.jpg`, kind: "stock" };
  if (p.kwp < 5) return { src: `${STOCK}/roof-small.jpg`, kind: "stock" };
  if (p.kwp < 8) return { src: `${STOCK}/roof-medium.jpg`, kind: "stock" };
  return { src: `${STOCK}/roof-large.jpg`, kind: "stock" };
}

/** Price per kWp, rounded to the peso. */
export const pricePerKwp = (p: Pick<PackageRow, "price_php" | "kwp">): number => (p.kwp > 0 ? Math.round(p.price_php / p.kwp) : 0);
