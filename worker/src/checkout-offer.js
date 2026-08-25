export function buildFanPriceMap(config) {
  const prices = new Map();
  const register = (baseSku, packages) => {
    for (const pack of packages || []) {
      const units = Math.max(1, Number(pack.unidades) || 1);
      const price = Number(pack.precio) || 0;
      if (!baseSku || price <= 0) continue;
      prices.set(units > 1 ? `${baseSku}-P${units}` : baseSku, price);
    }
  };
  register(String(config.sku || ""), config.paquetes);
  for (const size of config.tamanos || []) register(String(size.sku || ""), size.paquetes);
  return prices;
}

export function isOfferSku(sku, offer) {
  const bases = Array.isArray(offer.eligible_skus) ? offer.eligible_skus.map(String) : [];
  return bases.some((base) => sku === base || sku.startsWith(`${base}-P`));
}

export function isInactiveFanSku(sku, config) {
  const bases = Array.isArray(config.inactive_skus) ? config.inactive_skus.map(String) : [];
  return bases.some((base) => sku === base || sku.startsWith(`${base}-P`));
}

export function prepaidOfferValue(items, paymentMethod, subtotal, couponDiscount, offer) {
  if (!offer.activo || paymentMethod !== "prepaid" || !items.some((item) => isOfferSku(item.sku, offer))) return 0;
  const configured = Math.max(0, Number(offer.valor) || 0);
  const eligibleSubtotal = items.reduce((sum, item) => {
    if (!isOfferSku(item.sku, offer)) return sum;
    const lineTotal = Number(item.lineTotal);
    if (Number.isFinite(lineTotal)) return sum + Math.max(0, lineTotal);
    return sum + Math.max(0, Number(item.unitPrice) || 0) * Math.max(1, Number(item.quantity) || 1);
  }, 0);
  const value = offer.tipo === "percent"
    ? eligibleSubtotal * configured / 100
    : offer.tipo === "fixed" ? configured : 0;
  return Math.round(Math.min(value, Math.max(0, subtotal - couponDiscount)) * 100) / 100;
}
