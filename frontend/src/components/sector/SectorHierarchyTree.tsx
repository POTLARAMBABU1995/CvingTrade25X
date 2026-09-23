import type { SectorHierarchyTree } from '../../types/sectorHierarchy';

export function SectorHierarchyTree({ tree }: { tree: SectorHierarchyTree | null }) {
  if (!tree || !tree.industries.length) {
    return <div className="empty">No hierarchy tree available for the selected parent sector.</div>;
  }

  return (
    <section className="sector-hierarchy-tree" aria-label="Sector hierarchy tree">
      <h3 className="sector-hierarchy-tree__title">{tree.parentSector} Hierarchy</h3>
      <div className="sector-hierarchy-tree__body">
        {tree.industries.map((industry) => (
          <article key={industry.industrySector} className="sector-hierarchy-tree__industry">
            <header className="sector-hierarchy-tree__industry-header">
              <span>{industry.industrySector}</span>
              <span className="count-pill">{industry.stockCount} stocks</span>
            </header>
            <ul className="sector-hierarchy-tree__sub-list">
              {industry.subSectors.map((subSector) => (
                <li key={`${industry.industrySector}-${subSector.subSector}`} className="sector-hierarchy-tree__sub-item">
                  <div className="sector-hierarchy-tree__sub-row">
                    <span>{subSector.subSector}</span>
                    <span className="count-pill">{subSector.stockCount}</span>
                  </div>
                  <p className="sector-hierarchy-tree__symbols">
                    {subSector.stocks.slice(0, 8).map((item) => item.symbol).join(', ')}
                    {subSector.stocks.length > 8 ? ` +${subSector.stocks.length - 8} more` : ''}
                  </p>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
