import { placeV197StarBrainHost } from "../bridge/v197StarBrain";

describe("V197 star brain placement", () => {
  beforeEach(() => {
    document.body.className = "universe-edition";
    document.body.replaceChildren();
  });

  it("replaces the Map MasterStar fallback with the one exact brain host", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61">
        <section id="page-universe-map" class="active">
          <div class="lens-map-master"><div class="spark f4-master-star nur-star-module"></div></div>
        </section>
      </main>
    `;

    placeV197StarBrainHost(document);
    const mapHost = document.querySelector<HTMLElement>(".lens-map-master");
    const brain = mapHost?.querySelector<HTMLElement>("#front-nur-star");
    expect(brain?.dataset.nurSurface).toBe("map");
    expect(brain?.dataset.nurRigDepth).toBe("projected-3d");
    expect(mapHost?.dataset.nurLegacyMasterStar).toBe("removed");
    expect(mapHost?.querySelector(".spark, .f4-master-star, .nur-star-module")).toBeNull();
    expect(document.querySelectorAll("#front-nur-star")).toHaveLength(1);
  });

  it("clones Entry's exact three-ring halo structure around the Systems brain", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61">
        <section id="page-systems" class="active">
          <div class="universe-map-panel">
            <div class="universe-master-star">
              <div class="f4-core"><div class="spark f4-master-star"></div></div>
            </div>
          </div>
        </section>
      </main>
    `;

    placeV197StarBrainHost(document);
    const host = document.querySelector<HTMLElement>(".universe-master-star");
    const halos = host?.querySelectorAll<HTMLElement>(":scope > .nur-v197-brain-orbit-halo");
    expect(host?.querySelector("#front-nur-star")?.getAttribute("data-nur-surface")).toBe("universe");
    expect(halos).toHaveLength(3);
    expect(Array.from(halos ?? []).map(halo => halo.dataset.nurHaloSource))
      .toEqual(["entry-f4-ring", "entry-f4-ring", "entry-f4-ring"]);
    expect(host?.querySelector(":scope > .f4-ring.two")).not.toBeNull();
    expect(host?.querySelector(":scope > .f4-ring.three")).not.toBeNull();
    expect(host?.querySelector(":scope > .f4-core, :scope > .spark, :scope > .f4-master-star")).toBeNull();
  });
});
