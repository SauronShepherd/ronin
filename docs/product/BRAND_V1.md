# Ronin Brand v1

**Status:** normative visual identity for product UI and public documentation

## 1. Brand rule

Ronin's dominant product color is **brown**.

The logo already establishes the intended visual family: warm brown fur, black/charcoal armor, gold/amber metal and ivory highlights. Product UI should derive from that family rather than adopting the dominant red/green/blue identities associated with other major data platforms.

Red, green and blue remain available as semantic status colors. They are not Ronin's brand anchors.

## 2. Core palette

### Primary brown

| Token | Hex | Role |
|---|---|---|
| `ronin-brown-950` | `#241A16` | deepest brown backgrounds |
| `ronin-brown-900` | `#35251D` | dark surfaces |
| `ronin-brown-800` | `#503020` | dark brand emphasis |
| `ronin-brown-700` | `#604030` | strong brand brown |
| `ronin-brown-600` | `#705040` | primary interactive brown |
| `ronin-brown-500` | `#806050` | medium brown |
| `ronin-brown-400` | `#A47A5A` | hover/highlight on dark UI |
| `ronin-brown-300` | `#C9A383` | muted warm highlight |
| `ronin-brown-200` | `#E3C8AD` | borders/tinted backgrounds |
| `ronin-brown-100` | `#F2E3D2` | light brand surface |
| `ronin-brown-50` | `#FAF5EE` | lightest warm canvas |

The default primary token is **`ronin-brown-600` / `#705040`**.

### Gold / amber accent

| Token | Hex | Role |
|---|---|---|
| `ronin-gold-700` | `#B96800` | dark gold accent |
| `ronin-gold-600` | `#D88000` | strong accent |
| `ronin-gold-500` | `#F0A010` | logo-derived primary gold |
| `ronin-gold-400` | `#F0B010` | interactive highlight |
| `ronin-gold-300` | `#F0C020` | selected/attention highlight |

Gold is an accent, not the dominant canvas color.

### Neutrals

| Token | Hex | Role |
|---|---|---|
| `ronin-charcoal-950` | `#111111` | app chrome / deepest surface |
| `ronin-charcoal-900` | `#202020` | dark panel |
| `ronin-charcoal-800` | `#303030` | elevated dark surface |
| `ronin-ivory-100` | `#F0E0D0` | warm neutral |
| `ronin-ivory-50` | `#FFF9F2` | light app surface |
| `ronin-white` | `#FFFFFF` | high-contrast text/background |

## 3. Semantic status colors

Status colors are intentionally separate from brand colors:

- success: green;
- warning: amber/yellow;
- error/destructive: red;
- information: blue;
- neutral/unknown: gray.

A success screen must not become predominantly green; an error screen must not become predominantly red. Brand chrome remains brown/charcoal.

## 4. UI application

### Light theme

- app background: ivory/white;
- primary navigation/selection: brown;
- focused/active accents: brown + gold;
- main CTA: brown with accessible light text;
- secondary CTA: warm neutral border with brown text;
- selected tabs/graph nodes: brown family;
- high-value highlights: gold sparingly.

### Dark theme

- app background: charcoal;
- raised surfaces: charcoal/brown-black;
- primary interactive state: medium/light brown;
- high-value highlights: gold;
- body text: ivory/white.

## 5. Data visualization

Ronin dashboards must not encode all series as shades of brown. Brown is the product frame; analytical charts use a categorical/sequential visualization palette chosen for contrast and accessibility.

Rules:

- reserve primary brown for selected/current series where useful;
- reserve gold for emphasis, targets or highlighted measures;
- use color-blind-safe categorical palettes for multiple unrelated series;
- never rely on color alone for alert severity or line identity;
- ontology/lineage graphs use node shape/icon + label + color rather than color alone.

## 6. Product surface identity

All first-party surfaces use the same tokens:

- Studio web UI;
- CLI rich output where color is enabled;
- generated HTML reports;
- documentation diagrams;
- dashboards;
- ontology and lineage explorers;
- AI/ML Lab;
- monitoring and FinOps control center.

Provider/vendor badges may use vendor colors only inside bounded badges/icons. They must not recolor the Ronin application shell.

## 7. Logo usage

The supplied Ronin logo is the visual reference for the palette. Do not recolor the logo to a competitor-associated primary color.

When the full horizontal logo is too wide, a future official mark may use the samurai-dog emblem alone, but any derived mark must preserve the brown/gold/charcoal family.

## 8. Accessibility

Before Public v1 release:

- all interactive text/background combinations meet WCAG AA contrast at minimum;
- focus state is visible independently of color;
- status indicators combine text/icon/shape with color;
- chart palettes are tested for common color-vision deficiencies;
- light and dark themes have explicit token tests.

## 9. Implementation tokens

Frontends SHOULD consume semantic tokens rather than raw hex values:

```text
--ronin-color-primary
--ronin-color-primary-hover
--ronin-color-primary-active
--ronin-color-accent
--ronin-color-surface
--ronin-color-surface-raised
--ronin-color-text
--ronin-color-text-muted
--ronin-color-border
--ronin-color-focus
```

The web implementation may map these onto CSS variables, a design-token JSON file or another generated theme format, but `BRAND_V1.md` remains the visual contract until a machine-readable token file is added.
