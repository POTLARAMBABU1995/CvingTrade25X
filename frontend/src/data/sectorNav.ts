export type SectorNavItem = {
  href: string;
  label: string;
  page: string;
};

export type SectorPageItem = {
  code: string;
  href: string;
  label: string;
  page: string;
  slug: string;
};

export const SECTOR_DIRECTORY_PAGE = '/app/sector/stocks/auto';
export const SECTOR_OVERVIEW_PAGE = '/app/sector/overview';
export const STOCKEDGE_SECTOR_ROTATION_PAGE = '/app/sector/stockedge-rotation';

export const sectorNavItems = [
  { href: '/app/sector/rotation', label: 'Sector Rotation', page: '/app/sector/rotation' },
  {
    href: STOCKEDGE_SECTOR_ROTATION_PAGE,
    label: 'StockEdge Sector Rotation',
    page: STOCKEDGE_SECTOR_ROTATION_PAGE,
  },
  { href: SECTOR_OVERVIEW_PAGE, label: 'Sector_Overview', page: SECTOR_OVERVIEW_PAGE },
  { href: '/app/sector/stocks/auto', label: 'Sector Wise Stocks', page: SECTOR_DIRECTORY_PAGE },
] satisfies ReadonlyArray<SectorNavItem>;

export const sectorDropdownNavItems = [
  ...sectorNavItems,
] satisfies ReadonlyArray<SectorNavItem>;

export const sectorPageItems = [
  { href: '/app/sector/stocks/agriculture', label: 'Agriculture', page: '/app/sector/stocks/agriculture', code: 'AGRICULTURE', slug: 'agriculture' },
  { href: '/app/sector/stocks/fertilizers-agrochemicals', label: 'Fertilizers & Agrochemicals', page: '/app/sector/stocks/fertilizers-agrochemicals', code: 'FERTILIZERS_AGROCHEMICALS', slug: 'fertilizers-agrochemicals' },
  { href: '/app/sector/stocks/pesticides-agrochemicals', label: 'Pesticides & Agrochemicals', page: '/app/sector/stocks/pesticides-agrochemicals', code: 'PESTICIDES_AGROCHEMICALS', slug: 'pesticides-agrochemicals' },
  { href: '/app/sector/stocks/auto', label: 'Auto Mobile', page: '/app/sector/stocks/auto', code: 'AUTO', slug: 'auto' },
  { href: '/app/sector/stocks/alcohol-breweries', label: 'Alcohol Breweries', page: '/app/sector/stocks/alcohol-breweries', code: 'ALCOHOL_BREWERIES', slug: 'alcohol-breweries' },
  { href: '/app/sector/stocks/auto-ancillaries', label: 'Auto Ancillaries', page: '/app/sector/stocks/auto-ancillaries', code: 'AUTO_ANCILLARIES', slug: 'auto-ancillaries' },
  { href: '/app/sector/stocks/auto-components-equipments', label: 'Auto Components & Equipments', page: '/app/sector/stocks/auto-components-equipments', code: 'AUTO_COMPONENTS_EQUIPMENTS', slug: 'auto-components-equipments' },
  { href: '/app/sector/stocks/bank', label: 'Bank', page: '/app/sector/stocks/bank', code: 'BANK', slug: 'bank' },
  { href: '/app/sector/stocks/capital-goods', label: 'Capital Goods', page: '/app/sector/stocks/capital-goods', code: 'CAPITAL_GOODS', slug: 'capital-goods' },
  { href: '/app/sector/stocks/cement-cement-products', label: 'Cement & Cement Products', page: '/app/sector/stocks/cement-cement-products', code: 'CEMENT_CEMENT_PRODUCTS', slug: 'cement-cement-products' },
  { href: '/app/sector/stocks/chemicals', label: 'Chemicals', page: '/app/sector/stocks/chemicals', code: 'CHEMICALS', slug: 'chemicals' },
  { href: '/app/sector/stocks/specialty-chemicals', label: 'Specialty Chemicals', page: '/app/sector/stocks/specialty-chemicals', code: 'SPECIALTY_CHEMICALS', slug: 'specialty-chemicals' },
  { href: '/app/sector/stocks/petrochemicals', label: 'Petrochemicals', page: '/app/sector/stocks/petrochemicals', code: 'PETROCHEMICALS', slug: 'petrochemicals' },
  { href: '/app/sector/stocks/paints', label: 'Paints', page: '/app/sector/stocks/paints', code: 'PAINTS', slug: 'paints' },
  { href: '/app/sector/stocks/plastic-products', label: 'Plastic Products', page: '/app/sector/stocks/plastic-products', code: 'PLASTIC_PRODUCTS', slug: 'plastic-products' },
  { href: '/app/sector/stocks/explosives', label: 'Explosives', page: '/app/sector/stocks/explosives', code: 'EXPLOSIVES', slug: 'explosives' },
  { href: '/app/sector/stocks/abrasives', label: 'Abrasives', page: '/app/sector/stocks/abrasives', code: 'ABRASIVES', slug: 'abrasives' },
  { href: '/app/sector/stocks/electrodes-refractories', label: 'Electrodes & Refractories', page: '/app/sector/stocks/electrodes-refractories', code: 'ELECTRODES_REFRACTORIES', slug: 'electrodes-refractories' },
  { href: '/app/sector/stocks/construction', label: 'Construction', page: '/app/sector/stocks/construction', code: 'CONSTRUCTION', slug: 'construction' },
  { href: '/app/sector/stocks/construction-materials', label: 'Construction Materials', page: '/app/sector/stocks/construction-materials', code: 'CONSTRUCTION_MATERIALS', slug: 'construction-materials' },
  { href: '/app/sector/stocks/infrastructure', label: 'Infrastructure', page: '/app/sector/stocks/infrastructure', code: 'INFRASTRUCTURE', slug: 'infrastructure' },
  { href: '/app/sector/stocks/consumer-durables', label: 'Consumer Durables', page: '/app/sector/stocks/consumer-durables', code: 'CONSUMER_DURABLES', slug: 'consumer-durables' },
  { href: '/app/sector/stocks/electronics-services-consumer-durables', label: 'Electronics & Services Consumer Durables', page: '/app/sector/stocks/electronics-services-consumer-durables', code: 'ELECTRONICS_SERVICES_CONSUMER_DURABLES', slug: 'electronics-services-consumer-durables' },
  { href: '/app/sector/stocks/consumer-electronics', label: 'Consumer Electronics', page: '/app/sector/stocks/consumer-electronics', code: 'CONSUMER_ELECTRONICS', slug: 'consumer-electronics' },
  { href: '/app/sector/stocks/consumer-services', label: 'Consumer Services', page: '/app/sector/stocks/consumer-services', code: 'CONSUMER_SERVICES', slug: 'consumer-services' },
  { href: '/app/sector/stocks/financial-services', label: 'Financial Services', page: '/app/sector/stocks/financial-services', code: 'FIN_SERV', slug: 'financial-services' },
  { href: '/app/sector/stocks/fmcg', label: 'FMCG', page: '/app/sector/stocks/fmcg', code: 'FMCG', slug: 'fmcg' },
  { href: '/app/sector/stocks/household-personal-products', label: 'Household & Personal Products', page: '/app/sector/stocks/household-personal-products', code: 'HOUSEHOLD_PERSONAL_PRODUCTS', slug: 'household-personal-products' },
  { href: '/app/sector/stocks/healthcare', label: 'Healthcare', page: '/app/sector/stocks/healthcare', code: 'HEALTHCARE', slug: 'healthcare' },
  { href: '/app/sector/stocks/biotechnology', label: 'Biotechnology', page: '/app/sector/stocks/biotechnology', code: 'BIOTECHNOLOGY', slug: 'biotechnology' },
  { href: '/app/sector/stocks/medical-equipment-supplies', label: 'Medical Equipment & Supplies', page: '/app/sector/stocks/medical-equipment-supplies', code: 'MEDICAL_EQUIPMENT_SUPPLIES', slug: 'medical-equipment-supplies' },
  { href: '/app/sector/stocks/it', label: 'IT', page: '/app/sector/stocks/it', code: 'IT', slug: 'it' },
  { href: '/app/sector/stocks/it-enabled-services', label: 'IT Enabled Services', page: '/app/sector/stocks/it-enabled-services', code: 'IT_ENABLED_SERVICES', slug: 'it-enabled-services' },
  { href: '/app/sector/stocks/software-products-services', label: 'Software Products & Services', page: '/app/sector/stocks/software-products-services', code: 'SOFTWARE_PRODUCTS_SERVICES', slug: 'software-products-services' },
  { href: '/app/sector/stocks/media', label: 'Media', page: '/app/sector/stocks/media', code: 'MEDIA', slug: 'media' },
  { href: '/app/sector/stocks/media-entertainment', label: 'Media & Entertainment', page: '/app/sector/stocks/media-entertainment', code: 'MEDIA_ENTERTAINMENT', slug: 'media-entertainment' },
  { href: '/app/sector/stocks/print-media-publishing', label: 'Print Media & Publishing', page: '/app/sector/stocks/print-media-publishing', code: 'PRINT_MEDIA_PUBLISHING', slug: 'print-media-publishing' },
  { href: '/app/sector/stocks/metal', label: 'Metal', page: '/app/sector/stocks/metal', code: 'METAL', slug: 'metal' },
  { href: '/app/sector/stocks/metals-mining', label: 'Metals & Mining', page: '/app/sector/stocks/metals-mining', code: 'METALS_MINING', slug: 'metals-mining' },
  { href: '/app/sector/stocks/iron-steel', label: 'Iron & Steel', page: '/app/sector/stocks/iron-steel', code: 'IRON_STEEL', slug: 'iron-steel' },
  { href: '/app/sector/stocks/mining', label: 'Mining', page: '/app/sector/stocks/mining', code: 'MINING', slug: 'mining' },
  { href: '/app/sector/stocks/non-ferrous-metals', label: 'Non-Ferrous Metals', page: '/app/sector/stocks/non-ferrous-metals', code: 'NON_FERROUS_METALS', slug: 'non-ferrous-metals' },
  { href: '/app/sector/stocks/midsmall-it-telecom', label: 'Midsmall IT Telecom', page: '/app/sector/stocks/midsmall-it-telecom', code: 'MIDSMALL_IT_TELECOM', slug: 'midsmall-it-telecom' },
  { href: '/app/sector/stocks/oil-and-gas', label: 'Oil & Gas', page: '/app/sector/stocks/oil-and-gas', code: 'OIL_AND_GAS', slug: 'oil-and-gas' },
  { href: '/app/sector/stocks/lpg-cng-png-lng-supplier', label: 'LPG CNG PNG LNG Supplier', page: '/app/sector/stocks/lpg-cng-png-lng-supplier', code: 'LPG_CNG_PNG_LNG_SUPPLIER', slug: 'lpg-cng-png-lng-supplier' },
  { href: '/app/sector/stocks/lubricants', label: 'Lubricants', page: '/app/sector/stocks/lubricants', code: 'LUBRICANTS', slug: 'lubricants' },
  { href: '/app/sector/stocks/oil-equipment-services', label: 'Oil Equipment & Services', page: '/app/sector/stocks/oil-equipment-services', code: 'OIL_EQUIPMENT_SERVICES', slug: 'oil-equipment-services' },
  { href: '/app/sector/stocks/petroleum-products-refineries', label: 'Petroleum Products & Refineries', page: '/app/sector/stocks/petroleum-products-refineries', code: 'PETROLEUM_PRODUCTS_REFINERIES', slug: 'petroleum-products-refineries' },
  { href: '/app/sector/stocks/pharma', label: 'Pharma', page: '/app/sector/stocks/pharma', code: 'PHARMA', slug: 'pharma' },
  { href: '/app/sector/stocks/power', label: 'Power', page: '/app/sector/stocks/power', code: 'POWER', slug: 'power' },
  { href: '/app/sector/stocks/private-bank', label: 'Private Bank', page: '/app/sector/stocks/private-bank', code: 'PRIVATE_BANK', slug: 'private-bank' },
  { href: '/app/sector/stocks/psu-bank', label: 'PSU Bank', page: '/app/sector/stocks/psu-bank', code: 'PSU_BANK', slug: 'psu-bank' },
  { href: '/app/sector/stocks/realty-real-estate', label: 'Realty Real Estate', page: '/app/sector/stocks/realty-real-estate', code: 'REALTY_REAL_ESTATE', slug: 'realty-real-estate' },
  { href: '/app/sector/stocks/restaurants', label: 'Restaurants', page: '/app/sector/stocks/restaurants', code: 'RESTAURANTS', slug: 'restaurants' },
  { href: '/app/sector/stocks/hospitality-hotels-resorts', label: 'Hospitality Hotels & Resorts', page: '/app/sector/stocks/hospitality-hotels-resorts', code: 'HOSPITALITY_HOTELS_RESORTS', slug: 'hospitality-hotels-resorts' },
  { href: '/app/sector/stocks/tourism-travel', label: 'Tourism & Travel', page: '/app/sector/stocks/tourism-travel', code: 'TOURISM_TRAVEL', slug: 'tourism-travel' },
  { href: '/app/sector/stocks/education-e-learning', label: 'Education & E-Learning', page: '/app/sector/stocks/education-e-learning', code: 'EDUCATION_E_LEARNING', slug: 'education-e-learning' },
  { href: '/app/sector/stocks/services', label: 'Services', page: '/app/sector/stocks/services', code: 'SERVICES', slug: 'services' },
  { href: '/app/sector/stocks/telecommunication', label: 'Telecommunication', page: '/app/sector/stocks/telecommunication', code: 'TELECOMMUNICATION', slug: 'telecommunication' },
  { href: '/app/sector/stocks/utilities', label: 'Utilities', page: '/app/sector/stocks/utilities', code: 'UTILITIES', slug: 'utilities' },
  { href: '/app/sector/stocks/waste-water-management', label: 'Waste & Water Management', page: '/app/sector/stocks/waste-water-management', code: 'WASTE_WATER_MANAGEMENT', slug: 'waste-water-management' },
  { href: '/app/sector/stocks/nbfc', label: 'NBFC', page: '/app/sector/stocks/nbfc', code: 'NBFC', slug: 'nbfc' },
  { href: '/app/sector/stocks/insurance', label: 'Insurance', page: '/app/sector/stocks/insurance', code: 'INSURANCE', slug: 'insurance' },
  { href: '/app/sector/stocks/capital-markets', label: 'Capital Markets', page: '/app/sector/stocks/capital-markets', code: 'CAPITAL_MARKETS', slug: 'capital-markets' },
  { href: '/app/sector/stocks/asset-management-company', label: 'Asset Management Company', page: '/app/sector/stocks/asset-management-company', code: 'ASSET_MANAGEMENT_COMPANY', slug: 'asset-management-company' },
  { href: '/app/sector/stocks/fintech', label: 'Fintech', page: '/app/sector/stocks/fintech', code: 'FINTECH', slug: 'fintech' },
  { href: '/app/sector/stocks/housing-finance-company', label: 'Housing Finance Company', page: '/app/sector/stocks/housing-finance-company', code: 'HOUSING_FINANCE_COMPANY', slug: 'housing-finance-company' },
  { href: '/app/sector/stocks/stockbroking-and-allied', label: 'Stockbroking & Allied', page: '/app/sector/stocks/stockbroking-and-allied', code: 'STOCKBROKING_AND_ALLIED', slug: 'stockbroking-and-allied' },
  { href: '/app/sector/stocks/rubber-products-tyres', label: 'Rubber Products Tyres', page: '/app/sector/stocks/rubber-products-tyres', code: 'RUBBER_PRODUCTS_TYRES', slug: 'rubber-products-tyres' },
  { href: '/app/sector/stocks/aviation-air-transport', label: 'Aviation Air Transport', page: '/app/sector/stocks/aviation-air-transport', code: 'AVIATION_AIR_TRANSPORT', slug: 'aviation-air-transport' },
  { href: '/app/sector/stocks/logistics-shipping', label: 'Logistics Shipping', page: '/app/sector/stocks/logistics-shipping', code: 'LOGISTICS_SHIPPING', slug: 'logistics-shipping' },
  { href: '/app/sector/stocks/port-and-port-services', label: 'Port & Port Services', page: '/app/sector/stocks/port-and-port-services', code: 'PORT_AND_PORT_SERVICES', slug: 'port-and-port-services' },
  { href: '/app/sector/stocks/road-rail-transport', label: 'Road Rail Transport', page: '/app/sector/stocks/road-rail-transport', code: 'ROAD_RAIL_TRANSPORT', slug: 'road-rail-transport' },
  { href: '/app/sector/stocks/transport-infrastructure', label: 'Transport Infrastructure', page: '/app/sector/stocks/transport-infrastructure', code: 'TRANSPORT_INFRASTRUCTURE', slug: 'transport-infrastructure' },
  { href: '/app/sector/stocks/engineering', label: 'Engineering', page: '/app/sector/stocks/engineering', code: 'ENGINEERING', slug: 'engineering' },
  { href: '/app/sector/stocks/electricals-heavy-electrical-equipment', label: 'Electricals Heavy Electrical Equipment', page: '/app/sector/stocks/electricals-heavy-electrical-equipment', code: 'ELEC_HEAVY_EQUIPMENT', slug: 'electricals-heavy-electrical-equipment' },
  { href: '/app/sector/stocks/industrial-manufacturing', label: 'Industrial Manufacturing', page: '/app/sector/stocks/industrial-manufacturing', code: 'INDUSTRIAL_MANUFACTURING', slug: 'industrial-manufacturing' },
  { href: '/app/sector/stocks/industrial-products', label: 'Industrial Products', page: '/app/sector/stocks/industrial-products', code: 'INDUSTRIAL_PRODUCTS', slug: 'industrial-products' },
  { href: '/app/sector/stocks/industrial-gases-fuels', label: 'Industrial Gases & Fuels', page: '/app/sector/stocks/industrial-gases-fuels', code: 'INDUSTRIAL_GASES_FUELS', slug: 'industrial-gases-fuels' },
  { href: '/app/sector/stocks/commodities-trading', label: 'Commodities & Trading', page: '/app/sector/stocks/commodities-trading', code: 'COMMODITIES_TRADING', slug: 'commodities-trading' },
  { href: '/app/sector/stocks/defence-aerospace-defense', label: 'Defence Aerospace & Defense', page: '/app/sector/stocks/defence-aerospace-defense', code: 'DEFENCE_AEROSPACE_DEFENSE', slug: 'defence-aerospace-defense' },
  { href: '/app/sector/stocks/diversified', label: 'Diversified', page: '/app/sector/stocks/diversified', code: 'DIVERSIFIED', slug: 'diversified' },
  { href: '/app/sector/stocks/paper-packaging', label: 'Paper & Packaging', page: '/app/sector/stocks/paper-packaging', code: 'PAPER_PACKAGING', slug: 'paper-packaging' },
  { href: '/app/sector/stocks/retailing-speciality-retail', label: 'Retailing Speciality Retail', page: '/app/sector/stocks/retailing-speciality-retail', code: 'RETAILING_SPECIALITY_RETAIL', slug: 'retailing-speciality-retail' },
  { href: '/app/sector/stocks/ecommerce-eretai', label: 'E-Commerce E-Retail', page: '/app/sector/stocks/ecommerce-eretai', code: 'ECOMMERCE_ERETAI', slug: 'ecommerce-eretai' },
  { href: '/app/sector/stocks/footwear', label: 'Footwear', page: '/app/sector/stocks/footwear', code: 'FOOTWEAR', slug: 'footwear' },
  { href: '/app/sector/stocks/gems', label: 'Gems', page: '/app/sector/stocks/gems', code: 'GEMS', slug: 'gems' },
  { href: '/app/sector/stocks/jewellery-watches', label: 'Jewellery & Watches', page: '/app/sector/stocks/jewellery-watches', code: 'JEWELLERY_WATCHES', slug: 'jewellery-watches' },
  { href: '/app/sector/stocks/leather-leather-products', label: 'Leather & Leather Products', page: '/app/sector/stocks/leather-leather-products', code: 'LEATHER_LEATHER_PRODUCTS', slug: 'leather-leather-products' },
  { href: '/app/sector/stocks/textiles-apparels', label: 'Textiles & Apparels', page: '/app/sector/stocks/textiles-apparels', code: 'TEXTILES_APPARELS', slug: 'textiles-apparels' },
] satisfies ReadonlyArray<SectorPageItem>;

const sectorCodeAliases: Record<string, string> = {
  CONS_DUR: 'CONSUMER_DURABLES',
  ELEC_SERVICES_CONS_DURABLES: 'ELECTRONICS_SERVICES_CONSUMER_DURABLES',
  ELEC_HEAVY_EQUIP: 'ELEC_HEAVY_EQUIPMENT',
  ELECTRICALS_HEAVY_ELECTRICAL_EQUIPMENT: 'ELEC_HEAVY_EQUIPMENT',
  FINANCIAL_SERVICES: 'FIN_SERV',
  HEALTH: 'HEALTHCARE',
  HEALTHCARE_INDEX: 'HEALTHCARE',
  MID_HEALTH: 'HEALTHCARE',
  MIDSMALL_HEALTHCARE: 'HEALTHCARE',
  NIFTY500_HEALTHCARE: 'HEALTHCARE',
  OIL_GAS: 'OIL_AND_GAS',
  PVT_BANK: 'PRIVATE_BANK',
  TELECOM: 'TELECOMMUNICATION',
};

const sectorPathAliases: Record<string, string> = {
  '/app/sector/stocks/alcohol_breweries': '/app/sector/stocks/alcohol-breweries',
  '/app/sector/stocks/auto_ancillaries': '/app/sector/stocks/auto-ancillaries',
  '/app/sector/stocks/auto_components_equipments': '/app/sector/stocks/auto-components-equipments',
  '/app/sector/stocks/auto-mobile': '/app/sector/stocks/auto',
  '/app/sector/stocks/healthcare-index': '/app/sector/stocks/healthcare',
  '/app/sector/stocks/midsmall-healthcare': '/app/sector/stocks/healthcare',
  '/app/sector/stocks/nifty500-healthcare': '/app/sector/stocks/healthcare',
  '/app/sector/stocks/oil-gas': '/app/sector/stocks/oil-and-gas',
  '/app/sector/stocks/telecom': '/app/sector/stocks/telecommunication',
  'alcohol_breweries': 'alcohol-breweries',
  'auto_ancillaries': 'auto-ancillaries',
  'auto_components_equipments': 'auto-components-equipments',
  'auto-mobile': 'auto',
  'healthcare-index': 'healthcare',
  'midsmall-healthcare': 'healthcare',
  'nifty500-healthcare': 'healthcare',
  'oil-gas': 'oil-and-gas',
  'telecom': 'telecommunication',
};

function normalizeNavPage(page?: string): string | undefined {
  return page?.trim().replace(/^\//, '').toLowerCase();
}

export function findSectorPageByCode(code: string): SectorPageItem | undefined {
  const normalized = code.trim().toUpperCase();
  const canonical = sectorCodeAliases[normalized] ?? normalized;
  const found = sectorPageItems.find((item) => item.code === canonical);
  if (found) return found;

  const slug = canonical.toLowerCase().replace(/_/g, '-');
  return {
    code: canonical,
    href: `/app/sector/stocks/${slug}`,
    label: canonical.replace(/_/g, ' '),
    page: `/app/sector/stocks/${slug}`,
    slug: slug,
  };
}

export function findSectorPageByPath(pathname: string): SectorPageItem | undefined {
  const normalized = pathname.trim().replace(/^\//, '').toLowerCase();
  const appStocksPrefix = 'app/sector/stocks/';
  const shortStocksPrefix = 'sector/stocks/';
  const slug = normalized.startsWith(appStocksPrefix)
    ? normalized.slice(appStocksPrefix.length)
    : normalized.startsWith(shortStocksPrefix)
      ? normalized.slice(shortStocksPrefix.length)
      : '';
  
  if (!slug) return undefined;

  const canonicalPage = sectorPathAliases[normalized] ?? normalized;
  const canonicalSlug = sectorPathAliases[slug] ?? slug;
  
  const normalizedSlug = canonicalSlug.replace(/_/g, '-');
  const normalizedPage = canonicalPage.includes('/app/sector/stocks/')
    ? `/app/sector/stocks/${normalizedSlug}`
    : canonicalPage;

  const found = sectorPageItems.find(
    (item) => item.page === canonicalPage
      || item.page === normalizedPage
      || item.slug === canonicalSlug
      || item.slug === normalizedSlug,
  );
  if (found) return found;

  // Fallback for dynamic discovery without hardcoding
  const uppercaseSlug = normalizedSlug.replace(/-/g, '_').toUpperCase();
  return {
    code: uppercaseSlug,
    href: `/app/sector/stocks/${normalizedSlug}`,
    label: uppercaseSlug.replace(/_/g, ' '),
    page: `/app/sector/stocks/${normalizedSlug}`,
    slug: normalizedSlug,
  };
}

export function isSectorStocksFamilyPage(page?: string): boolean {
  const normalized = normalizeNavPage(page);
  if (!normalized) return false;
  if (normalized === normalizeNavPage(SECTOR_DIRECTORY_PAGE)) return true;
  return sectorPageItems.some((item) => normalizeNavPage(item.page) === normalized);
}

export function isSectorDropdownPageActive(activePage: string | undefined, navPage: string): boolean {
  const normalizedActivePage = normalizeNavPage(activePage);
  const normalizedNavPage = normalizeNavPage(navPage);
  if (!normalizedActivePage) return false;
  if (!normalizedNavPage) return false;
  if (normalizedNavPage === normalizeNavPage(SECTOR_DIRECTORY_PAGE)) {
    return isSectorStocksFamilyPage(normalizedActivePage);
  }
  return normalizedActivePage === normalizedNavPage;
}

export function isSectorNavPageActive(activePage: string | undefined, navPage: string): boolean {
  return isSectorDropdownPageActive(activePage, navPage);
}

